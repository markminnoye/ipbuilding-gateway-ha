"""Discovery sweep button for the IPBuilding Gateway integration.

Exposes a single HA ``ButtonEntity`` that triggers a forced
``POST /api/v1/discover`` on the gateway. Lives in its own
``button.py`` so the event entities (see ``event.py``) are registered
under the ``event`` platform, not the ``button`` one — HA Core
derives the entity-domain from the source file name and the
``PLATFORMS`` list in ``__init__.py``.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator
from .hub import gateway_device_info


class IPBuildingDiscoverButton(ButtonEntity):
    """Trigger a forced discovery sweep on the gateway."""

    _attr_has_entity_name = True
    _attr_name = "Run discovery sweep"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "discover_sweep"
    _attr_icon = "mdi:radar"

    def __init__(
        self, entry: ConfigEntry, coordinator: IPBuildingCoordinator
    ) -> None:
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
    """Set up the discovery button for the gateway."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IPBuildingDiscoverButton(entry, coordinator)])
