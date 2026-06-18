"""Coordinator-less REST access to the gateway.

These helpers talk to the gateway purely over HTTP given a ``host`` + ``port``.
They are used by the config flow, where onboarding runs *before* the config
entry (and therefore the coordinator) exists, so the wizard can read devices,
modules and button configuration and trigger a discovery sweep without a
running :class:`IPBuildingCoordinator`.

All calls are best-effort: on any error they log at debug/warning and return an
empty result, so a slow or unreachable module never aborts onboarding.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=5)
_DISCOVER_TIMEOUT = aiohttp.ClientTimeout(total=120)


def _base(host: str, port: int) -> str:
    return f"http://{host}:{port}"


async def async_fetch_devices(host: str, port: int) -> list[dict[str, Any]]:
    """Return the flat per-channel/button device list (``GET /api/v1/devices``)."""
    url = f"{_base(host, port)}/api/v1/devices"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status != 200:
                    log.warning("REST devices returned %s", resp.status)
                    return []
                data = await resp.json()
                return list(data.get("devices", []) or [])
    except Exception as exc:
        log.debug("REST devices fetch failed: %s", exc)
        return []


async def async_fetch_modules(host: str, port: int) -> list[dict[str, Any]]:
    """Return the module list (``GET /api/v1/modules``)."""
    url = f"{_base(host, port)}/api/v1/modules"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status != 200:
                    log.warning("REST modules returned %s", resp.status)
                    return []
                data = await resp.json()
                return list(data.get("modules", []) or [])
    except Exception as exc:
        log.debug("REST modules fetch failed: %s", exc)
        return []


async def async_fetch_button_config(host: str, port: int) -> list[dict[str, Any]]:
    """Return a flat list of ``getButtons`` entries across all input modules.

    Mirrors :meth:`IPBuildingCoordinator.async_fetch_button_config`: each
    button dict is enriched with ``module_id`` and ``module_ip``.
    """
    modules = await async_fetch_modules(host, port)
    out: list[dict[str, Any]] = []
    for module in modules:
        if module.get("type") != "input":
            continue
        for btn in module.get("buttons") or []:
            enriched = dict(btn)
            enriched["module_id"] = module.get("id")
            enriched["module_ip"] = module.get("ip")
            out.append(enriched)
    return out


async def async_run_discover(host: str, port: int) -> dict[str, Any]:
    """Run a forced discovery sweep (``POST /api/v1/discover``).

    Returns the sweep summary; an empty/failed sweep yields ``ok=False``.
    """
    url = f"{_base(host, port)}/api/v1/discover"
    result: dict[str, Any] = {
        "ok": False,
        "added": [],
        "changed": [],
        "removed": [],
        "duration_ms": 0,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, timeout=_DISCOVER_TIMEOUT) as resp:
                if resp.status != 200:
                    log.warning("Discover sweep returned %s", resp.status)
                    return result
                payload = await resp.json()
                return {
                    "ok": bool(payload.get("ok")),
                    "added": list(payload.get("added") or []),
                    "changed": list(payload.get("changed") or []),
                    "removed": list(payload.get("removed") or []),
                    "duration_ms": int(payload.get("duration_ms") or 0),
                }
    except Exception as exc:
        log.warning("Discover sweep failed: %s", exc)
        return result


async def async_refresh_module_metadata(host: str, port: int) -> None:
    """Force the gateway to reload ``getSysSet``/``getButtons`` for all modules.

    ``POST /api/v1/modules/refresh`` populates the gateway's metadata cache so
    input-module buttons (and their rooms) appear in ``/api/v1/devices``.
    """
    url = f"{_base(host, port)}/api/v1/modules/refresh"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, timeout=_DISCOVER_TIMEOUT) as resp:
                if resp.status != 200:
                    log.warning("modules/refresh returned %s", resp.status)
    except Exception as exc:
        log.debug("modules/refresh failed: %s", exc)
