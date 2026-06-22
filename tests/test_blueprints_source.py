"""Source-level sanity checks for the packaged blueprints.

Every shipped blueprint must declare its ``ipbuilding_blueprint_version`` so
the upgrade-aware sync in ``blueprints.py`` can detect new releases on
existing installations. This file mirrors the source-only style of
``test_event_entity_id.py``: it inspects the YAML directly so it runs
without a Home Assistant install. Runtime upgrade tests live in
``test_blueprints.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BLUEPRINT_DIR = (
    _REPO
    / "custom_components"
    / "ha_ipbuilding_gateway"
    / "blueprints"
    / "automation"
    / "ha_ipbuilding_gateway"
)

_VERSION_HEADER_RE = re.compile(r"^\s*#\s*ipbuilding_blueprint_version:\s*(\d+)\s*$")


def _shipped_blueprints() -> list[Path]:
    return sorted(_BLUEPRINT_DIR.glob("*.yaml"))


def test_every_shipped_blueprint_declares_a_version() -> None:
    """Each YAML in the package must carry a ``ipbuilding_blueprint_version`` header.

    Without a version the upgrade sync cannot distinguish a new release
    from an identical file and would silently skip upgrades.

    The legacy ``dim_button.yaml`` shipped before versioning was introduced
    is the exception: it stays in the package as a backwards-compatible
    stub until the ``button_dim.yaml`` rollout finishes. Once the stub is
    in place (i.e. the file contains ``[VEROUDERD]``) this exception
    disappears automatically.
    """
    blueprints = _shipped_blueprints()
    assert blueprints, "expected at least one packaged blueprint"
    for path in blueprints:
        text = path.read_text(encoding="utf-8")
        head_lines = text.splitlines()[:20]
        match = next(
            (_VERSION_HEADER_RE.match(line) for line in head_lines if line.startswith("#")),
            None,
        )
        if match is None:
            is_deprecation_stub = (
                "[VEROUDERD]" in text or "deprecated" in text.lower()
            )
            is_legacy_dim = (
                path.name == "dim_button.yaml"
                and not is_deprecation_stub
            )
            assert is_deprecation_stub or is_legacy_dim, (
                f"{path.name} is missing the "
                "# ipbuilding_blueprint_version: N header"
            )
        else:
            assert int(match.group(1)) >= 1, (
                f"{path.name} declares an invalid version: {match.group(1)!r}"
            )
            # The operator-facing description must echo the same version so
            # the version is visible in the HA Blueprints UI. Operators
            # otherwise have no way to tell whether the blueprint on their
            # system is older than the one in the repo.
            header_version = int(match.group(1))
            description_match = re.search(
                r"[Bb]lueprint-versie:\s*(\d+)", text
            )
            assert description_match, (
                f"{path.name} is missing the operator-visible "
                "`**Blueprint-versie: N.**` marker in its description. "
                "The version header on line 1 is for the sync; the "
                "description marker is what the operator sees in HA."
            )
            assert (
                int(description_match.group(1)) == header_version
            ), (
                f"{path.name}: version in description "
                f"({description_match.group(1)}) does not match the "
                f"sync header ({header_version}). Keep them in sync."
            )


def test_dim_blueprint_does_not_set_invalid_max() -> None:
    """The dim blueprint must not carry ``max: 1`` with ``mode: restart``.

    Home Assistant's automation schema rejects ``max < 2`` and ``max`` is
    only meaningful with ``queued`` / ``parallel`` mode. The previous
    dim_button.yaml shipped both, producing
    ``Message malformed: value must be at least 2 @ data['max']`` when
    operators saved a derived automation.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        # Older branches may still call it dim_button.yaml; that case is
        # covered by the deprecation stub and is intentionally exempt.
        return
    text = dim.read_text(encoding="utf-8")
    assert "mode: restart" in text
    # Disallow any ``max:`` line at the automation top level.
    assert not re.search(r"^max:\s*\d+", text, re.MULTILINE), (
        "button_dim.yaml must not declare max: (invalid with mode: restart)"
    )


