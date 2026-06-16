"""Switch entity platform for IPBuilding Open.

Exposes relay/dimmer channels with semantic_type in (switch, plug, fan)
as HA switch entities.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SEMANTIC_TYPE_FAN, SEMANTIC_TYPE_PLUG, SEMANTIC_TYPE_SWITCH
from .coordinator import IPBuildingCoordinator
from .entity import apply_active_registry_defaults, build_channel_device_info, entity_icon

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