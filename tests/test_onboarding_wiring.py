"""Source-level tests for onboarding wiring."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"


def test_config_flow_has_onboarding_entry_step() -> None:
    text = (_COMP / "config_flow.py").read_text(encoding="utf-8")
    assert "async_step_onboarding" in text
    assert "OnboardingFlowMixin" in text
    assert 'context.get("entry_id")' in text


def test_init_launches_onboarding_when_not_completed() -> None:
    text = (_COMP / "__init__.py").read_text(encoding="utf-8")
    assert "_maybe_launch_onboarding" in text
    assert 'context={"source": "onboarding"' in text
    assert "CONF_ONBOARDING_COMPLETED" in text


def test_coordinator_exposes_discover_with_result() -> None:
    text = (_COMP / "coordinator.py").read_text(encoding="utf-8")
    assert "async def async_run_discover_with_result" in text
    assert "async_trigger_discover" in text
