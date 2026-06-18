"""Onboarding wizard steps shared by config flow and options flow."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import area_registry as ar, selector

from .const import (
    CONF_BUTTON_AUTOMATIONS,
    CONF_ONBOARDING_COMPLETED,
    CONF_ONBOARDING_SKIPPED,
    CONF_ROOM_MAPPINGS,
    DOMAIN,
)
from .room_mapping import apply_room_mappings, collect_unique_rooms

from .button_automation_builder import (
    collect_automations,
    summarise_for_wizard,
)
from .button_mapping import (
    SLOT_LONG_PRESS,
    SLOT_PRESS,
    SLOT_RELEASE,
    parse_buttons,
)

log = logging.getLogger(__name__)


class OnboardingFlowMixin:
    """Mixin providing Sprint 1 onboarding wizard steps."""

    _onboarding_entry: Any = None
    _discover_result: dict[str, Any] | None = None
    _rooms_list: list[str] = []
    _discovery_progress_done: bool = False
    _buttons_cache: list[dict[str, Any]] = []
    _module_devices_by_mac: dict[str, dict[str, Any]] = {}

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
            return await self.async_step_onboarding_modules_refresh()

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
            return await self.async_step_onboarding_modules_refresh()

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
        placeholders["button_count"] = str(len(self._buttons_cache))

        return self.async_show_form(
            step_id="onboarding_done",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )

    async def async_step_onboarding_modules_refresh(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reload modules so ``getButtons`` data lands before the button step."""
        if user_input is not None:
            return await self._button_overview_or_done()

        progress_task = self.hass.async_create_task(
            self._onboarding_modules_refresh_task()
        )
        return self.async_show_progress(
            step_id="onboarding_modules_refresh",
            progress_action="modules_refresh",
            progress_task=progress_task,
        )

    async def _onboarding_modules_refresh_task(self) -> None:
        try:
            await self._coordinator().async_request_refresh()
        except Exception as exc:
            log.warning("Onboarding modules refresh failed: %s", exc)
        await self._load_buttons_cache()

    async def _load_buttons_cache(self) -> None:
        try:
            self._buttons_cache = await self._coordinator().async_fetch_button_config()
        except Exception as exc:
            log.warning("Onboarding getButtons fetch failed: %s", exc)
            self._buttons_cache = []

    async def _button_overview_or_done(self) -> ConfigFlowResult:
        if not self._buttons_cache:
            return await self.async_step_onboarding_done()
        return await self.async_step_onboarding_buttons_overview()

    async def async_step_onboarding_buttons_overview(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a count summary of detected buttons + actions."""
        parsed = parse_buttons(self._buttons_cache)
        summary = summarise_for_wizard(parsed)

        if user_input is not None:
            entry = self._entry()
            targets: dict[tuple[str, str], str] = dict(
                entry.options.get(CONF_BUTTON_AUTOMATIONS, {}).get("targets", {})
            )
            self._pending_targets = targets
            return await self.async_step_onboarding_buttons_review()

        placeholders = {
            "button_count": str(summary["button_count"]),
            "actionable_count": str(summary["actionable_count"]),
            "warning_count": str(summary["warning_count"]),
        }
        return self.async_show_form(
            step_id="onboarding_buttons_overview",
            data_schema=vol.Schema({}),
            description_placeholders=placeholders,
        )

    async def async_step_onboarding_buttons_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the operator confirm/override the proposed button → target mapping.

        One form per page is impractical for many buttons, so we render
        a single form with one ``target_<idx>`` entity selector per
        ``func1`` action; other slots follow the same target by default.
        """
        parsed = parse_buttons(self._buttons_cache)
        candidates: list[tuple[str, str]] = []
        for button in parsed:
            for action in button.actions:
                if action.slot != SLOT_PRESS or action.warning:
                    continue
                if not action.target_ip_last_octet or action.target_channel is None:
                    continue
                candidates.append((button.hardware_id, action.slot))

        if user_input is not None:
            targets: dict[tuple[str, str], str] = {}
            for hardware_id, slot in candidates:
                entity_id = user_input.get(f"target_{hardware_id}_{slot}", "") or ""
                if entity_id:
                    targets[(hardware_id, slot)] = entity_id
            return await self._apply_button_targets(parsed, candidates, targets)

        if not candidates:
            return await self.async_step_onboarding_done()

        schema_dict: dict[Any, Any] = {}
        placeholders: dict[str, str] = {}
        for hardware_id, slot in candidates:
            schema_dict[vol.Optional(f"target_{hardware_id}_{slot}", default="")] = (
                selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["light", "switch"])
                )
            )
            placeholders[f"label_{hardware_id}_{slot}"] = self._button_label(
                parsed, hardware_id
            )
        return self.async_show_form(
            step_id="onboarding_buttons_review",
            data_schema=vol.Schema(schema_dict),
            description_placeholders=placeholders,
        )

    def _button_label(self, parsed: list[Any], hardware_id: str) -> str:
        for b in parsed:
            if b.hardware_id == hardware_id:
                return b.name or hardware_id
        return hardware_id

    async def _apply_button_targets(
        self,
        parsed: list[Any],
        candidates: list[tuple[str, str]],
        targets: dict[tuple[str, str], str],
    ) -> ConfigFlowResult:
        coordinator = self._coordinator()
        from homeassistant.helpers import device_registry as dr

        device_registry = dr.async_get(self.hass)
        button_device_ids: dict[str, str] = {}
        for device in device_registry.devices.values():
            for domain, identifier in device.identifiers:
                if domain == DOMAIN and identifier in {
                    p.hardware_id for p in parsed
                }:
                    button_device_ids[identifier] = device.id

        automations = collect_automations(
            parsed,
            button_device_ids=button_device_ids,
            target_entity_ids=targets,
            modules_snapshot=coordinator.modules,
            include_slots=(SLOT_PRESS, SLOT_LONG_PRESS, SLOT_RELEASE),
        )

        entry = self._entry()
        options = dict(entry.options)
        options[CONF_BUTTON_AUTOMATIONS] = {
            "targets": {f"{k[0]}|{k[1]}": v for k, v in targets.items()},
            "automations": automations,
        }
        self.hass.config_entries.async_update_entry(entry, options=options)

        # Best-effort reload of the automations integration so the new
        # automations appear without a manual restart.
        try:
            await self.hass.services.async_call(
                "automation", "reload", blocking=False
            )
        except Exception as exc:
            log.debug("automation.reload skipped: %s", exc)

        return await self.async_step_onboarding_done()