def test_dim_blueprint_has_helper_user_instructions() -> None:
    """The dim blueprint must mention entity_id vs. name where it still has
    user-editable helpers.

    Spacing in helper entity_ids broke installs in earlier versions —
    the operator-facing text must spell out that the entity_id must
    contain only lowercase letters, digits and underscores. v8 dropped
    the ``direction_helper`` input entirely (the dimmer module owns the
    ramp direction) so this test only applies while any user-facing
    helper input remains.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8").lower()
    if "direction_helper" not in text and "dim_step_pct" not in text:
        # v8+ blueprint — native ramp, no helper inputs.
        return
    assert "entity id" in text or "entity_id" in text
    assert "spaties" in text or "space" in text


def test_dim_blueprint_waits_on_press_before_toggling() -> None:
    """button_dim v3 must wait for release/long_press before toggling.

    v6 dropped the v3 wait_for_trigger: the gateway now classifies the press
    itself, emitting ``single_press`` on release of a short tap and
    ``long_press`` at the threshold. A bare ``light.toggle`` on a direct
    ``single_press`` trigger only fires for actual short presses — long
    presses never reach that branch because the gateway emits
    ``long_press`` instead, so the race the v3 wait_for_trigger was
    designed to handle is gone.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8")
    # v6 hooks the toggle directly into a `single_press` trigger. No
    # `wait_for_trigger` is allowed — the gateway disambiguates now.
    assert "wait_for_trigger" not in text, (
        "button_dim.yaml must not use wait_for_trigger — the gateway "
        "classifies the press into single_press / long_press, so a "
        "timing-based disambiguation is no longer needed and reintroduces "
        "the 600 ms vs 1.5 s race."
    )
    trigger_block = text.split("action:", 1)[0]
    assert 'to: "single_press"' in trigger_block, (
        "button_dim.yaml must trigger on single_press at the top level "
        "(v6 contract: gateway classifies the press)."
    )


def test_dim_blueprint_release_flip_guards_on_long_press() -> None:
    """button_dim v3-v7 must only flip the direction helper after a real long press.

    Firing the flip on every release would also flip after a short press,
    which makes the helper meaningless as a direction tracker. v8 dropped
    the direction helper entirely (the dimmer module owns ramp direction
    and auto-reverses on each successive hold), so the guard is gone too —
    but the ``from: "long_press"`` release-trigger scope remains, because
    a short-tap release must NOT fire the stop service either.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8")
    if "direction_helper" not in text:
        # v8+ blueprint — no helper to flip; the release trigger must still
        # be scoped with ``from: "long_press"`` so a short-tap release does
        # not fire the stop service and cancel the in-flight single_press.
        trigger_block = text.split("action:", 1)[0]
        assert 'from: "long_press"' in trigger_block, (
            "button_dim.yaml v8 must still scope the release trigger with "
            '`from: "long_press"` so a short-tap release does not cancel '
            "the single_press toggle or fire a stray dim_stop."
        )
        return
    assert "trigger.from_state.attributes.event_type == 'long_press'" in text, (
        "button_dim.yaml must guard the release branch on "
        "trigger.from_state.attributes.event_type == 'long_press' so a "
        "short press does not flip the dim direction."
    )


def test_dim_blueprint_short_press_continues_on_timeout() -> None:
    """button_dim v6 dropped the v3 short-press wait_for_trigger.

    v5 used a 600 ms ``wait_for_trigger`` with ``continue_on_timeout: true``
    and a ``wait.trigger is none`` fallback. v6 hooks the toggle into a
    direct ``single_press`` trigger — the gateway already decided that
    this was a short press, so no timing logic is needed. This test
    pins that contract: any reintroduction of wait_for_trigger requires
    removing the assertion below.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8")
    assert "wait_for_trigger" not in text, (
        "button_dim.yaml must not use wait_for_trigger on the short-press "
        "branch (v6 contract: gateway classifies the press directly into "
        "single_press / long_press)."
    )
    assert "light.toggle" in text, (
        "button_dim.yaml must still toggle the target light on a short "
        "press; v6 fires it from the single_press branch."
    )


