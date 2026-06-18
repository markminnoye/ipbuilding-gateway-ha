"""Source-level tests for IPBuildingEventButton entity-id handling.

Verifies the entity-id derivation rule from plan \u00a711:

  HA Core's ``_async_derive_object_ids`` honours
  ``Entity.internal_integration_suggested_object_id`` literally.
  We set that attribute to the raw hardware id (e.g. ``"2f8185190000df"``)
  so the resulting entity_id is ``event.<hardware_id>`` instead of
  ``button.<sluggified-name>``.

These tests inspect the source of ``event.py`` directly so they run
without a real Home Assistant install. Runtime tests for the same
invariant live in ``test_event_entity_id_runtime.py`` and require the
``homeassistant`` package; they are skipped otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"
_EVENT_SOURCE = (_COMP_DIR / "event.py").read_text()


def test_event_source_assigns_suggested_object_id_to_hardware_id():
    """The v0.4.0-rc.2 fix is the single line
    ``self.internal_integration_suggested_object_id = self._hardware_id``
    inside ``IPBuildingEventButton.__init__``.

    This textual check catches the regression where the line is
    accidentally removed during a refactor - even before any runtime
    tests get a chance to run.
    """
    pattern = re.compile(
        r"self\.internal_integration_suggested_object_id\s*=\s*self\._hardware_id"
    )
    assert pattern.search(_EVENT_SOURCE), (
        "event.py must assign "
        "`self.internal_integration_suggested_object_id = self._hardware_id` "
        "inside IPBuildingEventButton.__init__. This is the v0.4.0-rc.2 "
        "entity-id fix."
    )


def test_unique_id_pattern_unchanged():
    """Backwards-compat: the unique_id pattern stays
    ``event_<hardware_id>`` so the HA entity-registry reconciles the
    new event-platform entries with the historical button-platform
    entries on next startup.
    """
    pattern = re.compile(
        r'self\._attr_unique_id\s*=\s*f"event_\{hardware_id\}"'
    )
    assert pattern.search(_EVENT_SOURCE), (
        "event.py must keep "
        '`self._attr_unique_id = f"event_{hardware_id}"` for entity-registry '
        "backwards-compat."
    )


def test_event_py_uses_event_platform_modules():
    """The companion file that registers physical button entities must
    use the ``event`` platform, not the ``button`` one - HA Core
    derives the entity-domain from the source file name.

    This guard catches accidental re-renames back to ``button.py``
    that would re-introduce the v0.4.0-rc.1 bug (entities get a
    ``button.`` prefix and ``button.press`` service calls fail with
    ``'IPBuildingEventButton' object has no attribute
    '_async_press_action'``).
    """
    # event.py must import from homeassistant.components.event (not
    # .button) and must NOT define ButtonEntity - it should define
    # EventEntity only.
    assert "from homeassistant.components.event import" in _EVENT_SOURCE, (
        "event.py must import from homeassistant.components.event - if you "
        "renamed it back to button.py the entities would re-register as "
        "button.* instead of event.*."
    )
    assert "from homeassistant.components.button import" not in _EVENT_SOURCE, (
        "event.py must not import from homeassistant.components.button - "
        "the physical button entities are EventEntity, not ButtonEntity."
    )
    assert "class IPBuildingEventButton(EventEntity" in _EVENT_SOURCE, (
        "IPBuildingEventButton must extend EventEntity, not ButtonEntity."
    )
