"""Room-to-area mapping helpers for the onboarding wizard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import area_registry as ar, device_registry as dr

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import IPBuildingCoordinator


def collect_unique_rooms(devices: list[dict[str, Any]]) -> list[str]:
    """Return sorted unique non-empty ``room`` values from gateway devices."""
    rooms: set[str] = set()
    for device in devices:
        room = device.get("room")
        if room and str(room).strip():
            rooms.add(str(room).strip())
    return sorted(rooms)


def build_room_device_index(devices: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group devices by their ``room`` field."""
    index: dict[str, list[dict[str, Any]]] = {}
    for device in devices:
        room = device.get("room")
        if not room or not str(room).strip():
            continue
        key = str(room).strip()
        index.setdefault(key, []).append(device)
    return index


def apply_room_mappings(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: IPBuildingCoordinator,
    mappings: dict[str, str],
) -> None:
    """Assign HA areas to channel/button devices from onboarding mappings.

    ``mappings`` maps gateway room name → HA area id. When the area id is
    empty, an area is created with the same name as the gateway room.
    Existing ``area_id`` values on devices are never overwritten.
    """
    if not mappings:
        return

    areas = ar.async_get(hass)
    devices = dr.async_get(hass)
    index = build_room_device_index(coordinator.devices_snapshot())

    for room_name, area_id in mappings.items():
        if not room_name:
            continue
        if not area_id:
            existing = areas.async_get_area_by_name(room_name)
            if existing is None:
                area = areas.async_create(room_name)
                area_id = area.id
            else:
                area_id = existing.id
        else:
            area = areas.async_get_area(area_id)
            if area is None:
                continue

        for device in index.get(room_name, []):
            dev_id = device.get("id")
            if not dev_id:
                continue
            device_entry = devices.async_get_device(identifiers={(DOMAIN, dev_id)})
            if device_entry is None or device_entry.area_id is not None:
                continue
            devices.async_update_device(device_entry.id, area_id=area_id)
