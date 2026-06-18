"""Source-level tests for onboarding wiring."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP = _REPO / "custom_components" / "ha_ipbuilding_gateway"


def test_options_flow_routes_to_onboarding_intro() -> None:
    text = (_COMP / "options_flow.py").read_text(encoding="utf-8")
    assert "OnboardingFlowMixin" in text
    assert "async_step_onboarding_intro" in text
    assert "_auto_onboard" in text


def test_init_applies_onboarding_results_without_auto_launch() -> None:
    text = (_COMP / "__init__.py").read_text(encoding="utf-8")
    # The wizard now runs inside the config flow; there is no auto-launched
    # options flow after setup any more.
    assert "_maybe_launch_onboarding" not in text
    assert "options.async_init" not in text
    # Setup applies the choices the coupling wizard persisted into the entry.
    assert "_apply_onboarding_results" in text
    assert "apply_room_mappings" in text
    assert "CONF_IMPORT_BUTTONS" in text


def test_config_flow_runs_onboarding_wizard() -> None:
    text = (_COMP / "config_flow.py").read_text(encoding="utf-8")
    # Onboarding now lives in the coupling (config) flow, before the entry is
    # created, without reusing the options-flow mixin.
    assert "OnboardingFlowMixin" not in text
    assert "_start_onboarding" in text
    for step in ("async_step_ob_rooms", "async_step_ob_entities", "async_step_ob_buttons"):
        assert step in text
    # Confirm steps dispatch into the wizard instead of creating the entry directly.
    assert "_start_onboarding(" in text


def test_gateway_rest_helpers_exist() -> None:
    text = (_COMP / "gateway_rest.py").read_text(encoding="utf-8")
    for fn in (
        "async_fetch_devices",
        "async_fetch_button_config",
        "async_run_discover",
        "async_refresh_module_metadata",
    ):
        assert f"def {fn}" in text


def test_coordinator_exposes_discover_with_result() -> None:
    text = (_COMP / "coordinator.py").read_text(encoding="utf-8")
    assert "async def async_run_discover_with_result" in text
    assert "async_trigger_discover" in text
