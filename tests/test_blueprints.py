"""Tests for the packaged-blueprint sync.

As of ``v0.4.0-rc.11`` the companion no longer ships automation
blueprints to operators. ``async_install_packaged_blueprints`` is a
no-op that just logs a debug message and initialises the
``hass.data[DOMAIN]`` map.

This file keeps the historical import — ``async_install_packaged_blueprints``
and ``invalidate_packaged_blueprints_cache`` are part of the public API
and must remain importable even though their bodies are no-ops.

Source-level checks for the version-header format on every shipped
blueprint live in ``test_blueprints_source.py`` and run unconditionally.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

ha = pytest.importorskip("homeassistant")

from custom_components.ha_ipbuilding_gateway.blueprints import (  # noqa: E402
    async_install_packaged_blueprints,
    invalidate_packaged_blueprints_cache,
)
from custom_components.ha_ipbuilding_gateway.const import DOMAIN  # noqa: E402


@pytest.mark.asyncio
async def test_install_packaged_blueprints_is_noop(tmp_path, caplog) -> None:
    """The sync does not touch the filesystem in any way.

    Previously this copied packaged blueprints from
    ``custom_components/<domain>/blueprints/automation/`` into the
    operator's ``config/blueprints/automation/`` folder. Since
    ``v0.4.0-rc.11`` it is a no-op — operators build their own button
    automations via community blueprints or the standard HA flow.
    """
    source_root = (
        tmp_path
        / "custom_components"
        / "ha_ipbuilding_gateway"
        / "blueprints"
        / "automation"
        / "ha_ipbuilding_gateway"
    )
    source_root.mkdir(parents=True)
    (source_root / "button_dim.yaml").write_text(
        "# ipbuilding_blueprint_version: 5\n"
        "blueprint:\n  name: shipped\n  domain: automation\n"
    )

    dest_root = tmp_path / "blueprints" / "automation" / "ha_ipbuilding_gateway"

    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))

    import logging
    with caplog.at_level(logging.DEBUG, logger="custom_components.ha_ipbuilding_gateway.blueprints"):
        await async_install_packaged_blueprints(hass)

    # The destination directory is NOT created; no files are written.
    assert not dest_root.exists(), (
        f"async_install_packaged_blueprints must not create {dest_root}; "
        "the companion no longer ships blueprints to operators."
    )
    assert "no-op since v0.4.0-rc.11" in caplog.text


@pytest.mark.asyncio
async def test_install_packaged_blueprints_initialises_domain_data() -> None:
    """The no-op still initialises ``hass.data[DOMAIN]`` for downstream callers."""
    hass = MagicMock()
    hass.data = {}

    await async_install_packaged_blueprints(hass)

    assert DOMAIN in hass.data
    assert hass.data[DOMAIN] == {}


def test_invalidate_packaged_blueprints_cache_is_noop() -> None:
    """``invalidate_packaged_blueprints_cache`` is a no-op kept for compatibility."""
    hass = MagicMock()
    hass.data = {DOMAIN: {"_blueprint_versions": {"x": 1}}}

    # Must not raise, must not mutate.
    invalidate_packaged_blueprints_cache(hass)
    assert hass.data[DOMAIN] == {"_blueprint_versions": {"x": 1}}
