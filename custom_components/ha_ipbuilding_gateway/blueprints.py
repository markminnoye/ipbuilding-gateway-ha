"""Sync packaged automation blueprints into the HA config folder.

Historically this module copied ``custom_components/<domain>/blueprints/``
files into the operator's ``config/blueprints/automation/`` folder so
they appeared in Home Assistant's Blueprint picker. As of
``v0.4.0-rc.11`` the companion no longer ships those blueprints to
operators — see CHANGELOG and README for the rationale and migration
path. The public functions are kept as no-ops so existing call sites
(``async_setup_entry``) keep working without modification.

The packaged blueprint YAML files still live in the repo for reference,
for tests, and for future re-introduction. The source-only tests in
``tests/test_blueprints_source.py`` still validate their structure.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN

log = logging.getLogger(__name__)


async def async_install_packaged_blueprints(hass: HomeAssistant) -> None:
    """No-op since v0.4.0-rc.11.

    Previously this copied packaged blueprints into the operator's
    ``config/blueprints/automation/ha_ipbuilding_gateway/`` folder.
    Operators now build their button automations via community
    blueprints, the standard HA UI flow, or the raw YAML in this
    repository as a reference. See README for details.
    """
    log.debug(
        "async_install_packaged_blueprints is a no-op since v0.4.0-rc.11; "
        "the companion no longer ships automation blueprints to operators."
    )
    hass.data.setdefault(DOMAIN, {})


def invalidate_packaged_blueprints_cache(hass: HomeAssistant) -> None:
    """No-op since v0.4.0-rc.11. Kept for backward compatibility."""
    return None
