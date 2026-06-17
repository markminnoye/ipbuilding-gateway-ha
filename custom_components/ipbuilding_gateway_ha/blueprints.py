"""Install packaged automation blueprints into the HA config folder.

Home Assistant only lists blueprints under ``config/blueprints/<domain>/``.
Files shipped inside ``custom_components/<domain>/blueprints/`` are not
scanned automatically; copy missing ones on first integration setup.
"""

from __future__ import annotations

import logging
import pathlib
import shutil

from homeassistant.components.blueprint.const import BLUEPRINT_FOLDER
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

log = logging.getLogger(__name__)

_BLUEPRINTS_SYNCED_KEY = "_blueprints_synced"


async def async_install_packaged_blueprints(hass: HomeAssistant) -> None:
    """Copy packaged automation blueprints that are not yet in config."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_BLUEPRINTS_SYNCED_KEY):
        return

    integration = await async_get_integration(hass, DOMAIN)
    source_root = pathlib.Path(integration.file_path) / BLUEPRINT_FOLDER / "automation"
    if not source_root.is_dir():
        domain_data[_BLUEPRINTS_SYNCED_KEY] = True
        return

    dest_root = pathlib.Path(hass.config.path(BLUEPRINT_FOLDER, "automation"))

    def _copy_missing() -> list[str]:
        copied: list[str] = []
        for src in source_root.glob("**/*.yaml"):
            rel = src.relative_to(source_root)
            dest = dest_root / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(str(rel))
        return copied

    copied = await hass.async_add_executor_job(_copy_missing)
    if copied:
        from homeassistant.components.automation.helpers import async_get_blueprints

        await async_get_blueprints(hass).async_reset_cache()
        log.info(
            "Installed %d packaged automation blueprint(s): %s",
            len(copied),
            ", ".join(copied),
        )

    domain_data[_BLUEPRINTS_SYNCED_KEY] = True
