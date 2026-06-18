"""Options flow for ha_ipbuilding_gateway."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow

from .onboarding_flow import OnboardingFlowMixin


class IPBuildingOptionsFlowHandler(OnboardingFlowMixin, OptionsFlow):
    """Handle options for IPBuilding Gateway HA."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Present the options menu."""
        if user_input is not None:
            if user_input == "run_onboarding":
                self._onboarding_entry = self.config_entry
                self._discovery_progress_done = False
                self._discover_result = None
                return await self.async_step_onboarding_intro()
            return self.async_abort(reason="unknown_option")

        return self.async_show_menu(
            step_id="init",
            menu_options=["run_onboarding"],
        )
