"""Resolve gateway button targets to Home Assistant entity ids.

A button action in ``getButtons`` points at a relay/dimmer channel via
``(target_ip_last_octet, target_channel)``. Both the setup-time automation
builder and the options "re-run wizard" need to turn that into the HA
``entity_id`` of the light/switch backing that channel. Channels are matched on
``module_ip`` + ``channel`` (not the device-id string) so custom device slugs
still resolve.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN


def build_channel_entity_index(
    hass: HomeAssistant, devices: list[dict[str, Any]]
) -> dict[tuple[int, int], str]:
    """Map ``(module IP last octet, channel)`` -> HA entity_id.

    ``devices`` is a coordinator ``devices_snapshot()`` (flat per-channel
    dicts carrying ``module_ip``, ``channel`` and ``id``). Only channels that
    already have a registered entity on this integration's platform appear.
    """
    registry = er.async_get(hass)
    uid_to_entity = {
        ent.unique_id: ent.entity_id
        for ent in registry.entities.values()
        if ent.platform == DOMAIN
    }
    index: dict[tuple[int, int], str] = {}
    for dev in devices:
        module_ip = str(dev.get("module_ip") or "")
        channel = dev.get("channel")
        dev_id = dev.get("id")
        if channel is None or not dev_id or "." not in module_ip:
            continue
        try:
            last_octet = int(module_ip.rsplit(".", 1)[-1])
        except ValueError:
            continue
        entity_id = uid_to_entity.get(dev_id)
        if entity_id:
            index[(last_octet, int(channel))] = entity_id
    return index
