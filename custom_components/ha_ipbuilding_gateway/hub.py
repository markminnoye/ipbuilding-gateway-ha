"""Tier-1 IPBuilding Gateway hub device helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import IPBuildingCoordinator


def gateway_device_info(entry: ConfigEntry, coordinator: IPBuildingCoordinator) -> DeviceInfo:
    """Device registry entry for the gateway hub (Tier 1).

    Identifiers use ``entry.entry_id`` (HA's config-entry UUID) so multiple
    gateway installations remain independent. ``model`` is the standalone
    gateway string; a follow-up issue can add Supervisor add-on detection
    to switch this to "IPBuilding Gateway HA Add-on" in that case.
    """
    status = coordinator.gateway_status
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="IPBuilding Gateway",
        manufacturer="IPBuilding",
        model="IPBuilding Gateway Software",
        sw_version=status.get("version"),
        configuration_url=f"http://{coordinator.api_host}:{coordinator.api_port}/",
    )
