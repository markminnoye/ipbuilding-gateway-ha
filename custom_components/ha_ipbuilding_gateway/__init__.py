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

from .automation_store import async_write_button_automations
from .blueprints import async_install_packaged_blueprints
from .button_automation_builder import collect_automations
from .button_mapping import SLOT_LONG_PRESS, SLOT_PRESS, SLOT_RELEASE, parse_buttons
from .const import (
    CONF_BUTTON_AUTOMATIONS,
    CONF_IMPORT_BUTTONS,
    CONF_ROOM_MAPPINGS,
    DOMAIN,
)
from .coordinator import IPBuildingCoordinator
from .entity import module_device_model, module_device_name
from .hub import gateway_device_info
from .room_mapping import apply_room_mappings
from .target_resolver import build_channel_entity_index, build_channel_name_index

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
    # Apply the choices the coupling wizard collected (room→area mapping is
    # idempotent — it never overwrites a user-set area). The wizard now runs
    # inside the config flow, so there is no auto-launched options flow here.
    await _apply_onboarding_results(hass, entry, coordinator)
    return True


async def _apply_onboarding_results(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Apply the room mapping and (optionally) import button automations.

    Runs every setup. ``apply_room_mappings`` only assigns areas to devices
    that have none, so it is safe to re-run and it also catches button devices
    that only appeared after a ``getButtons`` refresh. Button automations are
    built once (when ``CONF_IMPORT_BUTTONS`` is set and they are not stored
    yet), since that step needs the channel entities created above.
    """
    mappings = entry.options.get(CONF_ROOM_MAPPINGS) or {}
    if mappings:
        apply_room_mappings(hass, entry, coordinator, dict(mappings))

    if not entry.options.get(CONF_IMPORT_BUTTONS):
        return
    if entry.options.get(CONF_BUTTON_AUTOMATIONS):
        return  # already imported
    await _import_button_automations(hass, entry, coordinator)


async def _import_button_automations(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: IPBuildingCoordinator
) -> None:
    """Build button automations from the input module's existing mapping."""
    try:
        parsed = parse_buttons(await coordinator.async_fetch_button_config())
    except Exception:
        log.exception("Failed to read button config for import")
        return
    if not parsed:
        return

    snapshot = coordinator.devices_snapshot()
    channel_index = build_channel_entity_index(hass, snapshot)
    name_index = build_channel_name_index(snapshot)

    # Resolve every configured slot (press/long/release) to its HA target so
    # the input module's mapping is taken over wholesale.
    targets: dict[tuple[str, str], str] = {}
    target_names: dict[tuple[str, str], str] = {}
    for button in parsed:
        for action in button.actions:
            if action.warning:
                continue
            if action.target_ip_last_octet is None or action.target_channel is None:
                continue
            key = (action.target_ip_last_octet, action.target_channel)
            entity_id = channel_index.get(key)
            if not entity_id:
                continue
            targets[(button.hardware_id, action.slot)] = entity_id
            if key in name_index:
                target_names[(button.hardware_id, action.slot)] = name_index[key]

    device_registry = dr.async_get(hass)
    hardware_ids = {p.hardware_id for p in parsed}
    button_device_ids: dict[str, str] = {}
    for device in device_registry.devices.values():
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier in hardware_ids:
                button_device_ids[identifier] = device.id

    automations = collect_automations(
        parsed,
        button_device_ids=button_device_ids,
        target_entity_ids=targets,
        target_names=target_names,
        include_slots=(SLOT_PRESS, SLOT_LONG_PRESS, SLOT_RELEASE),
    )
    if not automations:
        return

    # Write them as real, editable HA automations and reload.
    await async_write_button_automations(hass, automations)

    # Record what we generated so a later setup/reload does not re-import.
    options = dict(entry.options)
    options[CONF_BUTTON_AUTOMATIONS] = {
        "targets": {f"{k[0]}|{k[1]}": v for k, v in targets.items()},
        "automations": automations,
    }
    hass.config_entries.async_update_entry(entry, options=options)


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
    """Handle config entry updates.

    The onboarding wizard (an OptionsFlow) writes entry options/data several
    times — room mappings, button automations, the completion flag. Reloading
    the integration mid-wizard tears down ``hass.data[DOMAIN][entry_id]`` under
    the running flow, so the coordinator lookup raises ``KeyError(entry_id)``
    and the wizard breaks. Skip the reload while an options flow for this entry
    is in progress; room areas are written straight to the device registry, so
    they take effect without a reload. The flow's final options write (after it
    is no longer in progress) still triggers one clean reload.
    """
    if hass.config_entries.options.async_progress_by_handler(entry.entry_id):
        return
    await hass.config_entries.async_reload(entry.entry_id)
