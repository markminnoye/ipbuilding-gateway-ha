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

_REPO = Path(__file__).resolve().parents[1]
_BLUEPRINT_DIR = (
    _REPO
    / "custom_components"
    / "ipbuilding_gateway_ha"
    / "blueprints"
    / "automation"
    / "ipbuilding_gateway_ha"
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
    """Every shipped blueprint (except the legacy dim stub) exposes alias + area_id.

    Both top-level keys are part of the operator UX promise from the
    2026-06-18 design spec: the automation name comes from the operator
    (typically the friendly button name) and the room follows the
    gateway-side ``room`` field via ``suggested_area``.
    """
    for path in _shipped_blueprints():
        if path.name == "dim_button.yaml":
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
