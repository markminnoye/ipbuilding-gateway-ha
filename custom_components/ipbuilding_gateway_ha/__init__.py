"""IPBuilding Open integration for Home Assistant.

Connects to the ipbuilding-gateway via WebSocket to expose relay, dimmer,
and button devices as HA entities.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
)

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator
from .entity import module_device_name
from .hub import gateway_device_info

log = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPBuilding Open from a config entry."""
    coordinator = IPBuildingCoordinator(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()
    # Register the Tier-1 gateway device and the Tier-2 field-module devices
    # before the platforms create entities. HA does NOT auto-create the
    # via_device parent: a hub that fronts other devices must register them
    # explicitly (see HA dev docs, device registry "Manual registration").
    _register_hub_devices(hass, entry, coordinator)
    await coordinator.start()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["light", "switch", "button", "sensor"],
    )
    # Now that channel entities have been registered, link them to the
    # matching HA area by name when the gateway provided a ``room`` for
    # the channel. Devices without a match still carry ``suggested_area``
    # from :func:`build_channel_device_info`, so the onboarding "Naam
    # geven en toewijzen" screen offers the area as a preselect option
    # even when no matching HA area exists yet.
    _suggest_channel_areas(hass, entry, coordinator)
    return True


def _register_hub_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Register the gateway (Tier 1) and per-module (Tier 2) devices.

    Channels reference their module via ``via_device``; the module references
    the gateway via ``via_device``. HA only materialises a device when it is
    registered explicitly or carried by an entity's own ``identifiers`` — the
    via_device link alone does not create the parent. We therefore register
    the gateway and every known module here so the 3-tier tree is complete
    even for modules whose channels are all inactive.
    """
    registry = dr.async_get(hass)

    # Tier 1 — gateway hub device.
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **gateway_device_info(entry, coordinator),
    )

    # Tier 2 — one device per physical field module, rolled up to the gateway.
    for module in coordinator.modules.values():
        mac = module.get("id")
        if not mac:
            continue
        kwargs = {
            "config_entry_id": entry.entry_id,
            "identifiers": {(DOMAIN, mac)},
            "name": module_device_name(module),
            "manufacturer": "IPBuilding",
            "model": module.get("model") or module.get("type"),
            "via_device": (DOMAIN, entry.entry_id),
        }
        firmware = module.get("firmware")
        if firmware:
            kwargs["sw_version"] = firmware
        registry.async_get_or_create(**kwargs)


def _suggest_channel_areas(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Link each channel device to an HA area when ``room`` matches an existing one.

    Only updates a device that does not already have an ``area_id`` — we
    never overwrite an operator's manual area assignment.
    """
    areas = ar.async_get(hass)
    devices = dr.async_get(hass)

    snapshot = coordinator.data
    if not isinstance(snapshot, dict):
        return

    for device in snapshot.values():
        room = device.get("room")
        if not room:
            continue
        area = areas.async_get_area_by_name(room)
        if area is None:
            continue
        device_entry = devices.async_get_device(identifiers={(DOMAIN, device["id"])})
        if device_entry is None or device_entry.area_id is not None:
            continue
        devices.async_update_device(device_entry.id, area_id=area.id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.stop()
    # Home Assistant 2026.x removed the variadic ``platforms`` argument from
    # ``async_forward_entry_unload``; use ``async_unload_platforms`` instead.
    return await hass.config_entries.async_unload_platforms(
        entry,
        ("light", "switch", "button", "sensor"),
    )


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)
