"""Tests for the automations.yaml merge logic."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"

# automation_store imports Home Assistant lazily (only inside the writer), so
# the module — and the pure merge helper under test — imports with no HA stub.
spec = importlib.util.spec_from_file_location(
    "_ipb_automation_store", _COMP / "automation_store.py"
)
automation_store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(automation_store)  # type: ignore[union-attr]


def test_merge_replaces_managed_and_keeps_operator_entries() -> None:
    existing = [
        {"id": "my_own_automation", "alias": "Operator one"},
        {"id": "ipb_map_old_press", "alias": "Stale generated"},
        {"alias": "No id, operator authored"},
    ]
    new = [{"id": "ipb_map_new_press", "alias": "Fresh"}]
    merged = automation_store.merge_managed_automations(existing, new)
    ids = [a.get("id") for a in merged]
    assert "my_own_automation" in ids
    assert "ipb_map_new_press" in ids
    assert "ipb_map_old_press" not in ids  # our stale entry dropped
    # Operator entry without an id is preserved.
    assert any(a.get("alias") == "No id, operator authored" for a in merged)


def test_merge_handles_empty_or_non_list_existing() -> None:
    new = [{"id": "ipb_map_x_press", "alias": "X"}]
    assert automation_store.merge_managed_automations(None, new) == new
    assert automation_store.merge_managed_automations([], new) == new
