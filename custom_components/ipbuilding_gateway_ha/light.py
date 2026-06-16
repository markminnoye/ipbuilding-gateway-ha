"""Light entity platform for IPBuilding Open.

Exposes relay channels as ONOFF lights and dimmer channels as
BRIGHTNESS lights based on the semantic_type in devices.json.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SEMANTIC_TYPE_LIGHT
from .coordinator import IPBuildingCoordinator
from .entity import apply_active_registry_defaults, build_channel_device_info, entity_icon

log = logging.getLogger(__name__)

# Key in devices.json that indicates a light
_LIGHT_SEMANTIC_TYPES = {SEMANTIC_TYPE_LIGHT}


class IPBuildingLight(LightEntity):
    """A light entity backed by the IPBuilding Gateway via WebSocket."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.ONOFF}
    _attr_is_on: bool | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: IPBuildingCoordinator,
    ) -> None:
        self._device = device
        self._coordinator = coordinator
        self._entity_id = device["id"]
        self._semantic_type: str = device.get("semantic_type", "light")
        # Dimmer modules use DIM commands on the gateway; relays use ON/OFF.
        self._is_dimmer: bool = device.get("device_type") == "dimmer"
        self._attr_unique_id = device["id"]
        # 3-tier device tree: channel rolls up to its parent module via
        # via_device. Module-device is created implicitly by HA on first
        # reference. The module's product model (e.g. "IP0200PoE") takes
        # priority over the channel's semantic_type (e.g. "light").
        module = coordinator.module_for_channel(device)
        self._attr_device_info = build_channel_device_info(device, module)
        # Entity description: name=None + has_entity_name=True makes HA derive
        # the displayed name from the device name in the device registry.
        # ``original_icon`` was removed from ``EntityDescription`` in
        # Home Assistant 2026.3 — set the icon as a class attribute instead.
        self.entity_description = LightEntityDescription(
            key=device["id"],
            name=None,
        )
        self._attr_icon = entity_icon(device)
        # Store the update callback so the entity can be notified
        self._on_update: Callable[[dict], None] | None = None
        apply_active_registry_defaults(self, device)

    async def async_added_to_hass(self) -> None:
        """Register for updates from the coordinator."""
        # Set initial state from coordinator cache
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
        is_on = state.get("state") in ("on", "ON")
        self._attr_is_on = is_on

        # Dimmer-specific: extract brightness level when the device is a dimmer module.
        if self._is_dimmer and "level" in state:
            level = state.get("level")
            if level is not None:
                self._attr_brightness = round(255 * level / 100)
                # HA 2026.3 enforces strict supported_color_modes validation:
                # BRIGHTNESS and ONOFF cannot both be present in the set.
                # Dimmer modules support BRIGHTNESS only; ONOFF is implied
                # by brightness=0 and is exposed via the brightness attribute.
                self._attr_color_mode = ColorMode.BRIGHTNESS
                self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if self._is_dimmer:
            brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness)
            if not brightness:
                level = 100
            else:
                level = max(1, round(brightness * 100 / 255))
            await self._coordinator.async_send_command(
                self._entity_id, "DIM", level
            )
            return
        await self._coordinator.async_send_command(self._entity_id, "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        if self._is_dimmer:
            await self._coordinator.async_send_command(self._entity_id, "DIM", 0)
            return
        await self._coordinator.async_send_command(self._entity_id, "OFF")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities from a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    # ``devices_snapshot()`` returns a list and works on every code path:
    # REST fallback (list before v0.3.8), the dict cached after REST, and
    # the WebSocket snapshot. Reading ``coordinator.data`` directly would
    # diverge between those paths and silently create zero entities on
    # first refresh.
    devices = coordinator.devices_snapshot()

    # Track unique_ids we've already added to HA. Re-firing ``async_add_entities``
    # with the same unique_id makes Home Assistant log
    # "does not generate unique IDs" and silently drop the new entity — which
    # happens whenever a previously-inactive channel flips back to active.
    seen_unique_ids: set[str] = set()

    def _add(devices_to_add: list[dict]) -> None:
        new_lights = []
        for device in devices_to_add:
            if device.get("semantic_type") not in _LIGHT_SEMANTIC_TYPES:
                continue
            light = IPBuildingLight(device, coordinator)
            if light._attr_unique_id in seen_unique_ids:
                continue
            seen_unique_ids.add(light._attr_unique_id)
            new_lights.append(light)
        for light in new_lights:
            coordinator.track_platform_entity("light", light._entity_id, light)
        if new_lights:
            async_add_entities(new_lights)

    # Initial setup: also through _add so a subsequent flip-to-active
    # for one of these devices doesn't try to recreate them.
    _add(devices)

    coordinator.register_platform("light", _add)