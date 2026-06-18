"""Shared helpers for ha_ipbuilding_gateway entities.

Mirrors the HA-IPBuilding button pattern: channels (and IP1100PoE buttons)
with ``active: false`` in the gateway snapshot are registered in Home
Assistant as **disabled and hidden by default**, so the operator sees them
in Instellingen → Apparaten & entiteiten without them appearing on dashboards
or in automations until enabled.
"""

from __future__ import annotations

import re

from typing import Any

from .const import (
    DEVICE_TYPE_DIMMER,
    DEVICE_TYPE_INPUT,
    DEVICE_TYPE_RELAY,
    DOMAIN,
    SEMANTIC_TYPE_BUTTON,
    SEMANTIC_TYPE_COVER,
    SEMANTIC_TYPE_FAN,
    SEMANTIC_TYPE_LIGHT,
    SEMANTIC_TYPE_PLUG,
    SEMANTIC_TYPE_SWITCH,
)

# Auto-discovery and legacy devices.json use the hardware SKU as ``name``.
_HARDWARE_MODELS = frozenset({"IP0200PoE", "IP0300PoE", "IP1100PoE"})

# Long form: the Tier-2 module device name in the onboarding screen,
# where the suffix makes it explicit that the card represents the
# physical module (not one of its channels).
_MODULE_TYPE_LABELS: dict[str, str] = {
    DEVICE_TYPE_RELAY: "Relay module",
    DEVICE_TYPE_DIMMER: "Dimmer module",
    DEVICE_TYPE_INPUT: "Input module",
}

# Short form: shown as ``model`` on each Tier-3 channel device in
# "Apparaat-info". Compact to keep the per-channel panel readable when
# the install has 16+ channels.
_MODULE_TYPE_LABELS_SHORT: dict[str, str] = {
    DEVICE_TYPE_RELAY: "Relay",
    DEVICE_TYPE_DIMMER: "Dimmer",
    DEVICE_TYPE_INPUT: "Input",
}

# Type → canonical hardware SKU. Mirrors
# ``gateway.discovery._TYPE_TO_MODEL`` so the companion falls back to a
# stable "Apparaat-info" title even when the gateway snapshot is missing
# the factory product label (e.g. older add-on, ARP-only discovery).
_TYPE_TO_MODEL: dict[str, str] = {
    DEVICE_TYPE_RELAY: "IP0200PoE",
    DEVICE_TYPE_DIMMER: "IP0300PoE",
    DEVICE_TYPE_INPUT: "IP1100PoE",
}

_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# Mapping from channel ``semantic_type`` to a Material Design Icon. The
# dimmer-on-light special case is handled in :func:`entity_icon` because
# it depends on the parent module's ``device_type`` as well.
_SEMANTIC_ICONS: dict[str, str] = {
    SEMANTIC_TYPE_LIGHT: "mdi:lightbulb",
    SEMANTIC_TYPE_FAN: "mdi:fan",
    SEMANTIC_TYPE_PLUG: "mdi:power-plug",
    SEMANTIC_TYPE_SWITCH: "mdi:toggle-switch-variant",
    SEMANTIC_TYPE_COVER: "mdi:blinds-horizontal",
    SEMANTIC_TYPE_BUTTON: "mdi:gesture-tap-button",
}


def module_type_label(module_type: str | None) -> str:
    """Return the long module role label (Relay module / Dimmer module / Input module).

    Used as the Tier-2 module device name. Falls back to a generic
    ``IPBuilding module`` for unknown types and to the raw ``module_type``
    string when the type is not one of the three known field modules.
    """
    if not module_type:
        return "IPBuilding module"
    return _MODULE_TYPE_LABELS.get(module_type, module_type)


def module_type_label_short(module_type: str | None) -> str:
    """Return the short module role label (Relay / Dimmer / Input).

    Used as the ``model`` of each Tier-3 channel device in Apparaat-info.
    Falls back to ``module_type_label`` when the type is unknown so the
    operator still sees a meaningful string.
    """
    if not module_type:
        return "IPBuilding module"
    return _MODULE_TYPE_LABELS_SHORT.get(module_type, module_type_label(module_type))


def module_device_model(module: dict[str, Any]) -> str:
    """Return the hardware SKU to display as the module's ``model``.

    Prefers the gateway-provided ``model`` (factory product label, may be
    ``IP200PoE`` for legacy installs). Falls back to the canonical SKU for
    the type so onboarding keeps a stable title even when the gateway
    snapshot is incomplete.
    """
    model = module.get("model")
    if model:
        return model
    return _TYPE_TO_MODEL.get(module.get("type", ""), "")


