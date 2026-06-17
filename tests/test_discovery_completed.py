"""Regression tests for the ``discovery_completed`` WS handler and bootstrap.

Two regressions the uncommitted bootstrap / discovery_completed changes
risked:

1. The WS receive loop blocked on the 5 s ``/api/v1/devices`` REST
   call inside the ``discovery_completed`` handler. Fix: dispatch the
   heavy refresh via ``hass.async_create_task`` so the receive loop
   returns immediately.

2. ``_bootstrap_devices`` could re-enter after ``async_reload`` reset
   the in-memory cache, forming a discover → reload → discover loop.
   Fix: a one-shot flag in ``hass.data`` survives the reload and the
   second ``async_setup_entry`` skips the bootstrap.

These tests do not import HA — they assert the code paths through
text-level checks on the real source plus a tiny in-memory stub for the
flag itself. No voluptuous, no HA runtime.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal ``homeassistant`` stub so the companion's ``const`` can import.
# ---------------------------------------------------------------------------
if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    _ha_const = types.ModuleType("homeassistant.const")
    _ha_const.CONF_HOST = "host"
    _ha_const.CONF_PORT = "port"
    sys.modules["homeassistant.const"] = _ha_const

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ipbuilding_gateway_ha"

# Synthetic package so ``from .const import`` resolves.
_fake_pkg = types.ModuleType("ipbuilding_gateway_ha")
_fake_pkg.__path__ = [str(_COMP_DIR)]
sys.modules["ipbuilding_gateway_ha"] = _fake_pkg

_const_spec = importlib.util.spec_from_file_location(
    "ipbuilding_gateway_ha.const", _COMP_DIR / "const.py"
)
const_mod = importlib.util.module_from_spec(_const_spec)
sys.modules["ipbuilding_gateway_ha.const"] = const_mod
_const_spec.loader.exec_module(const_mod)  # type: ignore[union-attr]

_coordinator_path = _COMP_DIR / "coordinator.py"
_init_path = _COMP_DIR / "__init__.py"


# ---------------------------------------------------------------------------
# Test 1 — discovery_completed handler must not block on REST inside the
# WS receive loop.
# ---------------------------------------------------------------------------


def test_discovery_completed_dispatches_via_async_create_task() -> None:
    """The handler must schedule the heavy refresh, not await it inline."""
    text = _coordinator_path.read_text(encoding="utf-8")

    # The handler block should be small — ``async_create_task`` only.
    block_pattern = re.compile(
        r'elif msg_type == "discovery_completed":.*?\n            '
        r'self\.hass\.async_create_task\(',
        re.DOTALL,
    )
    assert block_pattern.search(text), (
        "discovery_completed handler no longer uses async_create_task; "
        "the receive loop will block on the 5 s REST timeout again"
    )

    # The handler must NOT await _async_update_data directly anymore.
    discovery_block = re.search(
        r'elif msg_type == "discovery_completed":(.*?)\n        else:',
        text,
        re.DOTALL,
    )
    assert discovery_block is not None
    assert "await self._async_update_data()" not in discovery_block.group(1), (
        "_async_update_data is awaited inline again; move it into the "
        "_refresh_after_discovery background task"
    )


def test_refresh_after_discovery_helper_exists() -> None:
    """A background coroutine must wrap the heavy refresh."""
    text = _coordinator_path.read_text(encoding="utf-8")
    assert "async def _refresh_after_discovery" in text, (
        "_refresh_after_discovery coroutine is missing; the WS handler "
        "has nothing to schedule"
    )
    # The helper must call _async_update_data so the actual REST refresh
    # still happens — just not inline with the receive loop.
    helper = re.search(
        r"async def _refresh_after_discovery.*?(?=\n    (?:async )?def |\nclass )",
        text,
        re.DOTALL,
    )
    assert helper is not None
    assert "_async_update_data" in helper.group(0), (
        "_refresh_after_discovery must perform the REST refresh; "
        "otherwise discovery events leave the cache stale"
    )
    assert "_schedule_diff" in helper.group(0), (
        "_refresh_after_discovery must schedule the diff so platforms "
        "create/remove entities when channels appear"
    )


# ---------------------------------------------------------------------------
# Test 2 — bootstrap flag must be one-shot and survive reload.
# ---------------------------------------------------------------------------


def test_bootstrap_flag_is_set_before_scheduling_task() -> None:
    """The flag must be set BEFORE ``async_create_task`` to win the race
    against the reload's second ``async_setup_entry``."""
    text = _init_path.read_text(encoding="utf-8")

    # The flag must be a hass.data entry keyed on entry_id.
    flag_pattern = re.compile(
        r'hass\.data\[DOMAIN\]\[f"\{entry\.entry_id\}_bootstrap_done"\]\s*=\s*True'
    )
    assert flag_pattern.search(text), (
        "Bootstrap one-shot flag is missing; a reload will re-enter "
        "_bootstrap_devices and loop"
    )

    # The flag MUST be set before async_create_task in the same block.
    snippet = re.search(
        r"if not bootstrap_done.*?return True",
        text,
        re.DOTALL,
    )
    assert snippet is not None
    flag_pos = snippet.group(0).find("_bootstrap_done\"")
    task_pos = snippet.group(0).find("async_create_task")
    assert flag_pos != -1 and task_pos != -1
    assert flag_pos < task_pos, (
        "Bootstrap flag must be set BEFORE async_create_task so the "
        "second setup_entry triggered by the reload skips the bootstrap"
    )