def test_dim_blueprint_uses_native_ramp_services() -> None:
    """button_dim v8 must drive the dimmer via the native ramp services.

    v8 removes the ``brightness_step_pct`` repeat loop entirely. The
    hold branch dispatches ``ha_ipbuilding_gateway.dim_start``; the
    release branch dispatches ``ha_ipbuilding_gateway.dim_stop``. The
    dimmer module owns ramp direction — no direction helper, no
    endpoint-trigger flip, no step/interval inputs.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8")
    assert "ha_ipbuilding_gateway.dim_start" in text, (
        "button_dim.yaml v8 must call ha_ipbuilding_gateway.dim_start on "
        "the hold branch (native ramp — the dimmer module owns direction)."
    )
    assert "ha_ipbuilding_gateway.dim_stop" in text, (
        "button_dim.yaml v8 must call ha_ipbuilding_gateway.dim_stop on "
        "the release branch (after a real long press)."
    )
    # The legacy loop is gone.
    assert "brightness_step_pct" not in text, (
        "button_dim.yaml v8 must not use brightness_step_pct — the native "
        "ramp replaces the per-step loop."
    )
    assert "repeat:" not in text, (
        "button_dim.yaml v8 must not use repeat: — the native ramp "
        "replaces the hold loop."
    )
    assert "direction_helper" not in text, (
        "button_dim.yaml v8 must not reference direction_helper — the "
        "dimmer module owns ramp direction and auto-reverses."
    )


def test_dim_blueprint_turns_light_on_when_dimming_from_off() -> None:
    """button_dim v3-v7 must turn the light on at 1% before dimming from off.

    Without the turn-on step the first hold on an off lamp would never
    produce light — ``brightness_step_pct`` only steps an already-on lamp.
    v8 dropped the loop entirely (native ramp) and relies on the dimmer
    module's last-level memory + the ``T<ch>991000`` toggle path: the
    module's own behaviour handles off→on when a dim_start lands on an
    off channel. This test only applies while the v3-v7 loop pattern is
    still in the file.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8")
    if "brightness_step_pct" not in text:
        # v8 native ramp — the dimmer module handles the off→on case.
        return
    assert "brightness_pct: 1" in text, (
        "button_dim.yaml must turn the light on at 1% before dimming "
        "from the off state."
    )


def test_no_blueprint_uses_area_id_at_top_level() -> None:
    """No blueprint may declare a top-level ``area_id`` key.

    ``area_id`` is not part of the Home Assistant automation schema —
    HA rejected derived automations with
    ``Message malformed: extra keys not allowed @ data['area_id']``
    when the operator saved a ``button_standard`` instance. The room
    must come from the Home Assistant save popup (or, in the future,
    the automation registry area assignment), never from the
    blueprint itself.
    """
    for path in _shipped_blueprints():
        text = path.read_text(encoding="utf-8")
        assert "area_id:" not in text, (
            f"{path.name} must not declare `area_id:` — it is not a "
            "valid top-level automation key. Use the HA save popup "
            "to assign the room."
        )


def test_no_blueprint_exposes_automation_name_or_area_input() -> None:
    """No blueprint declares ``automation_name`` / ``automation_area`` inputs.

    The Home Assistant save popup prefills the alias with the
    blueprint-name and prompts for the room. Re-declaring those fields
    as blueprint inputs produced a confusing duplicate-label UX
    (v3 of ``button_toggle``) and a save-time schema error
    (v3 of ``button_standard`` and ``button_dim`` — all removed).
    """
    for path in _shipped_blueprints():
        text = path.read_text(encoding="utf-8")
        assert "automation_name" not in text, (
            f"{path.name} must not declare an `automation_name` input. "
            "The HA save popup fills in the alias; declaring it as a "
            "blueprint input creates a duplicate-name UX."
        )
        assert "automation_area" not in text, (
            f"{path.name} must not declare an `automation_area` input. "
            "The HA save popup assigns the room; declaring it as a "
            "blueprint input produces `extra keys not allowed @ "
            "data['area_id']` when saving the derived automation."
        )
        assert "alias: !input" not in text, (
            f"{path.name} must not declare `alias: !input ...`. "
            "Let the HA save popup own the alias."
        )


