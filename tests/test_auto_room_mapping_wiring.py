"""Wiring tests for the auto-launched room-mapping options flow.

``homeassistant`` isn't installed in this environment, so the actual
flow can't be driven end-to-end (see ``test_room_mapping.py`` for the
real, unit-tested decision logic in ``should_offer_room_mapping``).
These assertions lock in the orchestration contract the same way
``test_onboarding_wiring.py`` did before the v1.2.0 wizard removal.
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"


def test_setup_entry_offers_room_mapping_via_options_flow() -> None:
    text = (_COMP / "__init__.py").read_text(encoding="utf-8")
    assert "_maybe_offer_room_mapping" in text
    assert "should_offer_room_mapping" in text
    assert "hass.config_entries.options.async_init" in text
    assert "CONF_ROOM_MAPPING_OFFERED" in text


def test_options_flow_skips_menu_when_auto_offered() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    assert "_auto_room_mapping" in text
    assert "async_step_map_rooms" in text


def test_update_listener_schedules_reload_not_direct() -> None:
    """HA 2026.6+ deprecates async_reload from update listeners."""
    text = (_COMP / "__init__.py").read_text(encoding="utf-8")
    listener = text.split("async def _async_update_listener(")[1].split(
        "async def ", 1
    )[0]
    assert "async_schedule_reload" in listener
    assert "await hass.config_entries.async_reload" not in listener


def test_config_flow_defers_reload_to_update_listener() -> None:
    """``_abort_if_unique_id_configured`` must not reload when a listener exists."""
    text = (_COMP / "config_flow.py").read_text(encoding="utf-8")
    assert "reload_on_update=False" in text
