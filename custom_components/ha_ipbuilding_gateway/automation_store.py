"""Persist generated button automations into the user's automations.yaml.

Home Assistant stores file-based automations as a YAML list (the file behind
``automation: !include automations.yaml`` in the default config). To make the
companion's button automations appear as real, editable automations we merge
them into that list — keyed by a stable ``ipb_map_*`` id so a re-run replaces
our own entries instead of duplicating them — and then reload the automation
integration.

This assumes the standard ``!include automations.yaml`` layout (HA's default).
If the operator manages automations differently, the generated configs still
live in the entry options as a record.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

log = logging.getLogger(__name__)

MANAGED_ID_PREFIX = "ipb_map_"


def merge_managed_automations(
    existing: Any, automations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return ``existing`` with our managed (``ipb_map_*``) entries replaced.

    Operator-authored automations are preserved; only entries whose ``id``
    starts with :data:`MANAGED_ID_PREFIX` are dropped before appending the
    freshly generated ones, so re-running never duplicates them.
    """
    if not isinstance(existing, list):
        existing = []
    kept = [
        item
        for item in existing
        if not str((item or {}).get("id", "")).startswith(MANAGED_ID_PREFIX)
    ]
    kept.extend(automations)
    return kept


async def async_write_button_automations(
    hass: HomeAssistant, automations: list[dict[str, Any]]
) -> bool:
    """Merge ``automations`` into automations.yaml and reload.

    Returns True when the file was written and a reload was requested. Our own
    previously-written entries (``id`` starting with ``ipb_map_``) are replaced;
    everything else the operator has is preserved.
    """
    if not automations:
        return False

    from homeassistant.config import AUTOMATION_CONFIG_PATH
    from homeassistant.util.yaml import load_yaml, save_yaml

    path = hass.config.path(AUTOMATION_CONFIG_PATH)

    def _merge_write() -> None:
        try:
            existing = load_yaml(path)
        except FileNotFoundError:
            existing = []
        save_yaml(path, merge_managed_automations(existing, automations))

    try:
        await hass.async_add_executor_job(_merge_write)
    except Exception:
        log.exception("Failed to write button automations to %s", path)
        return False

    try:
        await hass.services.async_call("automation", "reload", blocking=True)
    except Exception as exc:
        log.warning("automation.reload after writing automations failed: %s", exc)
    return True
