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
    """The dim blueprint must mention entity_id vs. name for its helper.

    Spacing in helper entity_ids broke installs in earlier versions —
    the operator-facing text must spell out that the entity_id must
    contain only lowercase letters, digits and underscores.
    """
    dim = _BLUEPRINT_DIR / "button_dim.yaml"
    if not dim.exists():
        return
    text = dim.read_text(encoding="utf-8").lower()
    assert "entity id" in text or "entity_id" in text
    assert "spaties" in text or "space" in text


def test_every_non_legacy_blueprint_has_alias_and_area_id() -> None:
    """Every shipped blueprint (except the legacy dim stub and the
    minimal `button_toggle`) exposes alias + area_id.

    Both top-level keys are part of the operator UX promise from the
    2026-06-18 design spec: the automation name comes from the operator
    (typically the friendly button name) and the room follows the
    gateway-side ``room`` field via ``suggested_area``.

    `button_toggle` is the minimal blueprint: HA asks for the room in
    the popup that appears after pressing "Opslaan", so the blueprint
    does not declare an `automation_area` input.
    """
    for path in _shipped_blueprints():
        if path.name in ("dim_button.yaml", "button_toggle.yaml"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "alias: !input automation_name" in text, (
            f"{path.name} must expose `alias: !input automation_name`"
        )
        assert "area_id: !input automation_area" in text, (
            f"{path.name} must expose `area_id: !input automation_area`"
        )


def test_toggle_blueprint_only_uses_press_trigger() -> None:
    """button_toggle.yaml must not react to long_press or release events.

    The toggle blueprint is the minimal-use-case. Avoiding the other
    triggers keeps the GUI small and prevents accidental runs on hold.
    """
    path = _BLUEPRINT_DIR / "button_toggle.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    assert 'to: "press"' in text
    assert 'to: "long_press"' not in text
    assert 'to: "release"' not in text


def test_standard_blueprint_excludes_cover_and_release() -> None:
    """button_standard.yaml must not act on cover or release behaviour.

    Curtains and screens have their own blueprint (button_cover). Mixing
    them here confuses operators because the release event fires after
    every press. The standard blueprint may still mention `cover` and
    `release` in its description text (e.g. as a pointer to the dedicated
    blueprints) — only the actions and triggers must stay out.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # No cover service call should appear in the action block.
    assert "cover." not in text
    # No release trigger id should be wired up.
    assert 'to: "release"' not in text
    # `activate_scene` is the only scene-shaped action; activate_scene
    # plus a cover domain would be contradictory — guard the input instead.
    input_text = text[text.index("input:"):]
    assert "cover" not in input_text


def test_cover_blueprint_uses_hold_and_release_triggers() -> None:
    """button_cover.yaml must hook into long_press and release events.

    The cover pattern is: while held, move in a direction; on release,
    stop. Both trigger types must be present.
    """
    path = _BLUEPRINT_DIR / "button_cover.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    assert 'to: "long_press"' in text
    assert 'to: "release"' in text


def test_toggle_blueprint_has_no_automation_area_input() -> None:
    """`button_toggle.yaml` must not declare an `automation_area` input.

    The automation area is asked by Home Assistant in the popup that
    appears after pressing "Opslaan". Declaring it as a blueprint input
    would produce a duplicate "Ruimte" label in the UI.
    """
    path = _BLUEPRINT_DIR / "button_toggle.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    assert "area_id: !input automation_area" not in text, (
        "button_toggle.yaml must not expose `area_id: !input "
        "automation_area`. HA asks for the room in the popup after "
        "Opslaan — duplicating it as a blueprint input is confusing."
    )
    assert "automation_area" not in text, (
        "button_toggle.yaml must not declare an `automation_area` input "
        "at all (the field name leaks via the variable too)."
    )


def test_toggle_blueprint_uses_entity_selector_not_target() -> None:
    """`button_toggle.yaml` must use an `entity:` selector, not `target:`.

    The minimal toggle blueprint is for a single entity. A `target:`
    selector exposes the entity/device/area tabbladen, plus a
    "Doel toevoegen" button. Both are noise for the minimal use case.
    """
    path = _BLUEPRINT_DIR / "button_toggle.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # target_kind / target_area zijn verwijderd in de UX-fix.
    assert "target_kind" not in text, (
        "button_toggle.yaml must not have a target_kind field"
    )
    assert "target_area" not in text, (
        "button_toggle.yaml must not have a target_area field"
    )
    # Het enige target_entity-veld moet een entity-selector gebruiken,
    # niet een target-selector.
    assert "target: !input target_entity" not in text, (
        "button_toggle.yaml must not pass a target: !input to the action"
    )
    # De selector voor target_entity moet `entity:` zijn (niet `target:`).
    assert "selector:\n        entity:" in text, (
        "button_toggle.yaml must declare an `entity:` selector for the target"
    )


def test_toggle_blueprint_has_no_automation_name_input() -> None:
    """`button_toggle.yaml` declares no `automation_name` field or `alias:`.

    Removing the field lets the Home Assistant save popup fill in the
    alias, avoiding the mismatch between `automation_name` and the
    blueprint-name that the popup uses as default. Operators type the
    friendly name (e.g. "Keuken wandknop → Keuken LED") directly in
    the popup that appears after pressing "Opslaan".
    """
    path = _BLUEPRINT_DIR / "button_toggle.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    assert "automation_name" not in text, (
        "button_toggle.yaml must not declare an `automation_name` input. "
        "The Home Assistant save popup fills in the alias; declaring it "
        "as a blueprint input produces a confusing mismatch with the "
        "blueprint-name the popup uses as default."
    )
    # Geen `alias:` op het automation-niveau — laat de popup hem invullen.
    assert "alias: !input" not in text, (
        "button_toggle.yaml must not declare `alias: !input ...`. "
        "Let Home Assistant's save popup own the alias."
    )


def test_standard_blueprint_uses_target_selector() -> None:
    """`button_standard.yaml` must use a `target:` selector per phase.

    A `target:` selector lets the operator pick an entity, multiple
    entities, or an area in one widget. The older split between
    `press_entity_target` (target selector) and `press_area` (area
    selector) caused duplicate "Ruimte" labels in the UI.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # Per fase moet er een `press_target` / `long_press_target` zijn
    # met een target-selector.
    assert "press_target:" in text
    assert "long_press_target:" in text
    # Oude velden moeten weg zijn.
    for forbidden in (
        "press_target_kind",
        "press_entity_target",
        "press_area:",
        "long_press_target_kind",
        "long_press_entity_target",
        "long_press_area:",
    ):
        assert forbidden not in text, (
            f"button_standard.yaml must not declare `{forbidden}`; use the "
            "combined `*_target` field with a `target:` selector instead."
        )


def test_standard_blueprint_has_scene_guard() -> None:
    """`button_standard.yaml` must guard scene-targeted actions.

    A scene has no on/off/toggle state, so `on`/`off`/`toggle` actions
    must skip when the target contains a scene entity. Likewise,
    `activate_scene` must skip when the target has no scene entity.
    The blueprint must derive `*_has_scene` from the target and
    reference it in conditions.
    """
    path = _BLUEPRINT_DIR / "button_standard.yaml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    assert "press_has_scene" in text, (
        "button_standard.yaml must derive `press_has_scene` from the target"
    )
    assert "long_press_has_scene" in text, (
        "button_standard.yaml must derive `long_press_has_scene` from the target"
    )
    # On/off/toggle voor press mogen alleen lopen als er GEEN scene in zit.
    assert "press_action == 'on' and not press_has_scene" in text, (
        "press `on` must be guarded by `not press_has_scene`"
    )
    assert "press_action == 'off' and not press_has_scene" in text
    assert "press_action == 'toggle' and not press_has_scene" in text
    # activate_scene moet lopen als er WEL een scene in zit.
    assert (
        "press_action == 'activate_scene' and press_has_scene" in text
    ), "press `activate_scene` must be guarded by `press_has_scene`"


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
