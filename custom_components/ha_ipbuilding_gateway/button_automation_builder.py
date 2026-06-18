"""Build Home Assistant automation configs from parsed button actions.

Generates *automation dicts* in the modern HA schema (``triggers`` /
``conditions`` / ``actions``), e.g.::

    {
        "id": "ipb_map_<hardware_id>_press",
        "alias": "<button name> → <target name>",
        "description": "",
        "triggers": [
            {"trigger": "device", "domain": "ha_ipbuilding_gateway",
             "device_id": "<button device id>", "type": "pressed"}
        ],
        "conditions": [],
        "actions": [
            {"action": "light.toggle", "metadata": {},
             "target": {"entity_id": "light.x"}, "data": {}}
        ],
        "mode": "single",
    }

The action service mirrors the gateway's per-slot ``action`` (on → turn_on,
off → turn_off, toggle → toggle). Only concrete single-target light/switch
automations are produced; outTypes the builder can't map to a single entity
(``motion``, the legacy ``special``/all-on family) are skipped so we never
write an automation that would fail HA's config validation. Persisting the
result to ``automations.yaml`` is the caller's job (see ``automation_store``).
"""

from __future__ import annotations

from typing import Any

from .button_mapping import (
    ParsedButton,
    SLOT_LONG_PRESS,
    SLOT_PRESS,
    SLOT_RELEASE,
)

DEVICE_TRIGGER_DOMAIN = "ha_ipbuilding_gateway"

# Device-trigger types (match custom_components/.../device_trigger.py).
_TRIGGER_TYPE_FOR_SLOT: dict[str, str] = {
    SLOT_PRESS: "pressed",
    SLOT_LONG_PRESS: "long_pressed",
    SLOT_RELEASE: "released",
}


def _service_for_action(out_type: str, action: str) -> tuple[str, str] | None:
    """Map ``(out_type, action)`` to a ``(domain, service)`` tuple.

    Returns ``None`` for outTypes the builder can't turn into a concrete
    single-target light/switch call (``motion``, ``special``/all-on family).
    ``action == "dim"`` collapses to ``turn_on`` for the simple per-slot
    automation.
    """
    if out_type in {"relay", "dimmer"} and action in {"on", "off", "toggle", "dim"}:
        service = {
            "on": "turn_on",
            "off": "turn_off",
            "toggle": "toggle",
            "dim": "turn_on",
        }[action]
        return "light", service
    return None


def _automation_id(hardware_id: str, slot: str) -> str:
    return f"ipb_map_{hardware_id}_{slot}"


def _alias(button: ParsedButton, slot: str, target_name: str) -> str:
    """Build the alias as ``"<button> → <target>"``.

    Non-press slots get a marker on the button side so each slot's automation
    keeps a distinct, readable alias.
    """
    name = button.name or button.hardware_id
    suffix = {SLOT_LONG_PRESS: " (lang)", SLOT_RELEASE: " (loslaten)"}.get(slot, "")
    return f"{name}{suffix} → {target_name}"


def _device_trigger(trigger_type: str, device_id: str) -> dict[str, Any]:
    return {
        "trigger": "device",
        "domain": DEVICE_TRIGGER_DOMAIN,
        "device_id": device_id,
        "type": trigger_type,
    }


def build_automation_for_action(
    button: ParsedButton,
    slot: str,
    *,
    button_device_id: str | None,
    target_entity_id: str | None,
    target_name: str | None = None,
) -> dict[str, Any] | None:
    """Build one HA automation dict for a single parsed action.

    Returns ``None`` when the action can't become a concrete single-target
    automation (missing button device, missing target, unresolved/at-parse
    warning, or an outType the builder can't map).
    """
    action = next((a for a in button.actions if a.slot == slot), None)
    if action is None or action.warning:
        return None
    if not button_device_id or not target_entity_id:
        return None

    service = _service_for_action(action.out_type, action.action)
    if service is None:
        return None
    domain, service_name = service

    return {
        "id": _automation_id(button.hardware_id, slot),
        "alias": _alias(button, slot, target_name or target_entity_id),
        "description": "",
        "triggers": [_device_trigger(_TRIGGER_TYPE_FOR_SLOT[slot], button_device_id)],
        "conditions": [],
        "actions": [
            {
                "action": f"{domain}.{service_name}",
                "metadata": {},
                "target": {"entity_id": target_entity_id},
                "data": {},
            }
        ],
        "mode": "single",
    }


def collect_automations(
    buttons: list[ParsedButton] | ParsedButton,
    *,
    button_device_ids: dict[str, str],
    target_entity_ids: dict[tuple[str, str], str],
    target_names: dict[tuple[str, str], str] | None = None,
    include_slots: tuple[str, ...] = (SLOT_PRESS,),
) -> list[dict[str, Any]]:
    """Build the full automation set for the wizard / setup apply step.

    ``button_device_ids`` maps hardware_id → HA device id of the button.
    ``target_entity_ids`` and ``target_names`` map ``(hardware_id, slot)`` →
    the target light/switch entity id and its friendly name. Slots without a
    resolvable target are skipped silently.
    """
    button_list = [buttons] if isinstance(buttons, ParsedButton) else list(buttons)
    names = target_names or {}
    out: list[dict[str, Any]] = []
    for button in button_list:
        for slot in include_slots:
            target = target_entity_ids.get((button.hardware_id, slot))
            if target is None:
                continue
            automation = build_automation_for_action(
                button=button,
                slot=slot,
                button_device_id=button_device_ids.get(button.hardware_id),
                target_entity_id=target,
                target_name=names.get((button.hardware_id, slot)),
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
