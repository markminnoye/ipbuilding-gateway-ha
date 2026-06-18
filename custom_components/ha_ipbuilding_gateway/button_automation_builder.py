"""Build Home Assistant automation configs from parsed button actions.

This module generates *automation dicts* in the standard HA format. The
wizard persists them via ``hass.services.async_call("automation",
"reload")`` after writing them to ``config/automations.yaml``. Operators
get the same editing/inspection experience as hand-written automations
and can disable them per-automation (they default to ``initial_state:
false`` to avoid surprises during onboarding).

Output schema (per automation)::

    {
        "id": "<stable>",
        "alias": "<human readable>",
        "mode": "single",
        "trigger": [...],
        "condition": [],
        "action": [...],
        "initial_state": False,
    }

The companion itself never persists these to disk — the caller passes a
``writer`` callable that handles the actual write (e.g. ``hass.config.path``
+ yaml dump). Keeping I/O out of the builder keeps it testable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .button_mapping import (
    ParsedButton,
    SLOT_LONG_PRESS,
    SLOT_PRESS,
    SLOT_RELEASE,
    build_device_id,
    resolve_module_ip,
)

# ---------------------------------------------------------------------------
# Device-trigger mapping (matches custom_components/.../device_trigger.py)
# ---------------------------------------------------------------------------

_TRIGGER_TYPE_FOR_SLOT: dict[str, str] = {
    SLOT_PRESS: "pressed",
    SLOT_LONG_PRESS: "long_pressed",
    SLOT_RELEASE: "released",
}

# ---------------------------------------------------------------------------
# Action-strategy constants
# ---------------------------------------------------------------------------

SERVICE_LIGHT_ON = "light.turn_on"
SERVICE_LIGHT_OFF = "light.turn_off"
SERVICE_LIGHT_TOGGLE = "light.toggle"
SERVICE_SWITCH_ON = "switch.turn_on"
SERVICE_SWITCH_OFF = "switch.turn_off"
SERVICE_SWITCH_TOGGLE = "switch.toggle"

# Service names that need the module's full light/switch list. We
# resolve these at apply-time using the coordinator snapshot.
MODULE_SCOPE_ACTIONS = {"on", "off", "allon", "alloff"}


def _service_for_action(
    out_type: str, action: str
) -> tuple[str, str] | None:
    """Map ``(out_type, action)`` to a ``(service_domain, service_name)`` tuple.

    Returns ``None`` for outType ``motion`` and the legacy "special"
    family which the wizard surfaces as a separate ``allon`` / ``alloff``
    strategy.

    ``action == "dim"`` collapses to ``light.turn_on`` for the simple
    per-slot automation; the dedicated dim-during-hold blueprint is a
    follow-up that does not live in this builder.
    """
    if out_type == "dimmer":
        if action in {"on", "off", "toggle", "dim"}:
            return "light", {
                "on": "turn_on",
                "off": "turn_off",
                "toggle": "toggle",
                "dim": "turn_on",
            }[action]
    if out_type == "relay":
        if action in {"on", "off", "toggle"}:
            return "light", {
                "on": "turn_on",
                "off": "turn_off",
                "toggle": "toggle",
            }[action]
    if out_type in {"special"} and action in {"on", "allon"}:
        return None  # handled by module-scope strategy
    if out_type in {"special"} and action in {"off", "alloff"}:
        return None
    return None


def _automation_id(hardware_id: str, slot: str) -> str:
    return f"ipb_map_{hardware_id}_{slot}"


def _alias(button: ParsedButton, slot: str) -> str:
    friendly = button.name or button.hardware_id
    suffix = {
        SLOT_PRESS: "korte druk",
        SLOT_LONG_PRESS: "lang ingedrukt",
        SLOT_RELEASE: "losgelaten",
    }.get(slot, slot)
    return f"{friendly} — {suffix}"


def _device_trigger(
    trigger_type: str, device_id: str | None
) -> dict[str, Any] | None:
    if not device_id:
        return None
    return {
        "platform": "device",
        "domain": "ha_ipbuilding_gateway",
        "device_id": device_id,
        "type": trigger_type,
    }


def build_automation_for_action(
    button: ParsedButton,
    slot: str,
    *,
    button_device_id: str | None,
    target_entity_id: str | None,
    modules_snapshot: dict[str, dict[str, Any]] | list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build one automation dict for a single parsed action.

    Returns ``None`` when the action can't be turned into a sensible
    automation (e.g. ``outType=motion``, or missing target). The caller
    surfaces those in the wizard summary.
    """
    action = next((a for a in button.actions if a.slot == slot), None)
    if action is None:
        return None

    if action.warning:
        return None  # action was unresolvable at parse time

    trigger = _device_trigger(
        _TRIGGER_TYPE_FOR_SLOT[slot], button_device_id
    )
    if trigger is None:
        return None

    service = _service_for_action(action.out_type, action.action)
    if service is not None:
        # Single-target light/switch call.
        if not target_entity_id:
            return None
        domain, service_name = service
        return {
            "id": _automation_id(button.hardware_id, slot),
            "alias": _alias(button, slot),
            "mode": "single",
            "trigger": [trigger],
            "condition": [],
            "action": [
                {
                    "service": f"{domain}.{service_name}",
                    "target": {"entity_id": target_entity_id},
                }
            ],
            "initial_state": False,
        }

    if action.action in MODULE_SCOPE_ACTIONS:
        return _build_module_scope_automation(
            button=button,
            slot=slot,
            trigger=trigger,
            modules_snapshot=modules_snapshot,
            turn_on=action.action in {"on", "allon"},
        )

    return None


