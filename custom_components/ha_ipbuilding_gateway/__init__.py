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
from .const import CONF_ROOM_MAPPING_OFFERED, CONF_ROOM_MAPPINGS, DOMAIN
from .coordinator import IPBuildingCoordinator
from .entity import module_device_model, module_device_name
from .hub import gateway_device_info
from .room_mapping import apply_room_mappings, collect_unique_rooms, should_offer_room_mapping
from .services import async_register_services, async_unregister_services

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
    # Register the hold-to-dim ramp services (dim_start / dim_stop). They go
    # through the same WS command path the light platform already uses; no
    # HTTP fallback — the dimmer must receive the ramp on time.
    async_register_services(hass, coordinator)
    # The first WS snapshot schedules a debounced diff before platforms exist.
    # Seed known devices now so that diff pass does not recreate every entity.
    coordinator.seed_known_devices()
    # Now that channel entities have been registered, link them to the
    # matching HA area by name when the gateway provided a ``room`` for
    # the channel. Devices without a match still carry ``suggested_area``
    # from :func:`build_channel_device_info`, so Home Assistant's native
    # device-assignment UI offers the area as a preselect option even
    # when no matching HA area exists yet. Operators can also map rooms
    # explicitly via the integration options ("Ruimtes koppelen").
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
        # ``async_on_unload`` takes a *callable* to run on unload, not a Task —
        # registering the Task itself made HA call it (``Task() ``) on unload and
        # raise "'_asyncio.Task' object is not callable". Register the task's
        # ``cancel`` so an in-flight bootstrap is cancelled cleanly on unload.
        bootstrap_task = hass.async_create_task(
            _bootstrap_devices(hass, entry.entry_id)
        )
        entry.async_on_unload(bootstrap_task.cancel)
    # Reapply any room→area mapping the operator saved through the
    # options flow. Idempotent — ``apply_room_mappings`` never overwrites
    # a device area the operator assigned manually, and it catches new
    # devices that did not exist when the mapping was first stored.
    _apply_stored_room_mappings(hass, entry, coordinator)
    # Auto-open the room-mapping options flow once the gateway's rooms are
    # known, so the operator does not have to find the tandwiel themselves
    # after adding a gateway. No-op once mapped (or once already offered).
    await _maybe_offer_room_mapping(hass, entry, coordinator)
    return True


async def _maybe_offer_room_mapping(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Auto-launch the options flow's room-mapping step exactly once.

    Sets a ``hass.data`` flag that ``IPBuildingOptionsFlowHandler.async_step_init``
    checks to skip straight to ``async_step_map_rooms`` instead of showing
    the menu. ``CONF_ROOM_MAPPING_OFFERED`` is persisted to ``entry.options``
    after the flow is started (so ``async_progress_by_handler`` already
    sees it as in-progress and ``_async_update_listener`` skips the reload
    that write would otherwise trigger).
    """
    rooms = collect_unique_rooms(coordinator.devices_snapshot())
    if not should_offer_room_mapping(entry.options, rooms):
        return
    hass.data[DOMAIN][f"{entry.entry_id}_auto_room_mapping"] = True
    await hass.config_entries.options.async_init(entry.entry_id)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ROOM_MAPPING_OFFERED: True}
    )


def _apply_stored_room_mappings(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Apply the operator-saved room mapping from ``entry.options``.

    Runs on every setup. ``apply_room_mappings`` only assigns areas to
    devices that have none, so it is safe to re-run on reload.
    """
    mappings = entry.options.get(CONF_ROOM_MAPPINGS) or {}
    if mappings:
        apply_room_mappings(hass, entry, coordinator, dict(mappings))


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
    async_unregister_services(hass)
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
    """Handle config entry updates.

    The options flow writes ``entry.options`` while the flow is still
    running (the operator moves through the room-mapping form). Reloading
    the integration mid-flow tears down ``hass.data[DOMAIN][entry_id]``
    under the running flow and the next lookup raises ``KeyError``. Skip
    the reload while an options flow for this entry is in progress; the
    final options write (after the flow closes) still triggers one clean
    reload.
    """
    if hass.config_entries.options.async_progress_by_handler(entry.entry_id):
        return
    await hass.config_entries.async_reload(entry.entry_id)
