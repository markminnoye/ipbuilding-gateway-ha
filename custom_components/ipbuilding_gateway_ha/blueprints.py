"""Install and upgrade packaged automation blueprints into the HA config folder.

Home Assistant only lists blueprints under ``config/blueprints/<domain>/``.
Files shipped inside ``custom_components/<domain>/blueprints/`` are not
scanned automatically; copy missing ones on first integration setup, and
upgrade existing ones when the packaged blueprint ships a newer version.

Each packaged blueprint carries a header comment of the form
``# ipbuilding_blueprint_version: N`` (bumped per release). The companion
compares that version with the destination file and overwrites when the
package is newer. Operators that hand-edit a packaged blueprint can add
a ``# user_modified: true`` marker to opt out of automatic upgrades — the
companion logs a warning but leaves the file alone.
"""

from __future__ import annotations

import logging
import pathlib
import re
import shutil

from homeassistant.components.blueprint.const import BLUEPRINT_FOLDER
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

log = logging.getLogger(__name__)

# Per-package-run cache key. When the package version advances the entry
# setup forces a re-sync by invalidating this key.
_BLUEPRINT_SYNC_KEY = "_blueprint_versions"

_USER_MODIFIED_MARKER = "user_modified: true"
_VERSION_HEADER_RE = re.compile(r"^\s*#\s*ipbuilding_blueprint_version:\s*(\d+)\s*$")


def _read_blueprint_version(path: pathlib.Path) -> int | None:
    """Return the version embedded in the first lines of the YAML.

    Returns ``None`` when the marker is absent (legacy packaged blueprints
    before versioning was introduced, or user-authored files).
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            for _ in range(20):
                line = handle.readline()
                if not line:
                    break
                match = _VERSION_HEADER_RE.match(line)
                if match:
                    return int(match.group(1))
    except OSError:
        return None
    return None


def _has_user_modified_marker(path: pathlib.Path) -> bool:
    """Detect the ``# user_modified: true`` opt-out marker."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            head = handle.read(2048)
    except OSError:
        return False
    return _USER_MODIFIED_MARKER in head


async def async_install_packaged_blueprints(hass: HomeAssistant) -> None:
    """Copy or upgrade packaged automation blueprints into the config folder.

    Sync rules per blueprint:

    - Destination missing → copy from package.
    - Package has a newer version than destination → overwrite (when the
      destination does not carry a ``user_modified: true`` marker).
    - Destination has a marker → skip + log warning.
    - Destination is already at the same or newer version → skip.

    A cache key in ``hass.data[DOMAIN]`` tracks which versions are currently
    installed. The caller is expected to call this from
    :func:`async_setup_entry`; the key is invalidated automatically when
    the package ``sw_version`` advances so that reloading the entry after
    a companion upgrade re-runs the sync.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    integration = await async_get_integration(hass, DOMAIN)
    source_root = pathlib.Path(integration.file_path) / BLUEPRINT_FOLDER / "automation"
    if not source_root.is_dir():
        domain_data[_BLUEPRINT_SYNC_KEY] = {}
        return

    dest_root = pathlib.Path(hass.config.path(BLUEPRINT_FOLDER, "automation"))

    def _sync() -> dict[str, dict[str, object]]:
        synced: dict[str, dict[str, object]] = {}
        for src in source_root.glob("**/*.yaml"):
            rel = src.relative_to(source_root)
            dest = dest_root / rel
            synced[str(rel)] = _sync_one(src, dest)
        return synced

    synced = await hass.async_add_executor_job(_sync)

    copied = [rel for rel, info in synced.items() if info.get("action") == "copied"]
    upgraded = [rel for rel, info in synced.items() if info.get("action") == "upgraded"]
    skipped_user = [
        rel for rel, info in synced.items() if info.get("action") == "skipped_user_modified"
    ]

    if copied or upgraded or skipped_user:
        from homeassistant.components.automation.helpers import async_get_blueprints

        await async_get_blueprints(hass).async_reset_cache()
        if copied:
            log.info(
                "Installed %d packaged automation blueprint(s): %s",
                len(copied),
                ", ".join(copied),
            )
        if upgraded:
            log.info(
                "Upgraded %d packaged automation blueprint(s): %s",
                len(upgraded),
                ", ".join(upgraded),
            )
        if skipped_user:
            log.warning(
                "Skipped %d packaged automation blueprint(s) marked user_modified: %s",
                len(skipped_user),
                ", ".join(skipped_user),
            )

    domain_data[_BLUEPRINT_SYNC_KEY] = {
        rel: info.get("version", 0) for rel, info in synced.items()
    }


def _sync_one(src: pathlib.Path, dest: pathlib.Path) -> dict[str, object]:
    """Apply the versioned copy/upgrade/skip rules for a single blueprint."""
    pkg_version = _read_blueprint_version(src)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return {"action": "copied", "version": pkg_version}

    if _has_user_modified_marker(dest):
        return {
            "action": "skipped_user_modified",
            "version": _read_blueprint_version(dest),
        }

    dest_version = _read_blueprint_version(dest)
    if pkg_version is not None and (
        dest_version is None or pkg_version > dest_version
    ):
        shutil.copy2(src, dest)
        return {"action": "upgraded", "version": pkg_version}

    return {"action": "skipped", "version": dest_version or pkg_version}


def invalidate_packaged_blueprints_cache(hass: HomeAssistant) -> None:
    """Drop the cached sync state so the next setup re-runs the upgrade check.

    Call from entry update listeners when the integration ``sw_version``
    changes so companion upgrades are picked up without a full HA restart.
    """
    domain_data = hass.data.get(DOMAIN)
    if isinstance(domain_data, dict):
        domain_data.pop(_BLUEPRINT_SYNC_KEY, None)
