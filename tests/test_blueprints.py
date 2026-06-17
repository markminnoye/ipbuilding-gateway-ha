"""Tests for packaged blueprint installation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ipbuilding_gateway_ha.blueprints import (
    async_install_packaged_blueprints,
)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_copies_missing_files(
    tmp_path: Path,
) -> None:
    """Missing blueprint YAML files are copied into config/blueprints/automation/."""
    source_root = (
        tmp_path
        / "custom_components"
        / "ipbuilding_gateway_ha"
        / "blueprints"
        / "automation"
        / "ipbuilding_gateway_ha"
    )
    source_root.mkdir(parents=True)
    blueprint_src = source_root / "dim_button.yaml"
    blueprint_src.write_text("blueprint:\n  name: test\n  domain: automation\n")

    dest_root = tmp_path / "blueprints" / "automation"
    hass = MagicMock()
    hass.data = {"ipbuilding_gateway_ha": {}}
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))

    integration = MagicMock()
    integration.file_path = str(
        tmp_path / "custom_components" / "ipbuilding_gateway_ha"
    )

    async_get_blueprints = AsyncMock()
    async_get_blueprints.return_value.async_reset_cache = AsyncMock()

    with (
        patch(
            "custom_components.ipbuilding_gateway_ha.blueprints.async_get_integration",
            AsyncMock(return_value=integration),
        ),
        patch(
            "homeassistant.components.automation.helpers.async_get_blueprints",
            async_get_blueprints,
        ),
    ):
        hass.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args: func(*args)
        )
        await async_install_packaged_blueprints(hass)

    dest_file = dest_root / "ipbuilding_gateway_ha" / "dim_button.yaml"
    assert dest_file.is_file()
    assert dest_file.read_text() == blueprint_src.read_text()
    async_get_blueprints.return_value.async_reset_cache.assert_awaited_once()
    assert hass.data["ipbuilding_gateway_ha"]["_blueprints_synced"] is True

    await async_install_packaged_blueprints(hass)
    assert hass.async_add_executor_job.await_count == 1


@pytest.mark.asyncio
async def test_install_packaged_blueprints_skips_existing_files(
    tmp_path: Path,
) -> None:
    """Existing destination files are left untouched."""
    source_root = (
        tmp_path
        / "custom_components"
        / "ipbuilding_gateway_ha"
        / "blueprints"
        / "automation"
        / "ipbuilding_gateway_ha"
    )
    source_root.mkdir(parents=True)
    (source_root / "dim_button.yaml").write_text("blueprint:\n  name: new\n")

    dest_root = tmp_path / "blueprints" / "automation" / "ipbuilding_gateway_ha"
    dest_root.mkdir(parents=True)
    dest_file = dest_root / "dim_button.yaml"
    dest_file.write_text("blueprint:\n  name: old\n")

    hass = MagicMock()
    hass.data = {"ipbuilding_gateway_ha": {}}
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))

    integration = MagicMock()
    integration.file_path = str(
        tmp_path / "custom_components" / "ipbuilding_gateway_ha"
    )

    with patch(
        "custom_components.ipbuilding_gateway_ha.blueprints.async_get_integration",
        AsyncMock(return_value=integration),
    ):
        hass.async_add_executor_job = AsyncMock(
            side_effect=lambda func, *args: func(*args)
        )
        await async_install_packaged_blueprints(hass)

    assert dest_file.read_text() == "blueprint:\n  name: old\n"
