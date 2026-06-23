"""Wiring tests for the scan/refresh options-flow actions (v1.8.0).

Companion 1.8.0 adds two operator-facing actions to the integration
options (tandwiel):

- ``scan_bus`` — POST /api/v1/discover
- ``refresh_modules`` — POST /api/v1/modules/refresh

These source-level checks lock in the same contracts the
``test_auto_room_mapping_wiring.py`` tests use for ``map_rooms``:
method names, menu options, coordinator call sites, and translation
keys. The actual flow cannot be driven end-to-end here because
``homeassistant`` is not installed in this environment.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"


def test_options_menu_lists_scan_and_refresh() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    assert '"scan_bus"' in text, "menu must list scan_bus"
    assert '"refresh_modules"' in text, "menu must list refresh_modules"


def test_options_flow_defines_scan_steps() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    assert "async def async_step_scan_bus(" in text
    assert "async def async_step_scan_bus_done(" in text
    # A separate confirm step is intentionally absent: an empty form
    # renders as "invisible text" with no submit field. The scan is
    # kicked off directly from the menu item.
    assert "async_step_scan_bus_progress" not in text


def test_options_flow_defines_refresh_steps() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    assert "async def async_step_refresh_modules(" in text
    assert "async def async_step_refresh_modules_done(" in text
    assert "async_step_refresh_modules_progress" not in text


def test_scan_step_calls_discover() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    block = text.split("async def async_step_scan_bus(")[1].split(
        "async def async_step_scan_bus_done("
    )[0]
    assert "async_run_discover_with_result" in block
    assert "scan_bus_done" in block


def test_refresh_step_calls_modules_refresh() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    block = text.split("async def async_step_refresh_modules(")[1].split(
        "async def async_step_refresh_modules_done("
    )[0]
    assert "async_run_modules_refresh_with_result" in block
    assert "refresh_modules_done" in block


def test_done_steps_return_to_menu() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    scan_done = text.split("async def async_step_scan_bus_done(")[1]
    refresh_done = text.split("async def async_step_refresh_modules_done(")[1]
    for body in (scan_done, refresh_done):
        assert "async_show_menu" in body
        assert '"scan_bus"' in body
        assert '"refresh_modules"' in body


def test_coordinator_modules_refresh_uses_correct_url() -> None:
    text = (_COMP / "coordinator.py").read_text(encoding="utf-8")
    assert "async_run_modules_refresh_with_result" in text
    assert "/api/v1/modules/refresh" in text
    assert "async_trigger_modules_refresh" in text


def test_coordinator_modules_refresh_counts_buttons() -> None:
    text = (_COMP / "coordinator.py").read_text(encoding="utf-8")
    block = text.split("async def async_run_modules_refresh_with_result(")[1].split(
        "async def async_trigger_modules_refresh("
    )[0]
    assert '"input"' in block
    assert "button_count" in block


def test_strings_contains_new_menu_keys_en() -> None:
    strings = json.loads((_COMP / "strings.json").read_text(encoding="utf-8"))
    menu = strings["options"]["step"]["init"]["menu_options"]
    assert "scan_bus" in menu
    assert "refresh_modules" in menu
    steps = strings["options"]["step"]
    assert "title" in steps["scan_bus"]
    assert "description" in steps["scan_bus"]
    assert "title" in steps["scan_bus_done"]
    assert "description" in steps["scan_bus_done"]
    assert "title" in steps["refresh_modules"]
    assert "description" in steps["refresh_modules"]
    assert "title" in steps["refresh_modules_done"]
    assert "description" in steps["refresh_modules_done"]


def test_nl_translations_contain_new_keys() -> None:
    nl = json.loads(
        (_COMP / "translations" / "nl.json").read_text(encoding="utf-8")
    )
    menu = nl["options"]["step"]["init"]["menu_options"]
    assert "scan_bus" in menu
    assert "refresh_modules" in menu
    steps = nl["options"]["step"]
    for key in ("scan_bus", "scan_bus_done", "refresh_modules", "refresh_modules_done"):
        assert "title" in steps[key]
        assert "description" in steps[key]


def test_en_translations_contain_new_keys() -> None:
    en = json.loads(
        (_COMP / "translations" / "en.json").read_text(encoding="utf-8")
    )
    menu = en["options"]["step"]["init"]["menu_options"]
    assert "scan_bus" in menu
    assert "refresh_modules" in menu
    steps = en["options"]["step"]
    for key in ("scan_bus", "scan_bus_done", "refresh_modules", "refresh_modules_done"):
        assert "title" in steps[key]
        assert "description" in steps[key]


def test_manifest_version_bumped() -> None:
    manifest = json.loads((_COMP / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.7.2"


def test_changelog_has_1_7_2_entry() -> None:
    text = (_REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [1.7.2]" in text
    assert "Modules opzoeken op de veldbus" in text
    assert "Knoppen en module-info bijwerken" in text
