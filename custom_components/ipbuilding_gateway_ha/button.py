"""Button entity platform for IPBuilding Open.

Exposes physical buttons on IP1100PoE modules as HA EventEntity
instances. Each button press from the gateway triggers a
`button_pressed` event in Home Assistant.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator
from .entity import apply_active_registry_defaults, build_channel_device_info
from .hub import gateway_device_info

log = logging.getLogger(__name__)

_BUTTON_EVENT_TYPES = ["press"]


class IPBuildingEventButton(EventEntity):
    """A hardware button exposed as a Home Assistant EventEntity.

    Fires ``ipbuilding_gateway_ha.button_pressed`` events when the gateway
    receives a button press from the IP1100PoE.
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
            action = data.get("action", "press")
            if action != "press":
                return
            event_data = {"hardware_id": self._hardware_id, "action": action}
            self.async_trigger_event("press", event_data)
            self.hass.bus.async_fire(
                f"{DOMAIN}.button_pressed",
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