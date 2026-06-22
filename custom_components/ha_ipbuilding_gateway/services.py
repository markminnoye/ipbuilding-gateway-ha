"""Hold-to-dim ramp services.

The companion registers two entity-targeted services that drive the native
``D<ch>001003`` / ``D<ch>001000`` ramp wire dialect:

- ``ha_ipbuilding_gateway.dim_start`` — start a continuous ramp on a
  companion light entity backed by an IP0300PoE channel. Sends the gateway
  action ``DIM_START``; the dimmer ramps and auto-reverses on each
  successive hold.
- ``ha_ipbuilding_gateway.dim_stop`` — stop the ramp. Sends ``DIM_STOP``;
  the dimmer replies with the level reached on release.

Both services use the standard HA ``target:`` selector (a ``light.`` entity).
The companion resolves the HA entity_id to the gateway device_id through the
entity registry so the action reaches the right IP0300PoE channel.

The ``light.toggle`` action on a companion dimmer entity is intentionally
left on the standard HA ``light`` platform — there is no native gateway
``TOGGLE`` routing from the light platform; it dispatches ``DIM 0`` / a
non-zero level depending on the current state. Operators that want the
single-wire ``T<ch>991000`` toggle (matching IPBox button-press semantics)
can wire a service call themselves, but the blueprint path uses the
``single_press → light.toggle`` flow for free.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids

from .const import DOMAIN

log = logging.getLogger(__name__)

# Entity-targeted services. ``make_entity_service_schema`` accepts the
# standard ``target:`` payload (entity_id / device_id / area_id) and requires
# at least one target — this matches the blueprint's ``target: entity_id:``
# call and is resolved to concrete entities by ``async_extract_entity_ids``.
_SERVICE_SCHEMA = cv.make_entity_service_schema({})


async def _resolve_device_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Map a ``light.<entity_id>`` HA id back to the gateway device_id.

    The companion's light entities set ``unique_id = device["id"]`` where
    ``device["id"]`` is the gateway device_id (e.g. ``10.10.1.40-1``). The
    entity registry lets us look up an entity by HA id and read its
    ``unique_id``. Returns None for entities that do not belong to this
    integration.
    """
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        return None
    return entry.unique_id


async def _dispatch(
    hass: HomeAssistant, coordinator: Any, action: str, call: ServiceCall
) -> None:
    """Resolve every targeted entity and send ``action`` to the gateway."""
    entity_ids = await async_extract_entity_ids(hass, call)
    if not entity_ids:
        raise HomeAssistantError(f"{action}: no target entity")
    for entity_id in entity_ids:
        device_id = await _resolve_device_id(hass, entity_id)
        if device_id is None:
            raise HomeAssistantError(
                f"{entity_id} is not a ha_ipbuilding_gateway dimmer channel"
            )
        ok = await coordinator.async_send_command(device_id, action)
        if not ok:
            raise HomeAssistantError(
                f"Gateway rejected {action} on {device_id} (WS disconnected?)"
            )


def async_register_services(hass: HomeAssistant, coordinator: Any) -> None:
    """Register the dim_start / dim_stop services on the hass instance.

    The handlers are real coroutine functions (closing over ``hass`` and the
    ``coordinator``) so Home Assistant awaits them — a sync lambda returning a
    coroutine would be classified as a callback/executor job and the coroutine
    would never be awaited.

    Idempotent: the second call (e.g. on integration reload that did not
    unload services first) is a no-op so we do not blow up with
    ``InvalidServiceId``.
    """
    if hass.services.has_service(DOMAIN, "dim_start"):
        return

    async def _dim_start(call: ServiceCall) -> None:
        await _dispatch(hass, coordinator, "DIM_START", call)

    async def _dim_stop(call: ServiceCall) -> None:
        await _dispatch(hass, coordinator, "DIM_STOP", call)

    hass.services.async_register(
        DOMAIN, "dim_start", _dim_start, schema=_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "dim_stop", _dim_stop, schema=_SERVICE_SCHEMA
    )
    log.info("Registered ha_ipbuilding_gateway dim_start / dim_stop services")


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove dim_start / dim_stop on integration unload."""
    hass.services.async_remove(DOMAIN, "dim_start")
    hass.services.async_remove(DOMAIN, "dim_stop")
