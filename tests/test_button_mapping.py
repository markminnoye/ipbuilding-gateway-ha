"""Tests for button_mapping helpers — parsing getButtons and outType normalisation."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"

if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    _ha_const = types.ModuleType("homeassistant.const")
    _ha_const.CONF_HOST = "host"
    _ha_const.CONF_PORT = "port"
    sys.modules["homeassistant.const"] = _ha_const

pkg = types.ModuleType("ha_ipbuilding_gateway")
pkg.__path__ = [str(_COMP)]
sys.modules["ha_ipbuilding_gateway"] = pkg

for name in ("const", "button_mapping"):
    spec = importlib.util.spec_from_file_location(
        f"ha_ipbuilding_gateway.{name}", _COMP / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"ha_ipbuilding_gateway.{name}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

button_mapping = sys.modules["ha_ipbuilding_gateway.button_mapping"]


# ---------------------------------------------------------------------------
# outType normalisation
# ---------------------------------------------------------------------------


def test_normalise_out_type_passes_through_strings() -> None:
    assert button_mapping.normalise_out_type("relay") == "relay"
    assert button_mapping.normalise_out_type("dimmer") == "dimmer"
    assert button_mapping.normalise_out_type("motion") == "motion"
    assert button_mapping.normalise_out_type(None) == "none"
    assert button_mapping.normalise_out_type("") == "none"


def test_normalise_out_type_maps_legacy_numerics() -> None:
    assert button_mapping.normalise_out_type(0) == "relay"
    assert button_mapping.normalise_out_type(1) == "dimmer"
    assert button_mapping.normalise_out_type(160) == "special"
    assert button_mapping.normalise_out_type(255) == "none"


def test_normalise_out_type_flags_unknown_values() -> None:
    assert button_mapping.normalise_out_type(99).startswith("unknown(")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_buttons_string_outType() -> None:
    raw = [
        {
            "id": "2D2F8185190000DF",
            "descr": "Keuken knop 1",
            "gr": "Keuken",
            "func1": {"ip": "30", "ch": 0, "outType": "relay", "action": "on"},
            "func2": {
                "ip": "40",
                "ch": 1,
                "outType": "dimmer",
                "action": "dim",
            },
        }
    ]
    parsed = button_mapping.parse_buttons(raw)
    assert len(parsed) == 1
    assert parsed[0].hardware_id == "2d2f8185190000df"
    assert parsed[0].name == "Keuken knop 1"
    assert parsed[0].room == "Keuken"
    assert len(parsed[0].actions) == 2
    slots = {a.slot for a in parsed[0].actions}
    assert slots == {"press", "long_press"}
    for a in parsed[0].actions:
        assert a.warning is None


def test_parse_buttons_numeric_outType() -> None:
    raw = [
        {
            "id": "2DABCDEF12345678",
            "descr": "Special",
            "gr": "",
            "func1": {"ip": 30, "ch": 12, "outType": 0, "action": "on"},
        }
    ]
    parsed = button_mapping.parse_buttons(raw)
    assert len(parsed) == 1
    assert parsed[0].actions[0].out_type == "relay"
    assert parsed[0].actions[0].target_ip_last_octet == 30


def test_parse_buttons_warns_on_missing_ip() -> None:
    raw = [
        {
            "id": "2D2F8185190000DF",
            "descr": "X",
            "gr": "Y",
            "func1": {"outType": "relay", "action": "on"},
        }
    ]
    parsed = button_mapping.parse_buttons(raw)
    assert parsed[0].actions[0].warning


def test_parse_buttons_skips_entries_without_id() -> None:
    raw = [{"descr": "orphan"}]
    assert button_mapping.parse_buttons(raw) == []


def test_parse_buttons_release_action() -> None:
    raw = [
        {
            "id": "2D2F8185190000DF",
            "descr": "Dim",
            "gr": "Keuken",
            "release": {"ip": "40", "ch": 0, "outType": "dimmer", "action": "off"},
        }
    ]
    parsed = button_mapping.parse_buttons(raw)
    assert len(parsed) == 1
    assert [a.slot for a in parsed[0].actions] == ["release"]


# ---------------------------------------------------------------------------
# Module IP resolution
# ---------------------------------------------------------------------------


def test_resolve_module_ip_by_last_octet() -> None:
    modules = {
        "00:24:77:AA:BB:01": {"ip": "10.10.1.30", "type": "relay"},
        "00:24:77:AA:BB:02": {"ip": "10.10.1.40", "type": "dimmer"},
    }
    assert button_mapping.resolve_module_ip(modules, 30) == "10.10.1.30"
    assert button_mapping.resolve_module_ip(modules, 40) == "10.10.1.40"
    assert button_mapping.resolve_module_ip(modules, 99) is None


def test_resolve_module_ip_accepts_list() -> None:
    modules = [
        {"ip": "10.10.1.30"},
        {"ip": "10.10.1.50"},
    ]
    assert button_mapping.resolve_module_ip(modules, 50) == "10.10.1.50"


def test_build_device_id_validates_module_ip_prefix() -> None:
    build_device_id = button_mapping.build_device_id

    # Valid: ip last-octet matches module IP.
    assert build_device_id("10.10.1.30", 30, 0) == "10.10.1.30-0"
    # Mismatched last octet: rejected.
    assert build_device_id("10.10.1.30", 40, 0) is None
    # Wrong subnet: rejected.
    assert build_device_id("192.168.1.30", 30, 0) is None
    # Missing pieces: rejected.
    assert build_device_id(None, 30, 0) is None
    assert build_device_id("10.10.1.30", None, 0) is None
    assert build_device_id("10.10.1.30", 0, None) is None
