"""Switch entity platform for IPBuilding Open.

Exposes relay/dimmer channels with semantic_type in (switch, plug, fan)
as HA switch entities.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SEMANTIC_TYPE_FAN, SEMANTIC_TYPE_PLUG, SEMANTIC_TYPE_SWITCH
from .coordinator import IPBuildingCoordinator
from .entity import apply_active_registry_defaults, build_channel_device_info, entity_icon
from .hub import gateway_device_info

log = logging.getLogger(__name__)

_SWITCH_SEMANTIC_TYPES = {SEMANTIC_TYPE_SWITCH, SEMANTIC_TYPE_PLUG, SEMANTIC_TYPE_FAN}


class IPBuildingSwitch(SwitchEntity):
    """A switch entity backed by the IPBuilding Gateway via WebSocket."""

    _attr_has_entity_name = True
    _attr_is_on: bool | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: IPBuildingCoordinator,
    ) -> None:
        self._device = device
        self._coordinator = coordinator
        self._entity_id = device["id"]
        self._is_dimmer: bool = device.get("device_type") == "dimmer"
        self._attr_unique_id = device["id"]
        # 3-tier device tree: channel rolls up to its parent module via
        # via_device. The module's product model (e.g. "IP0200PoE") takes
        # priority over the channel's device_type or semantic_type.
        module = coordinator.module_for_channel(device)
        self._attr_device_info = build_channel_device_info(device, module)
        self._attr_icon = entity_icon(device)
        self._on_update: Callable[[dict], None] | None = None
        apply_active_registry_defaults(self, device)

    async def async_added_to_hass(self) -> None:
        """Register for updates from the coordinator."""
        state = self._coordinator.get_device_state(self._entity_id)
        if state:
            self._update_from_state(state)

        def callback(data: dict) -> None:
            self._update_from_state(data)
            self.async_write_ha_state()

        self._on_update = callback
        self._coordinator.register_entity(self._entity_id, callback)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the update callback."""
        if self._on_update is not None:
            self._coordinator.unregister_entity(self._entity_id, self._on_update)

    def _update_from_state(self, state: dict) -> None:
        """Update entity state from a gateway state_changed message."""
        self._attr_is_on = state.get("state") in ("on", "ON")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._is_dimmer:
            await self._coordinator.async_send_command(self._entity_id, "DIM", 100)
            return
        await self._coordinator.async_send_command(self._entity_id, "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._is_dimmer:
            await self._coordinator.async_send_command(self._entity_id, "DIM", 0)
            return
        await self._coordinator.async_send_command(self._entity_id, "OFF")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Hub-level debug switch: visible on the gateway device, disabled by
    # default so the entity doesn't appear in the dashboard unless the
    # operator explicitly enables it. Mirrors the gateway's
    # `fieldbus.polling_enabled` runtime flag.
    debug_switch = IPBuildingFieldbusPollingSwitch(entry, coordinator)
    async_add_entities([debug_switch])

    # ``devices_snapshot()`` is the canonical read API; it works on every
    # code path (REST fallback list, REST cached dict, WebSocket snapshot).
    devices = coordinator.devices_snapshot()

    seen_unique_ids: set[str] = set()

    def _add(devices_to_add: list[dict]) -> None:
        new_switches = []
        for device in devices_to_add:
            if device.get("semantic_type") not in _SWITCH_SEMANTIC_TYPES:
                continue
            sw = IPBuildingSwitch(device, coordinator)
            if sw._attr_unique_id in seen_unique_ids:
                continue
            seen_unique_ids.add(sw._attr_unique_id)
            new_switches.append(sw)
        for sw in new_switches:
            coordinator.track_platform_entity("switch", sw._entity_id, sw)
        if new_switches:
            async_add_entities(new_switches)

    # Initial setup: also through _add so subsequent flip-to-active
    # devices don't try to recreate already-registered entities.
    _add(devices)

    coordinator.register_platform("switch", _add)


class IPBuildingFieldbusPollingSwitch(SwitchEntity):
    """Debug operator switch that toggles the gateway's UDP/1001 poll loop.

    Lives on the gateway device (Tier 1, alongside the gateway status
    sensor and the discovery-sweep button). Disabled by default in the
    entity registry so it does not show up on the dashboard unless the
    operator explicitly enables it — the warning text in the entity
    description and the runtime ``fieldbus.polling_disabled`` issue in
    the gateway status make the side-effects clear.

    `is_on` mirrors ``coordinator.fieldbus_polling_enabled()`` and is kept
    in sync via the gateway-status listener (same pattern as
    ``IPBuildingGatewayStatusSensor``).
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "fieldbus_polling"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, entry: ConfigEntry, coordinator: IPBuildingCoordinator
    ) -> None:
        self._entry = entry
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_fieldbus_polling"
        self._attr_device_info = gateway_device_info(entry, coordinator)
        self._on_status: Callable[[dict], None] | None = None
        # Seed the icon based on the current cached value so the very
        # first render after restart already shows the right state.
        self._attr_icon = (
            "mdi:lan-connect" if coordinator.fieldbus_polling_enabled() else "mdi:lan-disconnect"
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to gateway status updates."""
        self._attr_is_on = self._coordinator.fieldbus_polling_enabled()
        self._attr_extra_state_attributes = self._build_attributes()

        @callback
        def _on_status(status: dict) -> None:
            self._attr_is_on = self._coordinator.fieldbus_polling_enabled()
            self._attr_icon = (
                "mdi:lan-connect" if self._attr_is_on else "mdi:lan-disconnect"
            )
            self._attr_extra_state_attributes = self._build_attributes()
            self.async_write_ha_state()

        self._on_status = _on_status
        self._coordinator.register_gateway_listener(_on_status)

    async def async_will_remove_from_hass(self) -> None:
        if self._on_status is not None:
            self._coordinator.unregister_gateway_listener(self._on_status)
            self._on_status = None

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        ok = await self._coordinator.async_set_fieldbus_polling(True)
        if not ok:
            # Optimistic UI: keep the previous value, just log; HA will
            # re-render on the next WS gateway_status push.
            log.warning("Failed to re-enable fieldbus polling on the gateway")

    async def async_turn_off(self, **kwargs: Any) -> None:
        ok = await self._coordinator.async_set_fieldbus_polling(False)
        if not ok:
            log.warning("Failed to disable fieldbus polling on the gateway")

    def _build_attributes(self) -> dict[str, Any]:
        """Extra attributes: helps the operator confirm what they're toggling."""
        interval = self._coordinator.fieldbus_poll_interval_s()
        attrs: dict[str, Any] = {
            "warning": (
                "Disabling stops the UDP/1001 keep-alive polls. Input events "
                "may be sent to the IPBox. Re-enable from this switch or "
                "restart the gateway."
            ),
        }
        if interval is not None:
            attrs["poll_interval_s"] = interval
        return attrs