"""Tests for room_mapping helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"

if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    _ha_const = types.ModuleType("homeassistant.const")
    _ha_const.CONF_HOST = "host"
    _ha_const.CONF_PORT = "port"
    sys.modules["homeassistant.const"] = _ha_const

_ha_helpers = types.ModuleType("homeassistant.helpers")
_ha_helpers.area_registry = types.ModuleType("area_registry")
_ha_helpers.device_registry = types.ModuleType("device_registry")
sys.modules["homeassistant.helpers"] = _ha_helpers
sys.modules["homeassistant.helpers.area_registry"] = _ha_helpers.area_registry
sys.modules["homeassistant.helpers.device_registry"] = _ha_helpers.device_registry

_fake_pkg = types.ModuleType("ha_ipbuilding_gateway")
_fake_pkg.__path__ = [str(_COMP_DIR)]
sys.modules["ha_ipbuilding_gateway"] = _fake_pkg

const_spec = importlib.util.spec_from_file_location(
    "ha_ipbuilding_gateway.const", _COMP_DIR / "const.py"
)
const_mod = importlib.util.module_from_spec(const_spec)
sys.modules["ha_ipbuilding_gateway.const"] = const_mod
const_spec.loader.exec_module(const_mod)  # type: ignore[union-attr]

rm_spec = importlib.util.spec_from_file_location(
    "ha_ipbuilding_gateway.room_mapping", _COMP_DIR / "room_mapping.py"
)
room_mapping = importlib.util.module_from_spec(rm_spec)
sys.modules["ha_ipbuilding_gateway.room_mapping"] = room_mapping
rm_spec.loader.exec_module(room_mapping)  # type: ignore[union-attr]


def test_collect_unique_rooms_sorted_and_deduped() -> None:
    devices = [
        {"id": "a", "room": "Keuken"},
        {"id": "b", "room": "Badkamer"},
        {"id": "c", "room": "Keuken"},
        {"id": "d", "room": ""},
        {"id": "e", "room": "  "},
    ]
    assert room_mapping.collect_unique_rooms(devices) == ["Badkamer", "Keuken"]


def test_build_room_device_index_groups_by_room() -> None:
    devices = [
        {"id": "a", "room": "Keuken"},
        {"id": "b", "room": "Keuken"},
        {"id": "c", "room": "Badkamer"},
    ]
    index = room_mapping.build_room_device_index(devices)
    assert len(index["Keuken"]) == 2
    assert len(index["Badkamer"]) == 1
    assert "Badkamer" in index
