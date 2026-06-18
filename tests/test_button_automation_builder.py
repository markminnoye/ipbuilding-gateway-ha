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


# ---------------------------------------------------------------------------
# Action strategy tests (modern automation schema)
# ---------------------------------------------------------------------------


def test_relay_on_uses_turn_on() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 0, "on")])
    automation = button_automation_builder.build_automation_for_action(
        parsed,
        "press",
        button_device_id="device-abc",
        target_entity_id="light.keuken",
        target_name="Keuken LED",
    )
    assert automation is not None
    assert automation["id"] == "ipb_map_deadbeef0001_press"
    assert automation["alias"] == "Keuken knop → Keuken LED"
    assert automation["description"] == ""
    assert automation["mode"] == "single"
    assert automation["conditions"] == []
    assert automation["actions"][0]["action"] == "light.turn_on"
    assert automation["actions"][0]["target"]["entity_id"] == "light.keuken"
    trigger = automation["triggers"][0]
    assert trigger["trigger"] == "device"
    assert trigger["domain"] == "ha_ipbuilding_gateway"
    assert trigger["device_id"] == "device-abc"
    assert trigger["type"] == "pressed"
    # No initial_state — the imported automations are enabled.
    assert "initial_state" not in automation


def test_relay_toggle_uses_toggle_service() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 1, "toggle")])
    automation = button_automation_builder.build_automation_for_action(
        parsed,
        "press",
        button_device_id="device-abc",
        target_entity_id="light.keuken",
    )
    assert automation["actions"][0]["action"] == "light.toggle"
    # Falls back to the entity id when no friendly name is supplied.
    assert automation["alias"] == "Keuken knop → light.keuken"


def test_missing_button_device_id_returns_none() -> None:
    parsed = _parsed_button(slot_action_pairs=[("press", "relay", 30, 0, "on")])
    assert (
        button_automation_builder.build_automation_for_action(
            parsed,
            "press",
            button_device_id=None,
            target_entity_id="light.keuken",
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
        )
        is None
    )


def test_special_outtype_is_skipped() -> None:
    """The legacy 'special'/all-on family has no single target — skipped."""
    parsed = _parsed_button(slot_action_pairs=[("press", "special", 30, 0, "on")])
    assert (
        button_automation_builder.build_automation_for_action(
            parsed,
            "press",
            button_device_id="device-abc",
            target_entity_id=None,
        )
        is None
    )


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
    names = {
        ("deadbeef0001", "press"): "Keuken",
        ("deadbeef0001", "long_press"): "Bureau",
        ("deadbeef0001", "release"): "Keuken",
    }
    out = button_automation_builder.collect_automations(
        [parsed],
        button_device_ids=button_ids,
        target_entity_ids=targets,
        target_names=names,
        include_slots=("press", "long_press", "release"),
    )
    assert len(out) == 3
    ids = {a["id"] for a in out}
    assert "ipb_map_deadbeef0001_press" in ids
    assert "ipb_map_deadbeef0001_long_press" in ids
    assert "ipb_map_deadbeef0001_release" in ids
    aliases = {a["alias"] for a in out}
    assert "Keuken knop → Keuken" in aliases  # press alias has no slot marker
    assert "Keuken knop (lang) → Bureau" in aliases


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
