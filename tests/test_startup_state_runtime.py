"""Runtime tests for the startup-state "unknown" fix in light.py and switch.py.

These tests instantiate the real ``IPBuildingLight`` / ``IPBuildingSwitch``
classes and assert that ``_update_from_state`` maps gateway states
correctly. Requires a real ``homeassistant`` package; otherwise all
tests in this file are skipped.

Companion-only source-guard tests live in ``test_startup_state.py``;
those run unconditionally and catch the same regressions.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ha = pytest.importorskip("homeassistant")

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"


def _load_companion_module(name: str):
    """Load ``ha_ipbuilding_gateway.<name>`` and its minimal dependencies.

    The companion imports a long HA chain; we stub just enough to satisfy
    the entity-class constructors used in these tests. Returns the
    requested module.
    """
    if "ha_ipbuilding_gateway" not in sys.modules:
        pkg = types.ModuleType("ha_ipbuilding_gateway")
        pkg.__path__ = [str(_COMP_DIR)]
        sys.modules["ha_ipbuilding_gateway"] = pkg

    def _load(mod_name: str):
        spec = importlib.util.spec_from_file_location(
            f"ha_ipbuilding_gateway.{mod_name}", _COMP_DIR / f"{mod_name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:
            pytest.skip(f"companion.{mod_name} failed to import: {exc}")
        return mod

    for dep in ("const", "coordinator", "entity", "hub"):
        _load(dep)
    return _load(name)


def _make_light():
    """Construct an IPBuildingLight for the no-HA part of the test."""
    light_mod = _load_companion_module("light")
    device = {
        "id": "10.10.1.30-0",
        "name": "Keuken LED",
        "semantic_type": "light",
        "device_type": "relay",
        "module_id": "00:24:77:52:ac:be",
        "module_ip": "10.10.1.30",
    }
    coordinator = MagicMock()
    coordinator.module_for_channel.return_value = None
    return light_mod.IPBuildingLight(device, coordinator)


def _make_switch():
    switch_mod = _load_companion_module("switch")
    device = {
        "id": "10.10.1.30-1",
        "name": "Patio",
        "semantic_type": "switch",
        "device_type": "relay",
        "module_id": "00:24:77:52:ac:be",
        "module_ip": "10.10.1.30",
    }
    coordinator = MagicMock()
    coordinator.module_for_channel.return_value = None
    return switch_mod.IPBuildingSwitch(device, coordinator)


# ---------------------------------------------------------------------------
# light
# ---------------------------------------------------------------------------


class TestLightStartupState:
    def test_unknown_state_maps_to_none(self):
        light = _make_light()
        light._update_from_state({"state": "unknown"})
        assert light._attr_is_on is None

    def test_inactive_state_maps_to_none(self):
        light = _make_light()
        light._update_from_state({"state": "inactive"})
        assert light._attr_is_on is None

    def test_missing_state_maps_to_none(self):
        light = _make_light()
        light._update_from_state({})
        assert light._attr_is_on is None

    def test_on_state_maps_to_true(self):
        light = _make_light()
        light._update_from_state({"state": "on"})
        assert light._attr_is_on is True

    def test_off_state_maps_to_false(self):
        light = _make_light()
        light._update_from_state({"state": "off"})
        assert light._attr_is_on is False

    def test_ON_state_maps_to_true(self):
        # Legacy wire shape uses uppercase
        light = _make_light()
        light._update_from_state({"state": "ON"})
        assert light._attr_is_on is True


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------


class TestSwitchStartupState:
    def test_unknown_state_maps_to_none(self):
        sw = _make_switch()
        sw._update_from_state({"state": "unknown"})
        assert sw._attr_is_on is None

    def test_inactive_state_maps_to_none(self):
        sw = _make_switch()
        sw._update_from_state({"state": "inactive"})
        assert sw._attr_is_on is None

    def test_missing_state_maps_to_none(self):
        sw = _make_switch()
        sw._update_from_state({})
        assert sw._attr_is_on is None

    def test_on_state_maps_to_true(self):
        sw = _make_switch()
        sw._update_from_state({"state": "on"})
        assert sw._attr_is_on is True

    def test_off_state_maps_to_false(self):
        sw = _make_switch()
        sw._update_from_state({"state": "off"})
        assert sw._attr_is_on is False
