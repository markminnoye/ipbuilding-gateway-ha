"""Onboarding wizard steps shared by config flow and options flow."""

from __future__ import annotations

import asyncio
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
from .automation_store import async_write_button_automations
from .room_mapping import apply_room_mappings, collect_unique_rooms
from .target_resolver import build_channel_entity_index, build_channel_name_index

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
    _discover_task: asyncio.Task[None] | None = None
    _modules_refresh_task: asyncio.Task[None] | None = None
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
            # Preserve existing options — for an OptionsFlow the create-entry
            # ``data`` becomes the entry options, so returning ``{}`` would wipe
            # the room mappings / button-import settings written by the coupling
            # wizard and by this flow's own steps.
            return self.async_create_entry(title="", data=dict(entry.options))
        return self.async_abort(reason="onboarding_complete")

    async def async_step_onboarding_intro(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Welcome step — start wizard or skip."""
        return self.async_show_menu(
            step_id="onboarding_intro",
            menu_options=["start", "skip"],
        )

    async def async_step_start(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Begin the onboarding wizard.

        Dispatched by HA when the operator clicks the *start* menu entry
        in :meth:`async_step_onboarding_intro`. The menu always dispatches
        via ``next_step_id`` with ``user_input=None`` (see HA core
        ``data_entry_flow.py:362``), so the legacy ``if user_input is
        not None`` branches in earlier versions of this step never ran.
        """
        self._discover_task = None
        self._modules_refresh_task = None
        self._discover_result = None
        return await self.async_step_onboarding_discovery()

    async def async_step_skip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Skip the wizard and mark onboarding as completed-skipped.

        Dispatched by HA when the operator clicks the *skip* menu entry
        in :meth:`async_step_onboarding_intro`. Marks the config entry
        so the bootstrap in ``__init__.async_setup_entry`` does not
        re-open the wizard on the next reload.
        """
        return await self._finish_onboarding(skipped=True)

    async def async_step_onboarding_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run a forced discovery sweep with progress UI.

        Canonical HA pattern (see ``components/mqtt/config_flow.py``):
        the first invocation creates the asyncio task and returns
        ``async_show_progress``; the flow manager re-invokes the step
        when the task completes via ``call_configure``. The second
        invocation ``await``s the (now-finished) task, then returns
        ``async_show_progress_done(next_step_id=...)`` so HA leaves the
        SHOW_PROGRESS state cleanly. The previous implementation used
        a ``_discovery_progress_done`` bool to short-circuit on the
        second call and returned ``async_show_form`` directly, which
        violated ``data_entry_flow.py:400`` ("Show progress can only
        transition to show progress or show progress done") and
        stranded the wizard on the spinner.
        """
        if self._discover_task is None:
            self._discover_task = self.hass.async_create_task(
                self._onboarding_discover_task()
            )
            return self.async_show_progress(
                step_id="onboarding_discovery",
                progress_action="discovery",
                progress_task=self._discover_task,
            )

        # Second call: progress task is already finished. Await it to
        # surface any exception, then transition out of SHOW_PROGRESS.
        try:
            await self._discover_task
        except Exception as exc:  # noqa: BLE001 — task already logged
            log.debug("Onboarding discovery raised on await: %s", exc)
        finally:
            self._discover_task = None

        return self.async_show_progress_done(
            next_step_id="onboarding_rooms"
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
            for room in self._rooms_list:
                area_id = user_input.get(room, "") or ""
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

        # Key the schema by the gateway room name itself so HA renders it as
        # the field label ("Gelijkvloers", "Buiten", "Inkom", …). The form is
        # dynamic (N rooms) and HA translations are static JSON — there is no
        # way to predefine a label per ``area_<n>`` for an arbitrary room
        # count, so HA fell back to showing the raw key ("area_0"…"area_9").
        # Room names are unique (collect_unique_rooms dedupes).
        schema_dict: dict[Any, Any] = {}
        placeholders: dict[str, str] = {"room_count": str(len(self._rooms_list))}
        areas = ar.async_get(self.hass)
        for room in self._rooms_list:
            # Pre-select an existing HA area with the same name so the dropdown
            # defaults to e.g. "1e Verdiep" for the gateway room "1e Verdiep";
            # the operator can still override or clear it.
            existing = areas.async_get_area_by_name(room)
            schema_dict[vol.Optional(room, default=existing.id if existing else "")] = (
                selector.AreaSelector()
            )

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
        """Reload modules so ``getButtons`` data lands before the button step.

        Mirrors :meth:`async_step_onboarding_discovery` — the first
        call starts the task and shows the progress spinner, the second
        call (triggered by HA's progress completion callback) awaits
        the finished task and transitions to the next step. Without
        this, HA's progress state-machine raises *Show progress can
        only transition to show progress or show progress done*.
        """
        if self._modules_refresh_task is None:
            self._modules_refresh_task = self.hass.async_create_task(
                self._onboarding_modules_refresh_task()
            )
            return self.async_show_progress(
                step_id="onboarding_modules_refresh",
                progress_action="modules_refresh",
                progress_task=self._modules_refresh_task,
            )

        try:
            await self._modules_refresh_task
        except Exception as exc:  # noqa: BLE001 — task already logged
            log.debug("Onboarding modules refresh raised on await: %s", exc)
        finally:
            self._modules_refresh_task = None

        # The refresh task has populated ``self._buttons_cache``; decide the
        # next step now and hand control back to HA via
        # ``async_show_progress_done``. Returning a form directly here is
        # illegal while the step is in the SHOW_PROGRESS state (HA raises
        # "Show progress can only transition to show progress or show
        # progress done"), which is what previously froze the wizard.
        next_step = (
            "onboarding_buttons_overview"
            if self._buttons_cache
            else "onboarding_done"
        )
        return self.async_show_progress_done(next_step_id=next_step)

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
            for key, hardware_id, slot in self._review_field_keys(parsed, candidates):
                entity_id = user_input.get(key, "") or ""
                if entity_id:
                    targets[(hardware_id, slot)] = entity_id
            return await self._apply_button_targets(parsed, candidates, targets)

        if not candidates:
            return await self.async_step_onboarding_done()

        # Key the schema by the human-readable button label so HA renders it
        # as the field label. Same reason as the rooms step: the form is
        # dynamic and HA translations are static JSON, so a raw key like
        # ``target_<hwid>_<slot>`` would be shown verbatim.
        #
        # Pre-fill each selector with the entity the input module already
        # targets, so the existing button configuration is taken over
        # wholesale and the operator only has to confirm (or override).
        channel_entities = build_channel_entity_index(
            self.hass, self._coordinator().devices_snapshot()
        )
        actions_by_key: dict[tuple[str, str], Any] = {}
        for button in parsed:
            for action in button.actions:
                actions_by_key[(button.hardware_id, action.slot)] = action

        schema_dict: dict[Any, Any] = {}
        for key, hardware_id, slot in self._review_field_keys(parsed, candidates):
            action = actions_by_key.get((hardware_id, slot))
            default = ""
            if action is not None and action.target_ip_last_octet is not None:
                default = channel_entities.get(
                    (action.target_ip_last_octet, action.target_channel), ""
                )
            schema_dict[vol.Optional(key, default=default)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["light", "switch"])
            )
        return self.async_show_form(
            step_id="onboarding_buttons_review",
            data_schema=vol.Schema(schema_dict),
        )

    def _review_field_keys(
        self, parsed: list[Any], candidates: list[tuple[str, str]]
    ) -> list[tuple[str, str, str]]:
        """Return ``(field_key, hardware_id, slot)`` for each review candidate.

        ``field_key`` is the readable button label used as the schema key so
        HA shows it as the field label. Duplicate labels get a numeric suffix
        to keep keys unique, and the order is deterministic so the submit
        branch rebuilds the exact same keys to map answers back to
        ``(hardware_id, slot)``.
        """
        keys: list[tuple[str, str, str]] = []
        seen: dict[str, int] = {}
        for hardware_id, slot in candidates:
            label = self._button_label(parsed, hardware_id)
            count = seen.get(label, 0) + 1
            seen[label] = count
            key = label if count == 1 else f"{label} ({count})"
            keys.append((key, hardware_id, slot))
        return keys

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

        # Friendly target names for the automation aliases ("<button> → <name>").
        name_index = build_channel_name_index(coordinator.devices_snapshot())
        snapshot_by_entity: dict[str, tuple[int, int]] = {}
        channel_index = build_channel_entity_index(
            self.hass, coordinator.devices_snapshot()
        )
        for key, entity_id in channel_index.items():
            snapshot_by_entity[entity_id] = key
        target_names: dict[tuple[str, str], str] = {}
        for (hardware_id, slot), entity_id in targets.items():
            key = snapshot_by_entity.get(entity_id)
            if key and key in name_index:
                target_names[(hardware_id, slot)] = name_index[key]

        automations = collect_automations(
            parsed,
            button_device_ids=button_device_ids,
            target_entity_ids=targets,
            target_names=target_names,
            include_slots=(SLOT_PRESS, SLOT_LONG_PRESS, SLOT_RELEASE),
        )

        # Write them as real, editable HA automations and reload.
        await async_write_button_automations(self.hass, automations)

        entry = self._entry()
        options = dict(entry.options)
        options[CONF_BUTTON_AUTOMATIONS] = {
            "targets": {f"{k[0]}|{k[1]}": v for k, v in targets.items()},
            "automations": automations,
        }
        self.hass.config_entries.async_update_entry(entry, options=options)

        return await self.async_step_onboarding_done()
