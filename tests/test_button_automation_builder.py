"""Tests for the button_automation_builder."""

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

for name in ("const", "button_mapping", "button_automation_builder"):
    spec = importlib.util.spec_from_file_location(
        f"ha_ipbuilding_gateway.{name}", _COMP / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"ha_ipbuilding_gateway.{name}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

button_automation_builder = sys.modules[
    "ha_ipbuilding_gateway.button_automation_builder"
]
button_mapping = sys.modules["ha_ipbuilding_gateway.button_mapping"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _parsed_button(hardware_id: str = "deadbeef0001", *, slot_action_pairs=()):
    """Build a ParsedButton with ``(slot, out_type, ip, ch, action)`` tuples."""
    actions = []
    for slot, out_type, ip, ch, action in slot_action_pairs:
        actions.append(
            button_mapping.ButtonAction(
                slot=slot,
                raw={},
                out_type=out_type,
                target_ip_last_octet=ip,
                target_channel=ch,
                action=action,
            )
        )
    return button_mapping.ParsedButton(
        hardware_id=hardware_id,
        name="Keuken knop",
        room="Keuken",
        actions=actions,
    )


MODULES = {
    "00:24:77:AA:BB:01": {"ip": "10.10.1.30", "type": "relay"},
    "00:24:77:AA:BB:02": {"ip": "10.10.1.40", "type": "dimmer"},
}


# ---------------------------------------------------------------------------
# Action strategy tests
# ---------------------------------------------------------------------------


def test_relay_on_uses_turn_on() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 0, "on")])
    automation = button_automation_builder.build_automation_for_action(
        parsed,
        "press",
        button_device_id="device-abc",
        target_entity_id="light.keuken",
        modules_snapshot=MODULES,
    )
    assert automation is not None
    assert automation["id"] == "ipb_map_deadbeef0001_press"
    assert automation["action"][0]["service"] == "light.turn_on"
    assert automation["action"][0]["target"]["entity_id"] == "light.keuken"
    assert automation["initial_state"] is False
    assert automation["trigger"][0]["type"] == "pressed"


def test_relay_toggle_uses_toggle_service() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 1, "toggle")])
    automation = button_automation_builder.build_automation_for_action(
        parsed,
        "press",
        button_device_id="device-abc",
        target_entity_id="light.keuken",
        modules_snapshot=MODULES,
    )
    assert automation["action"][0]["service"] == "light.toggle"


def test_missing_button_device_id_returns_none() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 0, "on")])
    assert (
        button_automation_builder.build_automation_for_action(
            parsed,
            "press",
            button_device_id=None,
            target_entity_id="light.keuken",
            modules_snapshot=MODULES,
        )
        is None
    )


def test_missing_target_entity_returns_none() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 0, "on")])
    assert (
        button_automation_builder.build_automation_for_action(
            parsed,
            "press",
            button_device_id="device-abc",
            target_entity_id=None,
            modules_snapshot=MODULES,
        )
        is None
    )


def test_allon_module_scope_automation() -> None:
    """Special outType with action 'on' produces a module-scope automation."""
    parsed = _parsed_button(
        slot_action_pairs=[("press", "special", 30, 0, "on")]
    )
    automation = button_automation_builder.build_automation_for_action(
        parsed,
        "press",
        button_device_id="device-abc",
        target_entity_id=None,
        modules_snapshot=MODULES,
    )
    assert automation is not None
    assert automation["action"][0]["service"] == "light.turn_on"
    assert automation["action"][0]["target"]["group_id"] == "ipb_module_30"


def test_warning_action_returns_none() -> None:
    parsed = button_mapping.ParsedButton(
        hardware_id="deadbeef0001",
        name="X",
        room="",
        actions=[
            button_mapping.ButtonAction(
                slot="press",
                raw={},
                out_type="relay",
                target_ip_last_octet=30,
                target_channel=0,
                action="on",
                warning="some warning",
            )
        ],
    )
    assert (
        button_automation_builder.build_automation_for_action(
            parsed,
            "press",
            button_device_id="device-abc",
            target_entity_id="light.keuken",
            modules_snapshot=MODULES,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Bulk collection
# ---------------------------------------------------------------------------


def test_collect_automations_emits_press_long_press_and_release() -> None:
    parsed = _parsed_button(
        slot_action_pairs=[
            ("press", "relay", 30, 0, "on"),
            ("long_press", "dimmer", 40, 0, "dim"),
            ("release", "relay", 30, 0, "off"),
        ]
    )
    button_ids = {"deadbeef0001": "device-abc"}
    targets = {
        ("deadbeef0001", "press"): "light.keuken",
        ("deadbeef0001", "long_press"): "light.bureau",
        ("deadbeef0001", "release"): "light.keuken",
    }
    out = button_automation_builder.collect_automations(
        [parsed],
        button_device_ids=button_ids,
        target_entity_ids=targets,
        modules_snapshot=MODULES,
        include_slots=("press", "long_press", "release"),
    )
    assert len(out) == 3
    ids = {a["id"] for a in out}
    assert "ipb_map_deadbeef0001_press" in ids
    assert "ipb_map_deadbeef0001_long_press" in ids
    assert "ipb_map_deadbeef0001_release" in ids


def test_summarise_for_wizard_counts() -> None:
    parsed = _parsed_button(
        slot_action_pairs=[
            ("press", "relay", 30, 0, "on"),
        ]
    )
    summary = button_automation_builder.summarise_for_wizard([parsed])
    assert summary["button_count"] == 1
    assert summary["actionable_count"] == 1
    assert summary["warning_count"] == 0