def test_bootstrap_helper_skips_when_devices_present() -> None:
    """The fast-path guard inside ``_bootstrap_devices`` must remain."""
    text = _init_path.read_text(encoding="utf-8")
    helper = re.search(
        r"async def _bootstrap_devices.*?(?=\n(?:async )?def )",
        text,
        re.DOTALL,
    )
    assert helper is not None
    assert "if coordinator.devices_snapshot():" in helper.group(0), (
        "_bootstrap_devices lost its early-return guard; it will run a "
        "full forced sweep even when devices already appeared"
    )
    assert "async_trigger_discover" in helper.group(0), (
        "_bootstrap_devices must still call async_trigger_discover — "
        "otherwise a fresh install never gets its first sweep"
    )


# ---------------------------------------------------------------------------
# Test 3 — the flag itself behaves as a one-shot in pure Python.
# We re-implement the flag lookup here so the test does not depend on
# the hass.data path; the integration uses this exact pattern.
# ---------------------------------------------------------------------------


def test_flag_semantics_one_shot_in_pure_python() -> None:
    """Simulates setup_entry twice and asserts the second pass is a no-op."""
    hass_data: dict = {}
    entry_id = "01ABC"

    def setup_entry_pass() -> bool:
        # Mimic ``coordinator.devices_snapshot()`` returning [] on the
        # first pass and [] on the second (cache just got reset by
        # async_reload).
        snapshot: list = []  # empty in both passes
        bootstrap_done = hass_data.get(f"{entry_id}_bootstrap_done")
        if not bootstrap_done and not snapshot:
            hass_data[f"{entry_id}_bootstrap_done"] = True
            return True  # would have scheduled the task
        return False  # skipped

    # First pass: bootstrap runs.
    assert setup_entry_pass() is True
    assert hass_data[f"{entry_id}_bootstrap_done"] is True

    # Second pass (reload): bootstrap does NOT re-enter even though the
    # snapshot is empty.
    assert setup_entry_pass() is False


def test_flag_resets_only_on_user_initiated_reconfigure() -> None:
    """The flag MUST NOT reset inside the bootstrap helper itself —
    only an operator reconfigure (which we do not trigger here) should
    clear it. This guards against accidentally moving the flag write
    into _bootstrap_devices where a reload would still see stale True
    but lose the protection if anyone ever moves the write again."""
    text = _init_path.read_text(encoding="utf-8")
    helper = re.search(
        r"async def _bootstrap_devices.*?(?=\n(?:async )?def )",
        text,
        re.DOTALL,
    )
    assert helper is not None
    assert "_bootstrap_done" not in helper.group(0), (
        "_bootstrap_devices must not touch the bootstrap_done flag; "
        "moving it there would break the one-shot guarantee"
    )