def test_standard_blueprint_excludes_cover_and_release() -> None:
    """button_standard.yaml must not act on cover services or release triggers.

    Hold-to-move / release-to-stop for covers needs ``long_press`` plus
    ``release`` wiring that ``button_standard`` deliberately does not
    provide. Operators use ``button_dim`` for dimming or build a custom
    automation for covers.

    The description may still mention ``cover`` or ``release`` in prose;
    only actions and top-level triggers must stay out.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    action_idx = text.index("\naction:")
    action_block = text[action_idx:]
    assert "cover." not in action_block
    trigger_block = text[text.index("\ntrigger:") : action_idx]
    assert 'to: "release"' not in trigger_block, (
        "button_standard.yaml must not have a top-level trigger on "
        "release — that fires on every press."
    )
    input_text = text[text.index("input:") : text.index("\ntrigger:")]
    assert "cover" not in input_text


def test_standard_blueprint_uses_single_and_long_press_triggers() -> None:
    """button_standard.yaml must key on single_press and long_press triggers.

    From v7 the gateway classifies the press itself: it emits `single_press`
    on release of a short tap, and `long_press` at the hold threshold while
    the button is still held. The two are mutually exclusive, so a clean
    two-trigger blueprint with no timing logic replaces the v4-v6
    `wait_for_trigger` disambiguation. The race that the 600 ms timeout
    produced (long press never fired on default 1.5 s threshold buttons)
    is gone.

    Both triggers must filter on ``attribute: event_type`` (event entities
    store the type in the attribute, not the state) and must NOT be a
    top-level press + a wait_for_trigger pattern.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    action_idx = text.index("\naction:")
    yaml_body_idx = text.index("\ntrigger:")
    yaml_trigger_block = text[yaml_body_idx:action_idx]
    assert 'to: "single_press"' in yaml_trigger_block, (
        "button_standard.yaml must trigger on single_press at the top "
        "level (v7 contract: gateway classifies the press)."
    )
    assert 'to: "long_press"' in yaml_trigger_block, (
        "button_standard.yaml must trigger on long_press at the top "
        "level (v7 contract: gateway classifies the press)."
    )
    # No more wait_for_trigger: the gateway already disambiguates.
    assert "wait_for_trigger" not in text, (
        "button_standard.yaml must not use wait_for_trigger — the gateway "
        "now classifies the press (single_press on release, long_press "
        "at threshold), so a timing-based disambiguation is no longer "
        "needed and reintroduces the 600 ms vs 1.5 s race."
    )


def test_button_blueprints_use_event_type_attribute_on_triggers() -> None:
    """Every active blueprint trigger on `event.<hw_id>` must filter on `event_type`.

    Event entities expose a timestamp as state and put the press/long_press/release
    type in `attributes.event_type`. A bare `to: "press"` on the state trigger
    matches the timestamp and never fires — see the regression test failure
    for "Hal R → bureau toggle" reported on 2026-06-19.
    """
    targets = {
        "button_standard.yaml": ["press"],
        "button_dim.yaml": ["press", "long_press", "release"],
        "dim_button.yaml": ["press"],
    }
    for filename, event_types in targets.items():
        path = _BLUEPRINT_DIR / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Every `to: "press"` (etc) trigger must also carry `attribute: event_type`.
        for evt in event_types:
            pattern = re.compile(
                r"to:\s*[\"']" + re.escape(evt) + r"[\"']"
            )
            for match in pattern.finditer(text):
                # Look back ~120 chars for `attribute: event_type` on the same block.
                window = text[max(0, match.start() - 200) : match.end() + 50]
                assert "attribute: event_type" in window, (
                    f"{filename}: trigger for `{evt}` is missing "
                    "`attribute: event_type`. Event entities store the "
                    "press/long_press/release value in the attribute, "
                    "not in the state."
                )


