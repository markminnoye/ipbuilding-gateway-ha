"""Tests for packaged blueprint installation and upgrades.

Runtime tests require the ``homeassistant`` package (see other files in
this directory for the same pattern). When HA is not installed, all tests
in this file are skipped — the matching CI environment installs
``requirements-dev.txt``.

Source-level checks for the version-header format on every shipped
blueprint live in ``test_blueprints_source.py`` and run unconditionally.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ha = pytest.importorskip("homeassistant")

from custom_components.ipbuilding_gateway_ha.blueprints import (  # noqa: E402
    async_install_packaged_blueprints,
    invalidate_packaged_blueprints_cache,
)


def _make_hass(source_root: Path) -> MagicMock:
    hass = MagicMock()
    hass.data = {"ipbuilding_gateway_ha": {}}
    integration = MagicMock()
    integration.file_path = str(source_root.parent.parent)
    assert (
        source_root
        == Path(integration.file_path) / "blueprints" / "automation"
    )

    async_get_blueprints = AsyncMock()
    async_get_blueprints.return_value.async_reset_cache = AsyncMock()

    hass._bp_test_patches = [
        patch(
            "custom_components.ipbuilding_gateway_ha.blueprints.async_get_integration",
            AsyncMock(return_value=integration),
        ),
        patch(
            "homeassistant.components.automation.helpers.async_get_blueprints",
            async_get_blueprints,
        ),
    ]
    for p in hass._bp_test_patches:
        p.start()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda func, *a: func(*a))
    hass._bp_test_reset_cache = async_get_blueprints.return_value.async_reset_cache
    return hass


def _cleanup_hass(hass: MagicMock) -> None:
    for p in hass._bp_test_patches:
        p.stop()


def _write_blueprint(path: Path, *, version: int | None) -> None:
    if version is None:
        path.write_text("blueprint:\n  name: legacy\n  domain: automation\n")
        return
    path.write_text(
        f"# ipbuilding_blueprint_version: {version}\n"
        "blueprint:\n  name: v" + str(version) + "\n  domain: automation\n"
    )


def _source_root(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "custom_components"
        / "ipbuilding_gateway_ha"
        / "blueprints"
        / "automation"
        / "ipbuilding_gateway_ha"
    )


def _dest_root_for(tmp_path: Path) -> Path:
    return tmp_path / "blueprints" / "automation"


@pytest.mark.asyncio
async def test_install_packaged_blueprints_copies_missing_files(
    tmp_path: Path,
) -> None:
    """Missing blueprint YAML files are copied into config/blueprints/automation/."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "dim_button.yaml", version=2)
    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        dest_file = (
            _dest_root_for(tmp_path)
            / "ipbuilding_gateway_ha"
            / "dim_button.yaml"
        )
        assert dest_file.is_file()
        assert dest_file.read_text().startswith("# ipbuilding_blueprint_version: 2")
        hass._bp_test_reset_cache.assert_awaited_once()
        assert hass.data["ipbuilding_gateway_ha"]["_blueprint_versions"] == {
            "ipbuilding_gateway_ha/dim_button.yaml": 2
        }
    finally:
        _cleanup_hass(hass)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_upgrades_when_newer_version(
    tmp_path: Path,
) -> None:
    """A packaged blueprint with a higher version overwrites the destination."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "dim_button.yaml", version=3)

    dest_root = _dest_root_for(tmp_path) / "ipbuilding_gateway_ha"
    dest_root.mkdir(parents=True)
    _write_blueprint(dest_root / "dim_button.yaml", version=2)

    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        dest_file = dest_root / "dim_button.yaml"
        assert dest_file.read_text().startswith("# ipbuilding_blueprint_version: 3")
        assert hass.data["ipbuilding_gateway_ha"]["_blueprint_versions"] == {
            "ipbuilding_gateway_ha/dim_button.yaml": 3
        }
    finally:
        _cleanup_hass(hass)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_skips_user_modified(
    tmp_path: Path,
) -> None:
    """Destination files with the ``user_modified`` marker are left untouched."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "dim_button.yaml", version=3)

    dest_root = _dest_root_for(tmp_path) / "ipbuilding_gateway_ha"
    dest_root.mkdir(parents=True)
    dest_file = dest_root / "dim_button.yaml"
    dest_file.write_text(
        "# ipbuilding_blueprint_version: 2\n"
        "# user_modified: true\n"
        "blueprint:\n  name: custom\n"
    )

    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        assert dest_file.read_text() == (
            "# ipbuilding_blueprint_version: 2\n"
            "# user_modified: true\n"
            "blueprint:\n  name: custom\n"
        )
    finally:
        _cleanup_hass(hass)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_skips_when_destination_newer(
    tmp_path: Path,
) -> None:
    """When the destination already has a newer version, leave it alone."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "dim_button.yaml", version=2)

    dest_root = _dest_root_for(tmp_path) / "ipbuilding_gateway_ha"
    dest_root.mkdir(parents=True)
    dest_file = dest_root / "dim_button.yaml"
    _write_blueprint(dest_file, version=3)

    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        assert dest_file.read_text().startswith("# ipbuilding_blueprint_version: 3")
        hass._bp_test_reset_cache.assert_not_awaited()
    finally:
        _cleanup_hass(hass)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_skips_when_same_version(
    tmp_path: Path,
) -> None:
    """Same version on both sides → no copy, no upgrade, no cache reset."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "dim_button.yaml", version=2)

    dest_root = _dest_root_for(tmp_path) / "ipbuilding_gateway_ha"
    dest_root.mkdir(parents=True)
    dest_file = dest_root / "dim_button.yaml"
    _write_blueprint(dest_file, version=2)

    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        assert dest_file.read_text().startswith("# ipbuilding_blueprint_version: 2")
        hass._bp_test_reset_cache.assert_not_awaited()
    finally:
        _cleanup_hass(hass)


@pytest.mark.asyncio
async def test_install_packaged_blueprints_copies_legacy_files_without_version(
    tmp_path: Path,
) -> None:
    """Package files that pre-date the version header still copy cleanly."""
    source_root = _source_root(tmp_path)
    source_root.mkdir(parents=True)
    _write_blueprint(source_root / "legacy.yaml", version=None)
    hass = _make_hass(source_root)
    try:
        await async_install_packaged_blueprints(hass)
        dest_file = (
            _dest_root_for(tmp_path) / "ipbuilding_gateway_ha" / "legacy.yaml"
        )
        assert dest_file.is_file()
        assert "ipbuilding_blueprint_version" not in dest_file.read_text()
    finally:
        _cleanup_hass(hass)


def test_invalidate_cache_forces_re_sync() -> None:
    """invalidate_packaged_blueprints_cache drops the cached version map."""
    hass = MagicMock()
    hass.data = {
        "ipbuilding_gateway_ha": {
            "_blueprint_versions": {"ipbuilding_gateway_ha/dim_button.yaml": 2}
        }
    }
    invalidate_packaged_blueprints_cache(hass)
    assert "_blueprint_versions" not in hass.data["ipbuilding_gateway_ha"]
