"""Options flow for ha_ipbuilding_gateway.

Three operator-facing actions in the integration options (tandwiel):

- **Ruimtes koppelen** (``map_rooms``) — map gateway ``room`` values to
  Home Assistant areas. The onboarding wizard was removed in v1.2.0;
  this menu item is the explicit place to (re)run the mapping. Stores
  results in ``entry.options[CONF_ROOM_MAPPINGS]``; ``__init__.py``
  reapplies them on every setup.
- **Modules opzoeken op de veldbus** (``scan_bus``) — forced ARP-sweep
  + HTTP identify via ``POST /api/v1/discover``. Finds new, changed,
  and removed modules. Long-running (up to 120 s).
- **Module-instellingen bijwerken** (``refresh_modules``) — re-fetch
  ``getSysSet`` and ``getButtons`` from modules the gateway already
  knows via ``POST /api/v1/modules/refresh``. Faster than a scan
  (typically a few seconds) and does **not** look for new hardware.

In HA 2026.6+ ``OptionsFlow.config_entry`` is a read-only property
backed by ``self.hass.config_entries.async_get_known_entry`` — the
flow manager injects the entry id via ``self.handler`` after the
constructor returns. Do not define ``__init__(self, config_entry)``
and do not assign ``self.config_entry``: the property has no setter
and the assignment raises ``AttributeError`` before the first step
runs.

Menu options must map to ``async_step_<option>`` methods (the
frontend sends ``{"next_step_id": "<option>"}`` and the backend
dispatches via ``getattr(flow, "async_step_<option>")``).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar, selector

from .const import CONF_ROOM_MAPPINGS, DOMAIN
from .room_mapping import apply_room_mappings, collect_unique_rooms


class IPBuildingOptionsFlowHandler(OptionsFlow):
    """Handle options for IPBuilding Gateway HA."""

    @callback
    def async_get_options_flow(self) -> OptionsFlow:  # pragma: no cover - HA dispatches
        # Required by older HA; ignored by 2026.6+ which uses the static
        # ``async_get_options_flow`` on the config flow.
        return self

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options menu.

        Skips straight to ``async_step_map_rooms`` when ``__init__.py``'s
        ``_maybe_offer_room_mapping`` auto-launched this flow right after
        the gateway's rooms first became known — the operator should land
        on the room-mapping form, not the (multi-option) menu.
        """
        flag_key = f"{self.config_entry.entry_id}_auto_room_mapping"
        if self.hass.data.get(DOMAIN, {}).pop(flag_key, False):
            return await self.async_step_map_rooms()
        return self.async_show_menu(
            step_id="init",
            menu_options=["map_rooms", "scan_bus", "refresh_modules"],
        )

    # -------------------------------------------------------------------------
    # Ruimtes koppelen (existing)
    # -------------------------------------------------------------------------

    async def async_step_map_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Map gateway ``room`` values to Home Assistant areas.

        Pulls the current device snapshot from the running coordinator,
        renders one ``AreaSelector`` per unique gateway room, then stores
        the mapping in ``entry.options``. Leaving a field empty falls
        back to creating/reusing an HA area with the gateway room name.
        """
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        await coordinator.async_request_refresh()
        rooms = collect_unique_rooms(coordinator.devices_snapshot())

        if not rooms:
            return self.async_create_entry(
                title="", data=dict(self.config_entry.options)
            )

        if user_input is not None:
            areas = ar.async_get(self.hass)
            mappings: dict[str, str] = {}
            for room in rooms:
                area_id = user_input.get(room, "") or ""
                if not area_id:
                    existing = areas.async_get_area_by_name(room)
                    if existing is None:
                        area = areas.async_create(room)
                        area_id = area.id
                    else:
                        area_id = existing.id
                mappings[room] = area_id

            apply_room_mappings(
                self.hass, self.config_entry, coordinator, mappings
            )
            new_options = {
                **dict(self.config_entry.options),
                CONF_ROOM_MAPPINGS: mappings,
            }
            # ``async_create_entry`` *is* the options write — its ``data`` dict
            # becomes ``entry.options``. Returning ``data={}`` wipes every
            # stored option (including the mapping we just built).
            return self.async_create_entry(title="", data=new_options)

        areas_registry = ar.async_get(self.hass)
        stored = self.config_entry.options.get(CONF_ROOM_MAPPINGS) or {}
        schema: dict[Any, Any] = {}
        for room in rooms:
            default = stored.get(room) or ""
            if not default:
                existing = areas_registry.async_get_area_by_name(room)
                default = existing.id if existing else ""
            schema[vol.Optional(room, default=default)] = selector.AreaSelector()

        return self.async_show_form(
            step_id="map_rooms",
            data_schema=vol.Schema(schema),
            description_placeholders={"room_count": str(len(rooms))},
        )

    # -------------------------------------------------------------------------
    # Modules opzoeken op de veldbus
    # -------------------------------------------------------------------------

    async def async_step_scan_bus(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run the field-bus scan and show the result.

        A separate confirm step would render an empty form (no fields
        to submit) and look like "invisible text" to the operator. The
        scan is fast enough on real networks that we kick it off as
        soon as the menu item is selected, then land on the
        ``_done`` step with the result summary. The gateway's
        120 s timeout remains the upper bound.
        """
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        result = await coordinator.async_run_discover_with_result()
        placeholders = _scan_placeholders(result)
        return self.async_show_form(
            step_id="scan_bus_done",
            description_placeholders=placeholders,
        )

    async def async_step_scan_bus_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return to the options menu after a completed scan."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["map_rooms", "scan_bus", "refresh_modules"],
        )

    # -------------------------------------------------------------------------
    # Module-instellingen bijwerken
    # -------------------------------------------------------------------------

    async def async_step_refresh_modules(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-fetch module metadata and show the result.

        Same reasoning as ``async_step_scan_bus``: an empty confirm
        form would render with no input fields, leaving the operator
        looking at a page with only a Submit button. Run the call
        directly and land on the ``_done`` step.
        """
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        result = await coordinator.async_run_modules_refresh_with_result()
        placeholders = _refresh_placeholders(result)
        return self.async_show_form(
            step_id="refresh_modules_done",
            description_placeholders=placeholders,
        )

    async def async_step_refresh_modules_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return to the options menu after a completed refresh."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["map_rooms", "scan_bus", "refresh_modules"],
        )


def _scan_placeholders(result: dict[str, Any]) -> dict[str, str]:
    """Build description_placeholders for the scan-done step."""
    if not result.get("ok"):
        return {
            "summary": "Scan mislukt — controleer of de gateway bereikbaar is.",
            "ok": "false",
        }
    added = len(result.get("added") or [])
    changed = len(result.get("changed") or [])
    removed = len(result.get("removed") or [])
    duration_s = (int(result.get("duration_ms") or 0) + 500) // 1000
    if added == 0 and changed == 0 and removed == 0:
        summary = f"Geen wijzigingen gevonden ({duration_s} s)."
    else:
        summary = (
            f"{added} toegevoegd, {changed} bijgewerkt, "
            f"{removed} verwijderd ({duration_s} s)."
        )
    return {"summary": summary, "ok": "true"}


def _refresh_placeholders(result: dict[str, Any]) -> dict[str, str]:
    """Build description_placeholders for the refresh-done step."""
    if not result.get("ok"):
        error = result.get("error") or "onbekende fout"
        return {
            "summary": f"Bijwerken mislukt: {error}.",
            "ok": "false",
        }
    modules = int(result.get("module_count") or 0)
    buttons = int(result.get("button_count") or 0)
    summary = f"{modules} module(s) en {buttons} knop(pen) bijgewerkt."
    return {"summary": summary, "ok": "true"}