def test_standard_blueprint_uses_action_selector() -> None:
    """`button_standard.yaml` must use an `action:` selector per phase (v6 contract).

    v6 replaces the v5 fixed `select:` (Geen / Aan / Uit / Toggle /
    Scene activeren) + `target:` selector pair with a single `action:`
    selector per phase. The operator gets the full HA automation action
    editor — any service, any target, any data — instead of a constrained
    5-way choice + scene-guard logic in the blueprint itself.

    The blueprint just disambiguates short vs long press and hands the
    resolved branch to the operator-defined action sequence via
    `sequence: !input ...`.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # Per fase moet er een action-selector-input zijn.
    assert "press_action:" in text, (
        "button_standard.yaml must declare a `press_action` input"
    )
    assert "long_press_action:" in text, (
        "button_standard.yaml must declare a `long_press_action` input"
    )
    # Action-selector: letterlijk `selector:\n        action:` (action is
    # de canonieke selector-key uit HA, zonder opties).
    assert re.search(
        r"press_action:[\s\S]*?selector:\s*\n\s+action:", text
    ), "press_action input must use `selector: action:`"
    assert re.search(
        r"long_press_action:[\s\S]*?selector:\s*\n\s+action:", text
    ), "long_press_action input must use `selector: action:`"
    # De oude select/target-inputs moeten weg zijn.
    for forbidden in (
        "press_target:",
        "long_press_target:",
        "press_target_kind",
        "press_entity_target",
        "press_area:",
        "long_press_target_kind",
        "long_press_entity_target",
        "long_press_area:",
    ):
        assert forbidden not in text, (
            f"button_standard.yaml must not declare `{forbidden}`; v6 uses "
            "an `action:` selector for the whole sequence."
        )
    # De vaste actie-keuze (Geen/Aan/Uit/Toggle/Scene activeren) moet weg
    # zijn — die zit nu in de action-editor.
    for forbidden in (
        "value: \"activate_scene\"",
        "value: \"none\"\n                  - label: Aan",
        "press_action == 'activate_scene'",
        "press_has_scene",
        "long_press_has_scene",
    ):
        assert forbidden not in text, (
            f"button_standard.yaml must not contain `{forbidden}`; v6 has "
            "no fixed action matrix or scene-guard — the operator picks "
            "the service in the action-editor."
        )


def test_standard_blueprint_wires_press_long_action_inputs() -> None:
    """`button_standard.yaml` must run the operator action lists.

    v7 maps `single_press` (the short-tap gesture) to `press_action` and
    `long_press` to `long_press_action`. The wiring accepts both the
    `sequence: !input <name>` form (inside a `choose:` branch) and the
    `default: !input <name>` form (the v7 default-fallback shape), so we
    look for the `!input` references directly. The blueprint should not
    embed any pre-baked service calls — the operator owns the action
    list.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    action_idx = text.index("\naction:")
    action_block = text[action_idx:]
    assert "!input press_action" in action_block, (
        "button_standard.yaml must reference the operator-defined "
        "press action list via `!input press_action`."
    )
    assert "!input long_press_action" in action_block, (
        "button_standard.yaml must reference the operator-defined "
        "long_press action list via `!input long_press_action`."
    )
    # Geen hardcoded services meer onder de press/long_press branches.
    for forbidden in (
        "homeassistant.toggle",
        "homeassistant.turn_on",
        "homeassistant.turn_off",
        "scene.turn_on",
    ):
        assert forbidden not in action_block, (
            f"button_standard.yaml action block must not hardcode "
            f"`{forbidden}`; the operator supplies services via the "
            "action-selector input."
        )


def test_select_option_values_are_strings() -> None:
    """Every ``select`` option ``value`` must be a YAML string, not a bool.

    YAML 1.1 parses ``on``/``off``/``yes``/``no`` as booleans, so
    ``value: on`` arrives in Home Assistant as the boolean ``True``.
    The ``select`` selector validates values as ``str`` and rejects
    them with::

        Invalid blueprint: expected str for dictionary value
        @ data['blueprint']['input']['...']['value']. Got <bool>

    Quoting (e.g. ``value: "on"``) keeps the value a string. This test
    parses every shipped blueprint and asserts the invariant.
    """
    import re

    yaml = pytest.importorskip("yaml")

    option_re = re.compile(
        r"^\s*-\s*label:\s*(?P<label>[^\n]+)\n"
        r"\s*value:\s*(?P<value>[^\n]+)\n",
        re.MULTILINE,
    )
    bad: list[str] = []
    for path in _shipped_blueprints():
        if path.name == "dim_button.yaml":
            continue
        text = path.read_text(encoding="utf-8")
        for match in option_re.finditer(text):
            raw_value = match.group("value").strip()
            # Skip when the value is already quoted - YAML keeps it as a string.
            if raw_value.startswith('"') or raw_value.startswith("'"):
                continue
            # Parse just the value to see if YAML would coerce it to bool.
            parsed = yaml.safe_load(f"v: {raw_value}")
            if not isinstance(parsed, dict) or not isinstance(parsed.get("v"), str):
                bad.append(
                    f"{path.name}: option {match.group('label').strip()!r} "
                    f"value {raw_value!r} parses as "
                    f"{type(parsed.get('v')).__name__ if isinstance(parsed, dict) else type(parsed).__name__}"
                )
    assert not bad, (
        "YAML 1.1 boolean coercion: quote select option values to keep them "
        "as strings (e.g. `value: \"on\"`):\n  - " + "\n  - ".join(bad)
    )
