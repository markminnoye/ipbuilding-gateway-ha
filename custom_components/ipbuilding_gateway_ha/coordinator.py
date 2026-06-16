"""WebSocket coordinator for ipbuilding_gateway_ha.

Manages the WebSocket connection to the gateway, maintains device state,
and dispatches updates to platform entities.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from typing import Any, Callable

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_PORT,
    CONF_API_HOST,
    DEFAULT_API_PORT,
    DOMAIN,
    RECONNECT_BACKOFF_MULT,
    RECONNECT_BASE_DELAY,
    RECONNECT_JITTER,
    RECONNECT_MAX_DELAY,
)
from .entity import registry_unique_ids_for_device

log = logging.getLogger(__name__)


class IPBuildingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates WebSocket connection to the IPBuilding Gateway.

    Manages device state received via WebSocket and notifies listeners
    for specific entity updates.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self._host = str(entry.data.get(CONF_API_HOST, ""))
        self._port = int(entry.data.get(CONF_API_PORT, DEFAULT_API_PORT))
        self._ws_url = f"ws://{self._host}:{self._port}/ws"
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_session: aiohttp.ClientSession | None = None
        self._ws_connected = asyncio.Event()
        self._receive_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._reconnect_delay = RECONNECT_BASE_DELAY
        # Per-entity listeners: entity_id -> [callback(state)]
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {}
        # Module metadata keyed by MAC, populated from the WebSocket `snapshot`
        # `modules` field. Used by the 3-tier device tree (channel -> module
        # -> gateway). Older `device_list` messages do not carry modules.
        self._modules: dict[str, dict[str, Any]] = {}
        # Snapshot-driven dynamic entity lifecycle: (device_id, active) pairs
        # last seen, used to detect new/removed/flipped channels.
        self._known_devices: set[tuple[str, bool]] = set()
        # Debounce: coalesce burst of snapshot messages (e.g. WS reconnect)
        # into a single diff pass.
        self._diff_timer: asyncio.TimerHandle | None = None
        # Platforms (light/switch/sensor) call register_platform() so the
        # coordinator can ask them to add or remove entities when the snapshot
        # changes. Each entry: {platform -> {device_id -> [entity]}}.
        self._platform_callbacks: dict[str, Callable[[list[dict]], None]] = {}
        self._platform_entities: dict[str, dict[str, list[Any]]] = {}
        self._entry = entry
        self._gateway_status: dict[str, Any] = {}
        self._gateway_listeners: list[Callable[[dict[str, Any]], None]] = []
        super().__init__(hass, log, name=DOMAIN)

    @property
    def api_host(self) -> str:
        return self._host

    @property
    def api_port(self) -> int:
        return self._port

    @property
    def gateway_status(self) -> dict[str, Any]:
        return self._gateway_status

    @property
    def modules(self) -> dict[str, dict[str, Any]]:
        """Return cached module metadata keyed by MAC."""
        return dict(self._modules)

    def module_by_id(self, mac: str) -> dict[str, Any] | None:
        """Return a module dict by MAC, or None if unknown."""
        return self._modules.get(mac)

    def module_for_channel(self, device: dict[str, Any]) -> dict[str, Any] | None:
        """Return the parent module dict for a channel/button device."""
        return self._modules.get(device.get("module_id", ""))

    @property
    def ws_url(self) -> str:
        return self._ws_url

    # -------------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # -------------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch gateway status and device list via REST as a fallback when WS is unavailable."""
        await self.async_fetch_gateway_status()
        # Populate module metadata so the device tree (gateway -> module ->
        # channel) can be registered at setup time, independent of WS snapshot
        # timing. The WS `snapshot` keeps `self._modules` fresh afterwards.
        await self.async_fetch_modules()
        url = f"http://{self._host}:{self._port}/api/v1/devices"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        devices = data.get("devices", [])
                    else:
                        log.warning("REST fallback returned %s", resp.status)
                        devices = []
        except Exception as exc:
            log.debug("REST fallback failed: %s", exc)
            devices = []
        # Mirror the WS handler: cache by id so platforms that read the
        # coordinator via ``devices_snapshot()`` get a consistent dict on
        # every code path, and the in-memory state is no longer ahead of the
        # ``coordinator.data`` that the DataUpdateCoordinator exposes.
        self._data = {d["id"]: d for d in devices if d.get("id")}
        return self._data

    async def async_fetch_modules(self) -> dict[str, dict[str, Any]]:
        """Poll GET /api/v1/modules and cache the result keyed by MAC.

        Used at setup to register the per-module devices (Tier 2) before the
        WebSocket snapshot arrives. Returns the cached modules dict.
        """
        url = f"http://{self._host}:{self._port}/api/v1/modules"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        modules = data.get("modules", [])
                        self._modules = {m["id"]: m for m in modules if m.get("id")}
                    else:
                        log.warning("Gateway modules returned %s", resp.status)
        except Exception as exc:
            log.debug("Gateway modules fetch failed: %s", exc)
        return dict(self._modules)

    async def async_fetch_gateway_status(self) -> dict[str, Any]:
        """Poll GET /api/v1/status (fallback: /health for version only)."""
        status_url = f"http://{self._host}:{self._port}/api/v1/status"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    status_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._apply_gateway_status(data)
                        return self._gateway_status
                    log.warning("Gateway status returned %s", resp.status)
        except Exception as exc:
            log.debug("Gateway status fetch failed: %s", exc)

        health_url = f"http://{self._host}:{self._port}/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    health_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._apply_gateway_status({
                            "status": data.get("status", "ok"),
                            "version": data.get("version"),
                            "issues": [],
                            "subsystems": {},
                        })
                        return self._gateway_status
        except Exception as exc:
            log.debug("Gateway health fallback failed: %s", exc)
        return self._gateway_status

    async def async_trigger_discover(self) -> None:
        """Run POST /api/v1/discover on the gateway."""
        url = f"http://{self._host}:{self._port}/api/v1/discover"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        log.warning("Discover sweep returned %s", resp.status)
                    else:
                        log.info("Discover sweep completed: %s", await resp.text())
        except Exception as exc:
            log.warning("Discover sweep failed: %s", exc)
        await self.async_fetch_gateway_status()
        self._notify_gateway()

    def register_gateway_listener(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register for gateway_status updates."""
        self._gateway_listeners.append(callback)

    def unregister_gateway_listener(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Unregister a gateway_status listener."""
        with contextlib.suppress(ValueError):
            self._gateway_listeners.remove(callback)

    def _apply_gateway_status(self, data: dict[str, Any]) -> None:
        """Store gateway status payload (REST or WS)."""
        self._gateway_status = {k: v for k, v in data.items() if k != "type"}

    def _notify_gateway(self) -> None:
        for cb in self._gateway_listeners:
            try:
                cb(self._gateway_status)
            except Exception:
                log.exception("Gateway status listener error")

    # -------------------------------------------------------------------------
    # WebSocket lifecycle
    # -------------------------------------------------------------------------

    async def _async_connect(self) -> bool:
        """Establish WebSocket connection to the gateway.

        Returns True if connected, False otherwise.
        """
        try:
            self._ws_session = aiohttp.ClientSession()
            # ``receive_timeout=None`` and ``heartbeat=None`` on the client:
            # aiohttp 3.13.5 (HA Core 2026.x ships it) has a known race where
            # the client heartbeat task sometimes consumes a PONG that should
            # have been delivered to receive(), causing the receive loop to
            # timeout and tear the connection down every 30s
            # (aio-libs/aiohttp#12030, fixed in 3.14.0). The gateway now owns
            # the keep-alive (heartbeat=60 in gateway_api.py), so we let the
            # client sit idle and trust the server's PINGs.
            self._ws = await self._ws_session.ws_connect(
                self._ws_url,
                receive_timeout=None,
                heartbeat=None,
            )
            self._ws_connected.set()
            self._reconnect_delay = RECONNECT_BASE_DELAY
            log.info("WebSocket connected to %s", self._ws_url)
            return True
        except Exception as exc:
            log.warning("WebSocket connect failed: %s", exc)
            await self._close_ws_session()
            return False

    async def _close_ws_session(self) -> None:
        """Close the WebSocket and session."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._ws_session is not None:
            try:
                await self._ws_session.close()
            except Exception:
                pass
            self._ws_session = None
        self._ws_connected.clear()

    async def start(self) -> None:
        """Start the WebSocket receive loop with reconnect logic."""
        self._stop_event.clear()
        if not await self._async_connect():
            # Schedule reconnect
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            return

        self._receive_task = asyncio.create_task(self._receive_loop())

    async def stop(self) -> None:
        """Stop the receive loop and close the connection."""
        self._stop_event.set()
        if self._receive_task is not None:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None
        await self._close_ws_session()

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect with exponential backoff + jitter.

        On a successful connect the delay is reset to ``RECONNECT_BASE_DELAY``
        in :meth:`_async_connect` so the next disconnect starts fresh.
        """
        while not self._stop_event.is_set():
            # Apply ±RECONNECT_JITTER spread so multiple clients don't all
            # retry at the same instant after a gateway restart. random.uniform
            # is independent per coordinator instance (different HA integrations,
            # different gateway hosts), unlike a clock-derived value which is
            # ~identical for clients that dropped at the same moment.
            jitter = random.uniform(-RECONNECT_JITTER, RECONNECT_JITTER)
            delay = self._reconnect_delay * (1.0 + jitter)
            await asyncio.sleep(max(0.0, delay))
            if self._stop_event.is_set():
                break
            if await self._async_connect():
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._reconnect_task = None
                return
            self._reconnect_delay = min(
                self._reconnect_delay * RECONNECT_BACKOFF_MULT,
                RECONNECT_MAX_DELAY,
            )

    async def _receive_loop(self) -> None:
        """Receive and process WebSocket messages.

        Distinguishes three close paths so the HA log doesn't fill with
        ``WS receive error:`` lines every keep-alive cycle:

        1. ``WSMsgType.CLOSE`` / ``CLOSED`` — server- or peer-initiated
           graceful close → log at DEBUG.
        2. ``aiohttp.ClientConnectionError`` from ``receive()`` — usually a
           server-closed socket without a close frame → log at DEBUG.
        3. Anything else (real exception, ``WSMsgType.ERROR`` with an
           attached exception) → log at WARNING.
        """
        while True:
            if self._ws is None:
                break
            try:
                msg = await self._ws.receive()
            except aiohttp.ClientConnectionError as exc:
                log.debug("WS connection closed by server: %s", exc)
                break
            except Exception as exc:
                log.warning("WS receive error: %s", exc)
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_message(msg.data)
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                log.debug("WS closed (type=%s)", msg.type)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                err = self._ws.exception() if self._ws is not None else None
                if err is None:
                    log.debug("WS error frame without exception (graceful)")
                    break
                log.warning("WS error: %s", err)
                break

        await self._close_ws_session()
        # Schedule reconnect
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    # -------------------------------------------------------------------------
    # Message handling
    # -------------------------------------------------------------------------

    async def _handle_message(self, raw: str | dict) -> None:
        """Parse and dispatch a WebSocket message."""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            log.warning("Invalid JSON from gateway: %r", raw)
            return

        msg_type = data.get("type")
        log.debug("WS message: type=%s", msg_type)

        if msg_type == "snapshot":
            # New format: snapshot contains both modules and devices.
            # The companion only needs devices for entity state.
            #
            # NOTE: we deliberately do NOT call ``self.async_set_updated_data``
            # here. That method notifies HA's built-in coordinator listeners
            # (0-arg callbacks registered via ``async_add_listener``). Our
            # entity platforms manage their own updates through
            # ``_notify_all`` / ``_notify`` (1-arg callbacks). Calling both
            # would trip the built-in listener path with the wrong arity.
            if gateway_status := data.get("gateway_status"):
                self._apply_gateway_status(gateway_status)
                self._notify_gateway()
            # Track per-MAC module metadata for the 3-tier device tree. Older
            # `snapshot` payloads did not include `modules`; the empty-dict
            # fallback preserves existing behaviour.
            self._modules = {m["id"]: m for m in data.get("modules", [])}
            devices = data.get("devices", [])
            self._data = {dev["id"]: dev for dev in devices}
            self._notify_all(devices)
            self._schedule_diff(devices)
        elif msg_type == "device_list":
            # Legacy format kept for backward compatibility.
            devices = data.get("devices", [])
            self._data = {dev["id"]: dev for dev in devices}
            self._notify_all(devices)
            self._schedule_diff(devices)
        elif msg_type == "state_changed":
            entity_id = data.get("id", "")
            self._data[entity_id] = dict(self._data.get(entity_id, {}), **data)
            self._notify(entity_id, data)
        elif msg_type == "button_event":
            # Button events go to all button entities; route by hardware id
            self._notify_button(data)
        elif msg_type == "gateway_status":
            self._apply_gateway_status(data)
            self._notify_gateway()
        elif msg_type == "discovery_completed":
            await self.async_fetch_gateway_status()
            self._notify_gateway()
        else:
            log.debug("Unknown WS message type: %s", msg_type)

    def _notify(self, entity_id: str, data: dict) -> None:
        """Notify listeners for a specific entity."""
        for cb in self._listeners.get(entity_id, []):
            try:
                cb(data)
            except Exception:
                log.exception("Listener error for %s", entity_id)

    def _notify_all(self, devices: list[dict]) -> None:
        """Notify all listeners about a full device list update."""
        for dev in devices:
            self._notify(dev.get("id", ""), dev)

    def _notify_button(self, data: dict) -> None:
        """Notify button entities (routed by hardware id, not entity_id)."""
        for cb in self._listeners.get(f"button:{data.get('id')}", []):
            try:
                cb(data)
            except Exception:
                log.exception("Button listener error")

    # -------------------------------------------------------------------------
    # Dynamic entity lifecycle
    # -------------------------------------------------------------------------

    def register_platform(
        self,
        platform: str,
        add_callback: Callable[[list[dict]], None],
    ) -> Callable[[], None]:
        """Register a platform's dynamic-entity callback.

        ``add_callback`` receives a list of *new* device dicts each time a
        snapshot diff produces additions. The platform is responsible for
        creating entities (and tracking them via :meth:`track_platform_entity`
        so the coordinator can remove them later).
        """
        self._platform_callbacks[platform] = add_callback
        self._platform_entities.setdefault(platform, {})

        def _unregister() -> None:
            self._platform_callbacks.pop(platform, None)
            self._platform_entities.pop(platform, None)

        return _unregister

    def track_platform_entity(self, platform: str, device_id: str, entity: Any) -> None:
        """Record a platform entity so it can be removed on snapshot diff."""
        self._platform_entities.setdefault(platform, {}).setdefault(device_id, []).append(entity)

    def _schedule_diff(self, devices: list[dict]) -> None:
        """Coalesce snapshot bursts into a single debounced diff pass.

        Without debouncing a WS reconnect could trigger N snapshot frames in
        a second and the diff machinery would run for each one, possibly
        bouncing entity registry entries on every frame.
        """
        if self._diff_timer is not None:
            self._diff_timer.cancel()
        loop = asyncio.get_running_loop()
        self._diff_timer = loop.call_later(
            2.0, lambda: asyncio.ensure_future(self._apply_diff(devices))
        )

    async def _apply_diff(self, devices: list[dict]) -> None:
        """Reconcile entity registry + platforms with the latest snapshot.

        Three classes of change are handled:

        * **Genuine additions** — an ``id`` not seen before → ask each platform
          to create entities for it.
        * **Genuine removals** — an ``id`` that disappeared from
          ``devices.json`` → remove its entities and registry entries.
        * **Active flips / cold-start** — an ``id`` whose ``active`` flag
          changed, *or* a device that re-appears on the first snapshot already
          set to ``active: false`` → toggle the entity-registry
          disabled/hidden flags instead of deleting anything.
        """
        self._diff_timer = None
        new_pairs = {(d["id"], bool(d.get("active", True))) for d in devices if d.get("id")}

        added_pairs = new_pairs - self._known_devices
        removed_pairs = self._known_devices - new_pairs

        added_ids = {dev_id for (dev_id, _active) in added_pairs}
        removed_ids = {dev_id for (dev_id, _active) in removed_pairs}

        # Set-difference can never place the same ``(id, active)`` pair in both
        # ``added_pairs`` and ``removed_pairs``, so an active *flip* shows up as
        # the *id* appearing in both sets. Detect flips on the id alone.
        flipped_ids = added_ids & removed_ids
        truly_added_ids = added_ids - flipped_ids
        truly_removed_ids = removed_ids - flipped_ids

        # Build device-id-keyed lookups for callbacks.
        devices_by_id = {d["id"]: d for d in devices if d.get("id")}

        # 1. Additions → ask each platform to create entities for new ids.
        if truly_added_ids:
            additions = [
                devices_by_id[dev_id]
                for dev_id in truly_added_ids
                if dev_id in devices_by_id
            ]
            for _platform, cb in self._platform_callbacks.items():
                # Each platform filters to the device types it can render.
                cb(additions)

        # 2. Removals → remove platform entities; clear from registry.
        for dev_id in truly_removed_ids:
            await self._remove_device_entities(dev_id)
            self._remove_registry_entry(dev_id)

        # 3. Flips + cold-start → reconcile disabled/hidden flags. We only
        #    reconcile ids that just appeared (cold-start) or flipped, so a
        #    user who manually re-enables a disabled entity is not fought on
        #    every steady-state snapshot.
        reconcile_ids = truly_added_ids | flipped_ids
        if reconcile_ids:
            self._reconcile_active(
                [devices_by_id[i] for i in reconcile_ids if i in devices_by_id]
            )

        self._known_devices = new_pairs

    async def _remove_device_entities(self, device_id: str) -> None:
        """Remove all tracked platform entities for ``device_id`` from HA."""
        for _platform, by_id in self._platform_entities.items():
            for entity in by_id.pop(device_id, []):
                if getattr(entity, "hass", None) is None:
                    # Entity was never added to HA (e.g. setup failed for this
                    # platform during the previous run). Skip — there is
                    # nothing to remove and async_remove would crash with
                    # "'NoneType' object has no attribute 'loop'".
                    log.debug(
                        "Skipping remove for %s: entity not registered with HA",
                        device_id,
                    )
                    continue
                try:
                    await entity.async_remove(force_remove=True)
                except TypeError:
                    # Older HA without force_remove
                    await entity.async_remove()
                except Exception:
                    log.exception("Failed to remove entity for %s", device_id)

    def _remove_registry_entry(self, device_id: str) -> None:
        """Remove any HA entity_registry entry for ``device_id`` (best-effort)."""
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        remove_uids = {device_id, f"{device_id}_power", f"event_{device_id}"}
        for reg_entry in list(registry.entities.values()):
            if reg_entry.unique_id in remove_uids:
                registry.async_remove(reg_entry.entity_id)

    def _reconcile_active(self, devices: list[dict]) -> None:
        """Sync entity-registry disabled/hidden flags with ``active`` flags.

        For every device passed in, the matching registry entries (the bare
        device id used by light/switch, the ``<id>_power`` id used by the
        power sensor, and ``event_<id>`` for IP1100PoE buttons) are
        disabled+hidden when ``active`` is false, and the integration-applied
        disable/hide is cleared again when it is true.

        A single pass over the registry keeps this O(registry size) instead of
        O(devices × registry size).
        """
        from homeassistant.helpers import entity_registry as er

        active_by_uid: dict[str, bool] = {}
        for dev in devices:
            dev_id = dev.get("id")
            if not dev_id:
                continue
            active = bool(dev.get("active", True))
            for uid in registry_unique_ids_for_device(dev):
                active_by_uid[uid] = active

        if not active_by_uid:
            return

        registry = er.async_get(self.hass)
        for reg_entry in list(registry.entities.values()):
            if reg_entry.platform != DOMAIN:
                continue
            active = active_by_uid.get(reg_entry.unique_id)
            if active is None:
                continue

            update_kwargs: dict[str, Any] = {}
            if not active:
                # Only set our own marker; never clobber a USER-set disable.
                if reg_entry.disabled_by is None:
                    update_kwargs["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION
                if reg_entry.hidden_by is None:
                    update_kwargs["hidden_by"] = er.RegistryEntryHider.INTEGRATION
            else:
                # Only clear what the integration disabled/hid, so a user's
                # explicit "hide this" is not undone silently.
                if reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                    update_kwargs["disabled_by"] = None
                if reg_entry.hidden_by is er.RegistryEntryHider.INTEGRATION:
                    update_kwargs["hidden_by"] = None

            if update_kwargs:
                registry.async_update_entity(reg_entry.entity_id, **update_kwargs)
                log.debug(
                    "Reconciled %s (active=%s): %s",
                    reg_entry.entity_id,
                    active,
                    update_kwargs,
                )

    # -------------------------------------------------------------------------
    # Entity registration
    # -------------------------------------------------------------------------

    def register_entity(self, entity_id: str, callback: Callable[[dict], None]) -> None:
        """Register a callback for entity updates.

        Args:
            entity_id: e.g. "10.10.1.30:relay:0" or "button:2DE341851900001F"
            callback: called with the new state data on each update.
        """
        self._listeners.setdefault(entity_id, []).append(callback)

    def unregister_entity(self, entity_id: str, callback: Callable[[dict], None]) -> None:
        """Remove a callback for an entity."""
        if entity_id in self._listeners:
            self._listeners[entity_id] = [
                cb for cb in self._listeners[entity_id] if cb is not callback
            ]

    # -------------------------------------------------------------------------
    # Command sending
    # -------------------------------------------------------------------------

    async def async_send_command(
        self,
        entity_id: str,
        action: str,
        value: int | None = None,
    ) -> bool:
        """Send a command to the gateway via WebSocket.

        Returns True if the command was acknowledged by the gateway
        (command_result.ok=true).
        """
        if self._ws is None or not self._ws_connected.is_set():
            log.warning("Cannot send command: WS not connected")
            return False

        msg: dict[str, Any] = {"type": "command", "id": entity_id, "action": action}
        if value is not None:
            msg["value"] = value

        try:
            await self._ws.send_json(msg)
            log.debug("Command sent: %s %s %s", entity_id, action, value)
            return True
        except Exception as exc:
            log.warning("Failed to send command: %s", exc)
            return False

    # -------------------------------------------------------------------------
    # State access helpers
    # -------------------------------------------------------------------------

    def get_device_state(self, entity_id: str) -> dict[str, Any] | None:
        """Return cached state for an entity."""
        return self._data.get(entity_id) if isinstance(self._data, dict) else None

    def all_device_ids(self) -> list[str]:
        """Return all known entity IDs."""
        return list(self._data.keys()) if isinstance(self._data, dict) else []

    def devices_snapshot(self) -> list[dict[str, Any]]:
        """Return the current device list from WS cache or REST fallback."""
        if isinstance(self._data, dict) and self._data:
            return list(self._data.values())
        raw = self.data
        if isinstance(raw, dict):
            return list(raw.values())
        if isinstance(raw, list):
            return raw
        return []

    def seed_known_devices(self, devices: list[dict[str, Any]] | None = None) -> None:
        """Mark devices as known so the first WS snapshot diff does not re-add them.

        Call once after all platforms finish their initial ``async_setup_entry``
        pass. Without this, the debounced diff triggered by the first WebSocket
        ``snapshot`` treats every channel as a brand-new addition and HA logs
        "does not generate unique IDs" for each entity.
        """
        snapshot = devices if devices is not None else self.devices_snapshot()
        self._known_devices = {
            (d["id"], bool(d.get("active", True))) for d in snapshot if d.get("id")
        }