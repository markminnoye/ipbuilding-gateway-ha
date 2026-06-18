"""Source-level tests for the IPBuilding device-trigger handler.

Catches the regression where ``async_attach_trigger`` builds an empty
``event_data`` filter when the device's hardware id cannot be resolved.
An empty filter would silently match *every* button event in the
system instead of just the targeted device, so the trigger must fail
loudly in that case.

These tests inspect the source of ``device_trigger.py`` directly so
they run without a real Home Assistant install.
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ipbuilding_gateway_ha"
_TRIGGER_SOURCE = (_COMP_DIR / "device_trigger.py").read_text()


def test_no_empty_event_data_fallback():
    """The handler must never fall back to ``{}`` as event_data filter.

    Regression guard: a previous version used
    ``event_data = {"hardware_id": hardware_id} if hardware_id else {}``
    which, when ``hardware_id`` was ``None``, produced a filter that
    matches *all* events of the trigger type - causing automations to
    fire on any button press in the system.
    """
    forbidden = re_for_empty_fallback()
    assert forbidden.search(_TRIGGER_SOURCE) is None, (
        "device_trigger.py must not fall back to an empty event_data "
        "dict when the hardware id is missing. An empty filter would "
        "match every button event in the system, not just the one for "
        "the targeted device."
    )


def test_missing_hardware_id_raises():
    """When no hardware id can be resolved, ``async_attach_trigger``
    must raise rather than silently attaching a wide-open filter."""
    pattern = re_for_hardware_id_guard()
    assert pattern.search(_TRIGGER_SOURCE) is not None, (
        "device_trigger.py must guard the result of "
        "_hardware_id_for_device() and raise when it is falsy. "
        "Otherwise an empty event_data filter leaks across devices."
    )


def test_event_data_is_built_from_hardware_id():
    """The event_data filter must be derived from the resolved hardware
    id - this is the only way to scope the trigger to a single button."""
    pattern = re_for_event_data_uses_hardware_id()
    assert pattern.search(_TRIGGER_SOURCE) is not None, (
        'device_trigger.py must build event_data as '
        '{"hardware_id": hardware_id} (a non-empty dict) so the event '
        "trigger only matches the intended button."
    )


# --- regex helpers -------------------------------------------------------


def re_for_empty_fallback():
    """Match the forbidden ``{} else`` fallback that produced the bug."""
    import re
    # Tolerate whitespace and the variable name, but block the empty-dict
    # fallback. The two allowed shapes are:
    #   - "raise ..." when hardware_id is falsy (current fix)
    #   - "event_data = {"hardware_id": hardware_id}" (always set)
    return re.compile(
        r'event_data\s*=\s*\{"hardware_id":\s*hardware_id\}\s*if\s*hardware_id\s*else\s*\{\}',
    )


def re_for_hardware_id_guard():
    """Match an ``if not hardware_id:`` ... ``raise`` guard, allowing any
    number of intervening comment lines (the source file has a multi-line
    comment between the ``if`` and the ``raise``)."""
    import re
    return re.compile(
        r"if\s+not\s+hardware_id\s*:\s*\n"  # the if-statement
        r"(?:\s*#[^\n]*\n)*"                 # zero or more full-line comments
        r"\s*raise\b",                        # the raise
        re.MULTILINE,
    )


def re_for_event_data_uses_hardware_id():
    """Match the non-empty event_data assignment that scopes the trigger.

    Uses MULTILINE so the trailing ``$`` matches end-of-line rather than
    end-of-string.
    """
    import re
    return re.compile(
        r'event_data\s*=\s*\{"hardware_id":\s*hardware_id\}\s*$',
        re.MULTILINE,
    )
