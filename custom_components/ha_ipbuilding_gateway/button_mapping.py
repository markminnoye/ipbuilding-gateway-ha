"""Parse and normalise IP1100PoE ``getButtons`` entries for the wizard.

The onboarding wizard's button-mapping step consumes the cached
``buttons[]`` payload exposed by the gateway at
``GET /api/v1/modules``. Each entry has at most three action slots:

- ``func1`` — pressed (short tap)
- ``func2`` — long_press (held past the per-button threshold)
- ``release`` — released

The legacy IPBox project stored the same payload as
``autonomyButtons`` (see IPBUILDING_KNOWLEDGE.md §12.7). The numeric
``outType`` values used in the EEPROM-encoding map as follows:

  - 0   = relay
  - 1   = dimmer
  - 160 = special (mapped to ``allOn`` when ``action`` is "on" /
          "allOn", else "allOff")
  - 255 = none

String values are passed through unchanged (lowercased).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Action slot names — these match the trigger types in device_trigger.py.
# ---------------------------------------------------------------------------

SLOT_PRESS = "press"
SLOT_LONG_PRESS = "long_press"
SLOT_RELEASE = "release"

ALL_SLOTS: tuple[str, ...] = (SLOT_PRESS, SLOT_LONG_PRESS, SLOT_RELEASE)

# ---------------------------------------------------------------------------
# outType normalisation
# ---------------------------------------------------------------------------

_OUT_TYPE_NUMERIC_TO_STR: dict[int, str] = {
    0: "relay",
    1: "dimmer",
}


def normalise_out_type(raw: Any) -> str:
    """Map legacy numeric ``outType`` values to a canonical string.

    Falls back to the lower-cased string when ``raw`` is already a
    known type; unknown values pass through lower-cased so the caller
    can flag them in the wizard summary.
    """
    if raw is None:
        return "none"
    if isinstance(raw, (int, float)):
        if raw in _OUT_TYPE_NUMERIC_TO_STR:
            return _OUT_TYPE_NUMERIC_TO_STR[int(raw)]
        if int(raw) == 160:
            return "special"
        if int(raw) == 255:
            return "none"
        return f"unknown({int(raw)})"
    text = str(raw).strip().lower()
    return text or "none"


def normalise_action(raw: Any) -> str:
    """Lower-case the action label, default to ``toggle`` when empty."""
    if raw is None:
        return "toggle"
    return str(raw).strip().lower() or "toggle"


# ---------------------------------------------------------------------------
# Parsed model
# ---------------------------------------------------------------------------


@dataclass
class ButtonAction:
    """A single ``func1`` / ``func2`` / ``release`` payload."""

    slot: str  # SLOT_PRESS | SLOT_LONG_PRESS | SLOT_RELEASE
    raw: dict[str, Any] = field(repr=False)
    out_type: str = "none"
    target_ip_last_octet: int | None = None
    target_channel: int | None = None
    action: str = "toggle"
    warning: str | None = None


@dataclass
class ParsedButton:
    """One ``getButtons`` entry with its resolved action plan."""

    hardware_id: str
    name: str = ""
    room: str = ""
    actions: list[ButtonAction] = field(default_factory=list)


def _ip_last_octet(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).strip().split(".")[-1])
    except (TypeError, ValueError):
        return None


def _channel(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_action(
    slot: str, raw: dict[str, Any] | None
) -> ButtonAction | None:
    """Convert one ``func1`` / ``func2`` / ``release`` payload.

    Returns ``None`` when the slot is empty (an action-less button is
    perfectly valid — the user may have only configured func2).
    """
    if not raw or not isinstance(raw, dict):
        return None

    out_type = normalise_out_type(raw.get("outType"))
    action = normalise_action(raw.get("action"))
    ip_last = _ip_last_octet(raw.get("ip"))
    ch = _channel(raw.get("ch"))

    warning: str | None = None
    if out_type in {"none", "unknown"} or out_type.startswith("unknown("):
        warning = f"onbekende outType {out_type!r} — actie overgeslagen"
    elif ip_last is None or ch is None:
        warning = f"ontbrekende ip/ch voor {slot} — actie overgeslagen"

    return ButtonAction(
        slot=slot,
        raw=raw,
        out_type=out_type,
        target_ip_last_octet=ip_last,
        target_channel=ch,
        action=action,
        warning=warning,
    )


def parse_buttons(buttons: list[dict[str, Any]]) -> list[ParsedButton]:
    """Parse the raw ``getButtons`` array into ``ParsedButton`` records."""
    out: list[ParsedButton] = []
    for entry in buttons or []:
        hardware_id = str(entry.get("id") or "").lower()
        if not hardware_id:
            continue
        name = str(entry.get("descr") or entry.get("name") or "")
        room = str(entry.get("gr") or entry.get("room") or "")
        actions: list[ButtonAction] = []
        for slot, key in (
            (SLOT_PRESS, "func1"),
            (SLOT_LONG_PRESS, "func2"),
            (SLOT_RELEASE, "release"),
        ):
            parsed = _parse_action(slot, entry.get(key))
            if parsed is not None:
                actions.append(parsed)
        out.append(
            ParsedButton(
                hardware_id=hardware_id,
                name=name,
                room=room,
                actions=actions,
            )
        )
    return out


def build_device_id(
    module_ip: str | None, ip_last_octet: int | None, channel: int | None
) -> str | None:
    """Return the gateway device id ``"{module_ip}-{channel}"``.

    The wizard resolves the actual ``module_ip`` from the coordinator
    modules snapshot (modules are keyed on MAC). For unit testing we
    accept a pre-built module_ip and validate the pieces.
    """
    if module_ip is None or ip_last_octet is None or channel is None:
        return None
    if not module_ip.startswith("10.10.1."):
        return None
    if not module_ip.endswith(f".{ip_last_octet}"):
        return None
    return f"{module_ip}-{channel}"


def resolve_module_ip(
    modules: dict[str, dict[str, Any]] | list[dict[str, Any]],
    ip_last_octet: int | None,
) -> str | None:
    """Pick a module_ip from a coordinator modules snapshot by last octet.

    Accepts the dict-keyed-on-MAC form (``coordinator.modules``) or a
    plain list of module dicts (handy for tests).
    """
    if ip_last_octet is None:
        return None
    items: list[dict[str, Any]]
    if isinstance(modules, dict):
        items = list(modules.values())
    else:
        items = list(modules)
    for module in items:
        ip = str(module.get("ip") or "")
        if ip.startswith("10.10.1.") and ip.endswith(f".{ip_last_octet}"):
            return ip
        if ip.endswith(f".{ip_last_octet}"):
            return ip
    return None
