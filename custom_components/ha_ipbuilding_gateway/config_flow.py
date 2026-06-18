"""Config flow for IPBuilding Gateway HA.

Three discovery paths are supported, modelled after the Music Assistant
pattern:

1. **Supervisor add-on** (``async_step_hassio``) — the add-on posts to
   ``/supervisor/discovery`` and Home Assistant invokes this step with
   the add-on's host and port.
2. **Zeroconf / mDNS** (``async_step_zeroconf``) — the gateway broadcasts
   ``_ipbgw._tcp.local.`` on the LAN. The companion parses
   the TXT record; when the gateway is running as a Supervisor add-on
   (``homeassistant_addon=true``) we abort to avoid duplicate entries.
3. **Manual** (``async_step_user``) — operator enters host and port
   themselves (standalone Docker, remote setup, or a LAN discovery that
   never reached HA's mDNS listener).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar, selector
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .button_automation_builder import summarise_for_wizard
from .button_mapping import parse_buttons
from .gateway_rest import (
    async_fetch_button_config,
    async_fetch_devices,
    async_refresh_module_metadata,
    async_run_discover,
)
from .const import (
    CONF_IMPORT_BUTTONS,
    CONF_ONBOARDING_COMPLETED,
    CONF_ROOM_MAPPINGS,
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DISCOVERY_SCHEMA_VERSION,
    DOMAIN,
)
from .discovery_parser import (
    GatewayDiscoveryInfo,
    parse_zeroconf_properties as _parse_zeroconf_properties,
)
from .room_mapping import collect_unique_rooms

log = logging.getLogger(__name__)

ADDON_SLUG = "ipbuilding_gateway"

# Voluptuous schema for the manual fallback form.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_API_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_API_PORT): int,
    }
)


async def _validate_gateway(host: str, port: int) -> tuple[bool, str | None, str | None]:
    """Check the gateway is reachable and fetch its ``instance_id``.

    Returns ``(ok, error, instance_id)``. ``instance_id`` is the gateway's
    stable HA-discovery UUID when available, used as ``unique_id`` for
    the manual config flow.
    """
    url = f"http://{host}:{port}/api/v1/status"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return False, "gateway_unreachable", None
                data = await resp.json()
                instance_id = data.get("instance_id") or None
                log.info("Gateway validated: instance_id=%s", instance_id)
                return True, None, instance_id
    except aiohttp.ClientConnectorError:
        return False, "connection_refused", None
    except Exception as exc:
        log.debug("Gateway validation failed: %s", exc)
        return False, "gateway_unreachable", None


class IPBuildingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPBuilding Gateway HA."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: GatewayDiscoveryInfo | None = None
        # Onboarding wizard state (runs inside this flow before the entry exists).
        self._ob_host: str = ""
        self._ob_port: int = DEFAULT_API_PORT
        self._ob_title: str = "IPBuilding Gateway"
        self._ob_devices: list[dict[str, Any]] = []
        self._ob_buttons: list[dict[str, Any]] = []
        self._ob_rooms: list[str] = []
        self._ob_room_mappings: dict[str, str] = {}
        self._ob_import_buttons: bool = True
        self._ob_prepared: bool = False
        self._ob_prepare_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # User (manual) step
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual host/port entry (fallback / remote)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            valid, error, instance_id = await _validate_gateway(host, port)
            if valid:
                unique_id = instance_id or f"{host}:{port}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates=user_input)
                return await self._start_onboarding(
                    host, int(port), f"IPBuilding Gateway ({host})"
                )
            errors["base"] = error or "gateway_unreachable"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "host": user_input.get(CONF_HOST, "") if user_input else "",
                "port": str(user_input.get(CONF_PORT, DEFAULT_API_PORT))
                if user_input
                else "",
            },
        )

    # ------------------------------------------------------------------
    # Supervisor add-on discovery
    # ------------------------------------------------------------------

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Supervisor add-on discovery.

        The companion's unique_id is the add-on's discovery UUID. The
        entry is created only after the operator explicitly clicks
        *Toevoegen* in the **Discovered** UI.
        """
        if discovery_info.slug != ADDON_SLUG:
            return self.async_abort(reason="not_ipbuilding_gateway_addon")

        host = discovery_info.config.get("host")
        port = discovery_info.config.get("port", DEFAULT_API_PORT)
        if not host:
            return self.async_abort(reason="invalid_discovery_info")

        await self.async_set_unique_id(discovery_info.uuid)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=int(port),
            instance_id=None,
            base_url=None,
            is_addon=True,
            version=None,
            schema_version=0,
        )
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the add-on discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            host = self._discovery_info.host
            port = self._discovery_info.port
            valid, error, _ = await _validate_gateway(host, port)
            if not valid:
                return self.async_abort(reason="cannot_connect")

            return await self._start_onboarding(
                host, int(port), "IPBuilding Gateway (add-on)"
            )

        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={
                "url": f"http://{host}:{port}",
                "version": "onbekend",
            },
        )

    # ------------------------------------------------------------------
    # Zeroconf discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Zeroconf discovery broadcast from the gateway.

        The TXT record carries the same fields as the HassIO payload so
        the same parsing path works. When the gateway identifies itself
        as a Supervisor add-on, we abort — that case is handled by
        ``async_step_hassio`` and we don't want a duplicate entry.
        """
        log.info(
            "Zeroconf discovery received: type=%s name=%s srv_host=%s srv_port=%s properties=%s",
            discovery_info.type,
            discovery_info.name,
            getattr(discovery_info, "host", None),
            getattr(discovery_info, "port", None),
            discovery_info.properties,
        )
        try:
            parsed = _parse_zeroconf_properties(
                discovery_info.properties,
                host=discovery_info.host,
                port=discovery_info.port,
            )
        except (KeyError, ValueError) as exc:
            log.warning(
                "Invalid zeroconf payload (%s): %s",
                exc, discovery_info.properties,
            )
            return self.async_abort(reason="invalid_discovery_info")

        log.info(
            "Parsed zeroconf: host=%s port=%d is_addon=%s schema=%d",
            parsed.host, parsed.port, parsed.is_addon, parsed.schema_version,
        )

        # Deduplicate: when the gateway is running as an HA add-on, the
        # HassIO flow is the authoritative one.
        if (
            parsed.schema_version >= DISCOVERY_SCHEMA_VERSION
            and parsed.is_addon
        ):
            log.debug("Ignoring add-on gateway in zeroconf discovery")
            return self.async_abort(reason="already_discovered_addon")

        host = parsed.host or discovery_info.host
        port = parsed.port or discovery_info.port
        if not host or not port:
            return self.async_abort(reason="invalid_discovery_info")

        # Validate that the gateway actually answers on the advertised address.
        valid, error, _ = await _validate_gateway(host, port)
        if not valid:
            log.info("Discovered gateway %s:%d unreachable: %s", host, port, error)
            return self.async_abort(reason="cannot_connect")

        unique_id = parsed.instance_id or f"{host}:{port}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: host, CONF_PORT: port}
        )

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=port,
            instance_id=parsed.instance_id,
            base_url=parsed.base_url,
            is_addon=parsed.is_addon,
            version=parsed.version,
            schema_version=parsed.schema_version,
        )
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a Zeroconf (standalone) discovery."""
        assert self._discovery_info is not None
        info = self._discovery_info
        url = info.base_url or f"http://{info.host}:{info.port}"

        if user_input is not None:
            return await self._start_onboarding(
                info.host, int(info.port), "IPBuilding Gateway"
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "url": url,
                "version": info.version or "onbekend",
            },
        )

    # ------------------------------------------------------------------
    # Onboarding wizard (runs inside the coupling flow, before the entry
    # exists). Reads the gateway over REST and persists the operator's
    # choices into the entry; the actual area assignment and button
    # automations are applied in ``async_setup_entry`` once entities and
    # devices exist.
    # ------------------------------------------------------------------

    async def _start_onboarding(
        self, host: str, port: int, title: str
    ) -> ConfigFlowResult:
        """Begin the in-flow wizard after a gateway has been confirmed."""
        self._ob_host = host
        self._ob_port = port
        self._ob_title = title
        return await self.async_step_ob_prepare()

    async def async_step_ob_prepare(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Load gateway data; run a one-off sweep/metadata refresh if needed.

        Fast path — the gateway already exposes channels *and* buttons: no
        spinner, straight to room mapping. Otherwise a single progress spinner
        covers a discovery sweep (empty gateway) and a ``getButtons`` refresh
        so input-module buttons and their rooms are present for mapping.
        """
        if self._ob_prepared:
            return await self.async_step_ob_rooms()

        if self._ob_prepare_task is None:
            devices = await async_fetch_devices(self._ob_host, self._ob_port)
            has_buttons = any(d.get("semantic_type") == "button" for d in devices)
            if devices and has_buttons:
                self._ob_devices = devices
                self._ob_buttons = await async_fetch_button_config(
                    self._ob_host, self._ob_port
                )
                self._ob_prepared = True
                return await self.async_step_ob_rooms()
            self._ob_prepare_task = self.hass.async_create_task(
                self._ob_prepare_data()
            )
            return self.async_show_progress(
                step_id="ob_prepare",
                progress_action="preparing",
                progress_task=self._ob_prepare_task,
            )

        try:
            await self._ob_prepare_task
        except Exception as exc:  # noqa: BLE001 — best-effort, already logged
            log.debug("Onboarding prepare raised: %s", exc)
        finally:
            self._ob_prepare_task = None
            self._ob_prepared = True
        return self.async_show_progress_done(next_step_id="ob_rooms")

    async def _ob_prepare_data(self) -> None:
        devices = await async_fetch_devices(self._ob_host, self._ob_port)
        if not devices:
            await async_run_discover(self._ob_host, self._ob_port)
        # Force getButtons so input-module buttons (and their rooms) show up.
        await async_refresh_module_metadata(self._ob_host, self._ob_port)
        self._ob_devices = await async_fetch_devices(self._ob_host, self._ob_port)
        self._ob_buttons = await async_fetch_button_config(
            self._ob_host, self._ob_port
        )

    async def async_step_ob_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Map gateway room names to Home Assistant areas (creates missing areas)."""
        rooms = collect_unique_rooms(self._ob_devices)
        self._ob_rooms = rooms
        if not rooms:
            return await self.async_step_ob_entities()

        areas = ar.async_get(self.hass)
        if user_input is not None:
            mappings: dict[str, str] = {}
            for room in rooms:
                area_id = user_input.get(room, "") or ""
                if not area_id:
                    existing = areas.async_get_area_by_name(room)
                    area_id = existing.id if existing else areas.async_create(room).id
                mappings[room] = area_id
            self._ob_room_mappings = mappings
            return await self.async_step_ob_entities()

        # Key fields by room name so HA renders the room as the field label,
        # and preselect a same-named existing area.
        schema: dict[Any, Any] = {}
        for room in rooms:
            existing = areas.async_get_area_by_name(room)
            schema[vol.Optional(room, default=existing.id if existing else "")] = (
                selector.AreaSelector()
            )
        return self.async_show_form(
            step_id="ob_rooms",
            data_schema=vol.Schema(schema),
            description_placeholders={"room_count": str(len(rooms))},
        )

    async def async_step_ob_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Read-only overview of the entities that will be added."""
        if user_input is not None:
            return await self.async_step_ob_buttons()
        return self.async_show_form(
            step_id="ob_entities",
            data_schema=vol.Schema({}),
            description_placeholders=self._entities_overview_placeholders(),
        )

    def _entities_overview_placeholders(self) -> dict[str, str]:
        by_room: dict[str, list[str]] = {}
        light_count = switch_count = button_count = 0
        for dev in self._ob_devices:
            semantic = dev.get("semantic_type")
            name = str(dev.get("name") or dev.get("id") or "")
            room = str(dev.get("room") or "—")
            if semantic == "button":
                button_count += 1
            elif semantic == "switch":
                switch_count += 1
            else:
                light_count += 1
            by_room.setdefault(room, []).append(name)
        lines = [
            f"**{room}** ({len(by_room[room])}): {', '.join(sorted(by_room[room]))}"
            for room in sorted(by_room)
        ]
        return {
            "light_count": str(light_count),
            "switch_count": str(switch_count),
            "button_count": str(button_count),
            "total_count": str(len(self._ob_devices)),
            "entities": "\n".join(lines) or "—",
        }

    async def async_step_ob_buttons(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm import of the input module's existing button configuration."""
        parsed = parse_buttons(self._ob_buttons)
        if not parsed:
            self._ob_import_buttons = False
            return await self._ob_finish()
        if user_input is not None:
            self._ob_import_buttons = bool(user_input.get("import_buttons", True))
            return await self._ob_finish()
        summary = summarise_for_wizard(parsed)
        return self.async_show_form(
            step_id="ob_buttons",
            data_schema=vol.Schema(
                {vol.Optional("import_buttons", default=True): bool}
            ),
            description_placeholders={
                "button_count": str(summary["button_count"]),
                "actionable_count": str(summary["actionable_count"]),
                "warning_count": str(summary["warning_count"]),
            },
        )

    async def _ob_finish(self) -> ConfigFlowResult:
        options: dict[str, Any] = {CONF_IMPORT_BUTTONS: self._ob_import_buttons}
        if self._ob_room_mappings:
            options[CONF_ROOM_MAPPINGS] = self._ob_room_mappings
        return self.async_create_entry(
            title=self._ob_title,
            data={
                CONF_HOST: self._ob_host,
                CONF_PORT: self._ob_port,
                CONF_ONBOARDING_COMPLETED: True,
            },
            options=options,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler.

        Must be defined on the ``ConfigFlow`` subclass — HA looks up
        options flow via ``handler.async_get_options_flow(entry)`` on
        the class that owns the domain, and falls back to
        ``data_entry_flow.UnknownHandler`` when only a module-level
        function is provided.

        In HA 2026.6+ the flow manager injects the config entry id
        through ``self.handler`` after construction; the handler class
        reads the entry via the read-only ``OptionsFlow.config_entry``
        property. We therefore do not pass ``config_entry`` to the
        handler's constructor.
        """
        from .options_flow import IPBuildingOptionsFlowHandler

        return IPBuildingOptionsFlowHandler()