def _is_placeholder_name(name: str | None, module: dict[str, Any]) -> bool:
    """Return True when ``name`` is an auto-discovery placeholder, not an operator choice."""
    if not name:
        return True
    if name in _HARDWARE_MODELS:
        return True
    if name == module.get("ip"):
        return True
    return bool(_IPV4_RE.match(name))


def module_device_name(module: dict[str, Any]) -> str:
    """Pick the HA device name for a field module.

    Uses the operator-configured ``name`` when it is not the auto-discovery
    hardware default; otherwise falls back to the module role (relay/dimmer/input).
    Auto-discovery placeholders — the module's IP and the bare hardware SKU —
    are treated as defaults so an IP-based name (e.g. ``10.10.1.50``) does
    not leak into the onboarding "Apparaatnaam" field.
    """
    name = module.get("name")
    model = module.get("model")
    if name and name != model and not _is_placeholder_name(name, module):
        return name
    return module_type_label(module.get("type"))


def entity_icon(device: dict[str, Any]) -> str:
    """Return the Material Design Icon for a channel/button/light/switch.

    The dimmer-on-light special case (``mdi:brightness-6``) requires both
    ``semantic_type`` and ``device_type`` to disambiguate a brightness-capable
    channel from a plain relay-driven light.
    """
    semantic = device.get("semantic_type") or SEMANTIC_TYPE_LIGHT
    device_type = device.get("device_type")
    if semantic == SEMANTIC_TYPE_LIGHT and device_type == DEVICE_TYPE_DIMMER:
        return "mdi:brightness-6"
    return _SEMANTIC_ICONS.get(semantic, "mdi:help-circle")


def registry_unique_ids_for_device(device: dict[str, Any]) -> list[str]:
    """Return entity-registry ``unique_id`` values for a gateway device dict.

    Relay/dimmer channels use the bare device id (and ``<id>_power`` for the
    watt sensor). IP1100PoE buttons use ``event_<hardware_id>`` on the
    ``event`` platform.
    """
    dev_id = device.get("id")
    if not dev_id:
        return []
    unique_ids = [dev_id, f"{dev_id}_power"]
    if device.get("device_type") == DEVICE_TYPE_INPUT:
        unique_ids.append(f"event_{dev_id}")
    return unique_ids


def apply_active_registry_defaults(entity: Any, device: dict[str, Any]) -> None:
    """Mark ``entity`` disabled+hidden-by-default if the gateway reports it inactive.

    The companion ``coordinator`` also keeps the registry in sync at runtime
    (see ``coordinator._reconcile_active``), but setting these class-level
    attributes here covers the initial ``async_setup_entry`` path for entities
    that are brand new to the entity registry.
    """
    if not device.get("active", True):
        entity._attr_entity_registry_enabled_default = False
        entity._attr_entity_registry_visible_default = False


def build_module_hub_device_info(module: dict[str, Any]) -> dict[str, Any]:
    """Build device_info for a physical field module (IP0200PoE / IP0300PoE / IP1100PoE).

    Used as the ``via_device`` target for channels that roll up to this module.
    The actual registration happens implicitly when the first channel with
    ``via_device=(DOMAIN, module["id"])`` is added to HA.
    """
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, module["id"])},  # MAC
        "name": module_device_name(module),
        "manufacturer": "IPBuilding",
        "model": module_device_model(module) or module.get("type"),
    }
    firmware = module.get("firmware")
    if firmware:
        info["sw_version"] = firmware
    # The module-device rolls up to the gateway via hub.py's gateway_device_info.
    # We do not set via_device here; HA infers the chain from the per-entity
    # via_device on the channel pointing at (DOMAIN, module["id"]).
    return info


def build_channel_device_info(
    device: dict[str, Any], module: dict[str, Any] | None
) -> dict[str, Any]:
    """Build device_info for a channel/button/light/switch.

    Shows the module role (Relay / Dimmer / Input) as ``model`` so discovery and
    mapping stay readable; the parent module device keeps the hardware SKU.
    The optional ``room`` from ``devices.json`` is forwarded as
    ``suggested_area`` so the onboarding "Naam geven en toewijzen" screen
    preselects the matching HA area when one exists.

    The ``via_device`` field automatically causes HA to create the parent
    module-device in the registry on first reference.
    """
    role = device.get("device_type") or (module or {}).get("type")
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, device["id"])},
        "name": device.get("name", device["id"]),
        "manufacturer": "IPBuilding",
        "model": module_type_label_short(role),
    }
    if room := device.get("room"):
        info["suggested_area"] = room
    if module and module.get("id"):
        info["via_device"] = (DOMAIN, module["id"])  # MAC -> module
    firmware = (module or {}).get("firmware")
    if firmware:
        info["sw_version"] = firmware
    if module and module.get("mac"):
        info["serial_number"] = module["mac"]
    return info
