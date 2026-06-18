"""Onboarding wizard steps shared by config flow and options flow."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import area_registry as ar, selector

from .const import (
    CONF_ONBOARDING_COMPLETED,
    CONF_ONBOARDING_SKIPPED,
    CONF_ROOM_MAPPINGS,
    DOMAIN,
)
from .room_mapping import apply_room_mappings, collect_unique_rooms

log = logging.getLogger(__name__)


class OnboardingFlowMixin:
    """Mixin providing Sprint 1 onboarding wizard steps."""

    _onboarding_entry: Any = None
    _discover_result: dict[str, Any] | None = None
    _rooms_list: list[str] = []
    _discovery_progress_done: bool = False

    def _entry(self) -> Any:
        if self._onboarding_entry is not None:
            return self._onboarding_entry
        return getattr(self, "config_entry", None)

    def _coordinator(self) -> Any:
        entry = self._entry()
        if entry is None:
            raise RuntimeError("No config entry for onboarding")
        return self.hass.data[DOMAIN][entry.entry_id]

    def _discovery_placeholders(self) -> dict[str, str]:
        result = self._discover_result or {}
        duration_ms = int(result.get("duration_ms") or 0)
        return {
            "added": str(len(result.get("added") or [])),
            "changed": str(len(result.get("changed") or [])),
            "removed": str(len(result.get("removed") or [])),
            "duration_s": f"{duration_ms / 1000:.1f}",
        }

    async def _finish_onboarding(self, *, skipped: bool = False) -> ConfigFlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="cannot_connect")

        new_data = dict(entry.data)
        if skipped:
            new_data[CONF_ONBOARDING_SKIPPED] = True
            new_data.pop(CONF_ONBOARDING_COMPLETED, None)
        else:
            new_data[CONF_ONBOARDING_COMPLETED] = True
            new_data.pop(CONF_ONBOARDING_SKIPPED, None)

        self.hass.config_entries.async_update_entry(entry, data=new_data)

        if isinstance(self, config_entries.OptionsFlow):
            return self.async_create_entry(title="", data={})
        return self.async_abort(reason="onboarding_complete")

    async def async_step_onboarding_intro(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Welcome step — start wizard or skip."""
        if user_input is not None:
            if user_input == "skip":
                return await self._finish_onboarding(skipped=True)
            self._discovery_progress_done = False
            self._discover_result = None
            return await self.async_step_onboarding_discovery()

        return self.async_show_menu(
            step_id="onboarding_intro",
            menu_options=["start", "skip"],
        )

    async def async_step_onboarding_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run a forced discovery sweep with progress UI."""
        if user_input is not None:
            return await self.async_step_onboarding_rooms()

        if not self._discovery_progress_done:
            self._discovery_progress_done = True
            progress_task = self.hass.async_create_task(
                self._onboarding_discover_task()
            )
            return self.async_show_progress(
                step_id="onboarding_discovery",
                progress_action="discovery",
                progress_task=progress_task,
            )

        return self.async_show_form(
            step_id="onboarding_discovery",
            data_schema=vol.Schema({}),
            description_placeholders=self._discovery_placeholders(),
        )

    async def _onboarding_discover_task(self) -> None:
        try:
            self._discover_result = (
                await self._coordinator().async_run_discover_with_result()
            )
        except Exception as exc:
            log.warning("Onboarding discovery failed: %s", exc)
            self._discover_result = {
                "ok": False,
                "added": [],
                "changed": [],
                "removed": [],
                "duration_ms": 0,
            }

    async def async_step_onboarding_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Map gateway room names to Home Assistant areas."""
        coordinator = self._coordinator()
        await coordinator.async_request_refresh()
        self._rooms_list = collect_unique_rooms(coordinator.devices_snapshot())

        if not self._rooms_list:
            return await self.async_step_onboarding_done()

        if user_input is not None:
            mappings: dict[str, str] = {}
            areas = ar.async_get(self.hass)
            for index, room in enumerate(self._rooms_list):
                area_id = user_input.get(f"area_{index}", "") or ""
                if not area_id:
                    existing = areas.async_get_area_by_name(room)
                    area_id = existing.id if existing else ""
                mappings[room] = area_id

            entry = self._entry()
            apply_room_mappings(self.hass, entry, coordinator, mappings)
            self.hass.config_entries.async_update_entry(
                entry,
                options={**dict(entry.options), CONF_ROOM_MAPPINGS: mappings},
            )
            return await self.async_step_onboarding_done()

        schema_dict: dict[Any, Any] = {}
        placeholders: dict[str, str] = {"room_count": str(len(self._rooms_list))}
        for index, room in enumerate(self._rooms_list):
            schema_dict[vol.Optional(f"area_{index}", default="")] = (
                selector.AreaSelector()
            )
            placeholders[f"room_{index}"] = room

        return self.async_show_form(
            step_id="onboarding_rooms",
            data_schema=vol.Schema(schema_dict),
            description_placeholders=placeholders,
        )

    async def async_step_onboarding_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Final confirmation before marking onboarding complete."""
        if user_input is not None:
            return await self._finish_onboarding()

        placeholders = self._discovery_placeholders()
        placeholders["room_count"] = str(len(self._rooms_list))

        return self.async_show_form(
            step_id="onboarding_done",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )
