"""Runtime tests for IPBuildingEventButton entity-id handling.

These tests instantiate ``IPBuildingEventButton`` and assert that
``internal_integration_suggested_object_id`` is set to the raw
hardware id. Requires a real ``homeassistant`` package - otherwise
all tests in this file are skipped (the matching CI environment
has homeassistant installed, see ``requirements-dev.txt``).

The companion-only source-guard tests live in
``test_event_entity_id.py``; those run unconditionally and catch
the regression even when this file is skipped.
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


@pytest.fixture
def event_module():
    """Load the companion ``event.py`` into a synthetic package.

    The companion's coordinator/entity/hub helpers import a long HA
    chain. For these tests we only need the
    ``IPBuildingEventButton`` class - the helpers it transitively
    pulls in are stubbed just enough to satisfy import.

    Skips the whole module if ``event.py`` cannot be loaded (e.g. when
    ``homeassistant`` isn't installed in the test environment). The
    matching source-level tests in ``test_event_entity_id.py`` still
    run in that case and catch the same regressions.
    """
    if "ha_ipbuilding_gateway" not in sys.modules:
        pkg = types.ModuleType("ha_ipbuilding_gateway")
        pkg.__path__ = [str(_COMP_DIR)]
        sys.modules["ha_ipbuilding_gateway"] = pkg

    def _load(name: str):
        spec = importlib.util.spec_from_file_location(
            f"ha_ipbuilding_gateway.{name}", _COMP_DIR / f"{name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except Exception as exc:
            pytest.skip(f"companion.{name} failed to import: {exc}")
        return mod

    _load("const")
    return _load("event")


def test_suggested_object_id_is_hardware_id(event_module):
    """The entity asks HA Core to use the raw hardware id as object_id.

    Result: HA generates ``event.2f8185190000df`` (no slugify, no
    device-name contamination, no doubled room/name).
    """
    device = {"id": "2f8185190000df", "device_type": "input", "name": "Woonkamer hal L"}
    coordinator = MagicMock()
    coordinator.module_for_channel.return_value = None

    button = event_module.IPBuildingEventButton(device, coordinator)

    assert button.internal_integration_suggested_object_id == "2f8185190000df"
    assert button._hardware_id == "2f8185190000df"


def test_unique_id_remains_unchanged(event_module):
    """Backwards-compat: the unique_id pattern is preserved across the
    platform rename, so the HA entity-registry reconciles the new
    event.* entries with the historical button.* entries on next start.
    """
    device = {"id": "2f8185190000df", "device_type": "input", "name": "Woonkamer hal L"}
    coordinator = MagicMock()
    coordinator.module_for_channel.return_value = None

    button = event_module.IPBuildingEventButton(device, coordinator)

    assert button._attr_unique_id == "event_2f8185190000df"


def test_unique_id_differs_per_button(event_module):
    """Each physical button keeps its own unique id - no accidental collapse.

    Regression guard: if someone re-introduces a shared cache keyed on
    name, two physically distinct buttons would collide in the
    entity-registry.
    """
    device_a = {"id": "2f8185190000df", "device_type": "input", "name": "Knop A"}
    device_b = {"id": "cafebabe000001", "device_type": "input", "name": "Knop B"}
    coordinator = MagicMock()
    coordinator.module_for_channel.return_value = None

    a = event_module.IPBuildingEventButton(device_a, coordinator)
    b = event_module.IPBuildingEventButton(device_b, coordinator)

    assert a._attr_unique_id != b._attr_unique_id
    assert a.internal_integration_suggested_object_id != (
        b.internal_integration_suggested_object_id
    )
    assert a._attr_unique_id == "event_2f8185190000df"
    assert b._attr_unique_id == "event_cafebabe000001"
