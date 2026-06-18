"""Source-level guard for the startup-state "unknown" fix.

After a gateway/companion restart the first REST/WS snapshot reports
``state="unknown"`` for relay channels and (previously) ``state="off"``
for dimmer channels whose level isn't yet in the registry.  The
companion's ``_update_from_state`` must surface that as ``_attr_is_on = None``
(HA renders "Unknown") rather than ``False`` (HA renders "off").

These textual checks run unconditionally and catch the regression
where the fix is accidentally removed during a refactor, even before
any runtime tests get a chance to run. Runtime tests for the same
invariant live in ``test_startup_state_runtime.py`` and require the
``homeassistant`` package.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"
_LIGHT_SOURCE = (_COMP_DIR / "light.py").read_text()
_SWITCH_SOURCE = (_COMP_DIR / "switch.py").read_text()


def _assert_unknown_guard(source: str, platform: str) -> None:
    """``_update_from_state`` must not collapse ``unknown``/``inactive`` to
    ``False``. The fix checks for these gateway states explicitly and
    assigns ``None`` to ``_attr_is_on`` so HA renders the entity as
    "Unknown" instead of "off"."""
    pattern = re.compile(
        r"if\s+raw\s+in\s+\(None,\s*[\"']unknown[\"']\s*,\s*[\"']inactive[\"']\s*\)\s*:\s*"
        r"self\._attr_is_on\s*=\s*None",
        re.DOTALL,
    )
    assert pattern.search(source), (
        f"{platform}.py: _update_from_state must map "
        "None/unknown/inactive to _attr_is_on = None (HA 'Unknown')"
    )


def test_light_update_from_state_has_unknown_guard():
    _assert_unknown_guard(_LIGHT_SOURCE, "light")


def test_switch_update_from_state_has_unknown_guard():
    _assert_unknown_guard(_SWITCH_SOURCE, "switch")


def test_light_no_longer_collapses_unknown_to_false():
    """Regression guard: the pre-fix pattern ``state in ("on", "ON")``
    silently turned every unknown state into ``False`` (HA "off")."""
    pattern = re.compile(
        r"is_on\s*=\s*state\.get\([\"']state[\"']\)\s*in\s*\(\s*[\"']on[\"']\s*,\s*[\"']ON[\"']\s*\)"
    )
    assert not pattern.search(_LIGHT_SOURCE), (
        "light.py: the pre-fix pattern is_on = state.get('state') in "
        "('on', 'ON') must be replaced by the explicit unknown guard"
    )


def test_switch_no_longer_collapses_unknown_to_false():
    pattern = re.compile(
        r"is_on\s*=\s*state\.get\([\"']state[\"']\)\s*in\s*\(\s*[\"']on[\"']\s*,\s*[\"']ON[\"']\s*\)"
    )
    assert not pattern.search(_SWITCH_SOURCE), (
        "switch.py: the pre-fix pattern is_on = state.get('state') in "
        "('on', 'ON') must be replaced by the explicit unknown guard"
    )
