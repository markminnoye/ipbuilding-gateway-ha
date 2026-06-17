"""Button entity platform for IPBuilding Open.

Exposes physical buttons on IP1100PoE modules as HA EventEntity
instances. Each press/long_press/release from the gateway is routed to
the matching ``event_type`` on the entity and to a typed bus event
(``ipbuilding_gateway_ha.button_pressed`` / ``button_long_pressed`` /
``button_released``) so automations and blueprints can react to
multi-stage button interactions.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator
from .entity import apply_active_registry_defaults, build_channel_device_info
from .hub import gateway_device_info

log = logging.getLogger(__name__)

# Event types exposed on the EventEntity. ``press`` is a fresh press, ``long_press``
# fires when the gateway threshold is reached while the button is still held, and
# ``release`` fires when the button is let go. ``release`` arrives even on short
# presses so blueprints can use it for direction-flip logic.
_BUTTON_EVENT_TYPES = ["press", "long_press", "release"]

# Map action -> bus event suffix. Keep the legacy ``button_pressed`` name for
# backward compatibility with automations written against earlier companion
# versions.
_ACTION_TO_BUS_EVENT: dict[str, str] = {
    "press": "button_pressed",
    "long_press": "button_long_pressed",
    "release": "button_released",
}


class IPBuildingEventButton(EventEntity):
    """A hardware button exposed as a Home Assistant EventEntity.

    Fires the matching bus event for every action:
    - ``ipbuilding_gateway_ha.button_pressed``
    - ``ipbuilding_gateway_ha.button_long_pressed``
    - ``ipbuilding_gateway_ha.button_released``

    All three carry ``{"hardware_id": "<id>", "action": "<press|long_press|release>"}``.
    """

    _attr_has_entity_name = True
    _attr_event_types = _BUTTON_EVENT_TYPES
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: IPBuildingCoordinator,
    ) -> None:
        hardware_id = device["id"]
        name = device.get("name")
        self._device = device
        self._hardware_id = hardware_id
        self._coordinator = coordinator
        self._attr_unique_id = f"event_{hardware_id}"
        module = coordinator.module_for_channel(device)
        self._attr_device_info = build_channel_device_info(device, module)
        self.entity_description = EventEntityDescription(
            key=hardware_id,
            name=name or f"Button {hardware_id}",
            event_types=_BUTTON_EVENT_TYPES,
            device_class=EventDeviceClass.BUTTON,
            translation_key="button",
            translation_placeholders={"hardware_id": hardware_id},
        )
        self._on_button_event: Callable[[dict], None] | None = None
        apply_active_registry_defaults(self, device)

    async def async_added_to_hass(self) -> None:
        """Register to receive button events from the coordinator."""
        listener_key = f"button:{self._hardware_id}"

        @callback
        def _handle_button_event(data: dict) -> None:
            action = (data.get("action") or "press").lower()
            if action not in _BUTTON_EVENT_TYPES:
                log.debug(
                    "Ignoring unknown button action %r for %s",
                    action,
                    self._hardware_id,
                )
                return
            event_data = {
                "hardware_id": self._hardware_id,
                "action": action,
            }
            self._trigger_event(action, event_data)
            self.async_write_ha_state()
            bus_suffix = _ACTION_TO_BUS_EVENT.get(action)
            if bus_suffix:
                self.hass.bus.async_fire(
                    f"{DOMAIN}.{bus_suffix}",
                    event_data,
                )

        self._on_button_event = _handle_button_event
        self._coordinator.register_entity(listener_key, _handle_button_event)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the button event listener."""
        if self._on_button_event is not None:
            self._coordinator.unregister_entity(
                f"button:{self._hardware_id}", self._on_button_event
            )


class IPBuildingDiscoverButton(ButtonEntity):
    """Trigger a forced discovery sweep on the gateway."""

    _attr_has_entity_name = True
    _attr_name = "Run discovery sweep"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "discover_sweep"
    _attr_icon = "mdi:radar"

    def __init__(self, entry: ConfigEntry, coordinator: IPBuildingCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_discover"
        self._attr_device_info = gateway_device_info(entry, coordinator)

    async def async_press(self) -> None:
        """Run POST /api/v1/discover on the gateway."""
        await self._coordinator.async_trigger_discover()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button/event entities from a config entry.

    Creates an IPBuildingEventButton for each entry in devices.json that
    represents a physical button (type=input on IP1100PoE).
    """
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    # ``devices_snapshot()`` is the canonical read API; it works on every
    # code path (REST fallback list, REST cached dict, WebSocket snapshot).
    devices = coordinator.devices_snapshot()

    async_add_entities([IPBuildingDiscoverButton(entry, coordinator)])

    seen_unique_ids: set[str] = set()

    def _add(devices_to_add: list[dict]) -> None:
        new_buttons = []
        for device in devices_to_add:
            if device.get("device_type") != "input":
                continue
            hardware_id = device.get("id")
            if not hardware_id:
                continue
            button = IPBuildingEventButton(device, coordinator)
            if button._attr_unique_id in seen_unique_ids:
                continue
            seen_unique_ids.add(button._attr_unique_id)
            new_buttons.append(button)
        for button in new_buttons:
            coordinator.track_platform_entity("button", button._hardware_id, button)
        if new_buttons:
            async_add_entities(new_buttons)

    _add(devices)
    coordinator.register_platform("button", _add)