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

from .blueprints import async_install_packaged_blueprints
from .const import DOMAIN
from .coordinator import IPBuildingCoordinator
from .entity import module_device_model, module_device_name
from .hub import gateway_device_info

log = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPBuilding Open from a config entry."""
    await async_install_packaged_blueprints(hass)
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
        ["light", "switch", "event", "button", "sensor"],
    )
    # The first WS snapshot schedules a debounced diff before platforms exist.
    # Seed known devices now so that diff pass does not recreate every entity.
    coordinator.seed_known_devices()
    # Now that channel entities have been registered, link them to the
    # matching HA area by name when the gateway provided a ``room`` for
    # the channel. Devices without a match still carry ``suggested_area``
    # from :func:`build_channel_device_info`, so the onboarding "Naam
    # geven en toewijzen" screen offers the area as a preselect option
    # even when no matching HA area exists yet.
    _suggest_channel_areas(hass, entry, coordinator)
    # Run a one-shot discovery sweep if the gateway has nothing yet. The
    # flag lives on hass.data so a subsequent async_reload (which resets
    # the in-memory cache) does not re-enter the bootstrap and form a
    # discover → reload → discover loop. Set the flag BEFORE scheduling
    # the task so the second setup_entry that the reload triggers sees
    # it and skips.
    bootstrap_done = hass.data[DOMAIN].get(f"{entry.entry_id}_bootstrap_done")
    if not bootstrap_done and not coordinator.devices_snapshot():
        hass.data[DOMAIN][f"{entry.entry_id}_bootstrap_done"] = True
        entry.async_on_unload(
            hass.async_create_task(_bootstrap_devices(hass, entry.entry_id))
        )
    return True


async def _bootstrap_devices(hass: HomeAssistant, entry_id: str) -> None:
    """Populate entities when the gateway has no devices.json yet.

    Fresh add-on installs fall back to env module IPs for UDP polling but
    expose an empty ``/api/v1/devices`` until discovery writes devices.json.
    Trigger a forced sweep and reload the config entry so channel entities
    appear without a manual integration reload.
    """
    coordinator: IPBuildingCoordinator | None = hass.data.get(DOMAIN, {}).get(entry_id)
    entry = hass.config_entries.async_get_entry(entry_id)
    if coordinator is None or entry is None:
        return
    if coordinator.devices_snapshot():
        return

    log.info("No gateway devices yet; running discovery sweep")
    await coordinator.async_trigger_discover()
    if coordinator.devices_snapshot():
        await hass.config_entries.async_reload(entry_id)


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
            "model": module_device_model(module) or module.get("type"),
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

    # ``devices_snapshot()`` returns a list and works regardless of whether
    # the REST fallback or the WebSocket snapshot populated the cache.
    for device in coordinator.devices_snapshot():
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
        ("light", "switch", "event", "button", "sensor"),
    )


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)