def _build_module_scope_automation(
    *,
    button: ParsedButton,
    slot: str,
    trigger: dict[str, Any],
    modules_snapshot: dict[str, dict[str, Any]] | list[dict[str, Any]],
    turn_on: bool,
) -> dict[str, Any] | None:
    """Build an automation that toggles every active channel on a module."""
    action = next((a for a in button.actions if a.slot == slot), None)
    if action is None or action.target_ip_last_octet is None:
        return None
    module_ip = resolve_module_ip(modules_snapshot, action.target_ip_last_octet)
    if module_ip is None:
        return None

    # The wizard's caller resolves the actual entity_id list using its
    # own coordinator snapshot; we encode a deterministic group_id and
    # let the caller substitute a `light.<module_ip>_*` group at apply
    # time. To keep the builder pure we fall back to a YAML-friendly
    # group placeholder; the wizard's apply path will replace it with
    # a real entity list.
    service = SERVICE_LIGHT_ON if turn_on else SERVICE_LIGHT_OFF
    return {
        "id": _automation_id(button.hardware_id, slot) + "_module",
        "alias": _alias(button, slot) + f" (module {action.target_ip_last_octet})",
        "mode": "single",
        "trigger": [trigger],
        "condition": [],
        "action": [
            {
                "service": service,
                "target": {
                    "group_id": f"ipb_module_{action.target_ip_last_octet}",
                },
            }
        ],
        "initial_state": False,
    }


def collect_automations(
    buttons: list[ParsedButton] | ParsedButton,
    *,
    button_device_ids: dict[str, str],
    target_entity_ids: dict[tuple[str, str], str],
    modules_snapshot: dict[str, dict[str, Any]] | list[dict[str, Any]],
    include_slots: tuple[str, ...] = (SLOT_PRESS,),
) -> list[dict[str, Any]]:
    """Build the full automation set for the wizard apply step.

    ``button_device_ids`` maps hardware_id → HA device id of the
    IP1100PoE button entity. ``target_entity_ids`` maps
    ``(hardware_id, slot)`` → entity_id of the light/switch the action
    should control. Slots without a target are skipped silently.

    Accepts either a list of ``ParsedButton`` or a single instance for
    convenience in tests and one-off wizard calls.
    """
    if isinstance(buttons, ParsedButton):
        button_list = [buttons]
    else:
        button_list = list(buttons)
    out: list[dict[str, Any]] = []
    for button in button_list:
        for slot in include_slots:
            target = target_entity_ids.get((button.hardware_id, slot))
            if slot != SLOT_RELEASE and target is None:
                continue
            automation = build_automation_for_action(
                button=button,
                slot=slot,
                button_device_id=button_device_ids.get(button.hardware_id),
                target_entity_id=target,
                modules_snapshot=modules_snapshot,
            )
            if automation is not None:
                out.append(automation)
    return out


def summarise_for_wizard(buttons: list[ParsedButton]) -> dict[str, Any]:
    """Return counts the wizard can show in its overview step."""
    with_actions = sum(1 for b in buttons if b.actions)
    with_warning = sum(1 for b in buttons for a in b.actions if a.warning)
    return {
        "button_count": len(buttons),
        "actionable_count": with_actions,
        "warning_count": with_warning,
    }
