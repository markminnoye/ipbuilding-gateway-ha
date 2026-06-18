"""Unit tests for ``coordinator.devices_snapshot()`` and the REST-fallback cache.

The companion's entity bootstrap path was broken in 0.3.7: the REST fallback
returned a list while the four platforms (light/switch/sensor/button) read
``coordinator.data`` as a dict, so only the three module devices were ever
created. The fix gives the platforms a canonical ``devices_snapshot()`` and
also makes ``_async_update_data`` populate the internal ``_data`` dict so
both code paths agree.

These tests are pure-Python: they instantiate a real ``IPBuildingCoordinator``
(without the WebSocket) and assert the cache contract that the platforms
depend on.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal Home Assistant + aiohttp stub. The companion imports a lot of HA
# modules transitively; we only need the bits the coordinator uses.
# ---------------------------------------------------------------------------


class _StubDataUpdateCoordinator:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def async_config_entry_first_refresh(self) -> None:
        return None

    def __class_getitem__(cls, _item):
        return cls


class _StubConfigEntry:
    def __init__(self) -> None:
        self.data: dict = {}


class _StubHomeAssistant:
    pass


def _ensure_stub(name: str, **attrs) -> types.ModuleType:
    """Register a stub module at ``name`` if no real one is importable."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _ensure_stub_package(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if not isinstance(mod, types.ModuleType) or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = mod
    return mod


# Top-level ``homeassistant`` is sometimes a real package (when a sibling test
# imported it). We don't replace it; we only make sure the submodules the
# coordinator imports are stubbed, so even a "real" parent without those
# submodules satisfies the import.
_ensure_stub("homeassistant.const", CONF_HOST="host", CONF_PORT="port")
_ensure_stub_package("homeassistant.helpers")
_ensure_stub(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_StubDataUpdateCoordinator,
)
_ensure_stub("homeassistant.config_entries", ConfigEntry=_StubConfigEntry)
_ensure_stub("homeassistant.core", HomeAssistant=_StubHomeAssistant)

# aiohttp is needed for ``IPBuildingCoordinator`` imports.
_ensure_stub(
    "aiohttp",
    ClientWebSocketResponse=object,
    ClientSession=object,
    ClientConnectionError=type("ClientConnectionError", (Exception,), {}),
    ClientTimeout=lambda total=None: None,
    WSMsgType=types.SimpleNamespace(
        TEXT="text", CLOSE="close", CLOSED="closed", ERROR="error"
    ),
)

_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"

# Build a synthetic package so ``from .const import`` resolves. Pytest may
# import this test module more than once; always rebind the parent and
# (re)load the submodules so the coordinator surface is current.
_pkg = sys.modules.get("ha_ipbuilding_gateway")
if not isinstance(_pkg, types.ModuleType) or not hasattr(_pkg, "__path__"):
    _pkg = types.ModuleType("ha_ipbuilding_gateway")
    sys.modules["ha_ipbuilding_gateway"] = _pkg
_pkg.__path__ = [str(_COMP_DIR)]  # type: ignore[attr-defined]

for _name in ("const", "coordinator"):
    _spec = importlib.util.spec_from_file_location(
        f"ha_ipbuilding_gateway.{_name}", _COMP_DIR / f"{_name}.py"
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)  # type: ignore[union-attr]

coordinator_mod = sys.modules["ha_ipbuilding_gateway.coordinator"]


def _build_coordinator(*, data: list | dict | None = None):
    """Construct a coordinator without going through ``__init__`` networking."""
    coord = coordinator_mod.IPBuildingCoordinator.__new__(
        coordinator_mod.IPBuildingCoordinator
    )
    # Bypass DataUpdateCoordinator.__init__ to keep the test independent of
    # HA's runtime; we only care about the public surface the platforms use.
    coord._data = {}
    coord._modules = {}
    coord._known_devices = set()
    # ``_async_update_data`` builds the REST URL from these; they are only
    # read, never connected to.
    coord._host = "127.0.0.1"
    coord._port = 8080
    if data is None:
        coord.data = None
    elif isinstance(data, list):
        # Pre-fix behaviour: REST fallback left ``data`` as a list.
        coord.data = data
    else:
        # Post-fix behaviour: REST fallback stores a dict keyed by id.
        coord.data = data
    return coord


def test_devices_snapshot_falls_back_to_legacy_data_list():
    """When ``data`` is still a list (no WS or REST refresh), snapshot returns it."""
    legacy = [
        {"id": "10.10.1.30-0", "semantic_type": "light", "device_type": "relay"},
        {"id": "10.10.1.40-0", "semantic_type": "light", "device_type": "dimmer"},
    ]
    coord = _build_coordinator(data=legacy)

    snapshot = coord.devices_snapshot()
    assert [d["id"] for d in snapshot] == ["10.10.1.30-0", "10.10.1.40-0"]


def test_devices_snapshot_prefers_ws_cache():
    """The internal ``_data`` dict (WS path) wins over the public ``data`` list."""
    coord = _build_coordinator(data=[])  # public data empty
    coord._data = {
        "10.10.1.30-0": {"id": "10.10.1.30-0", "state": "on"},
        "10.10.1.40-0": {"id": "10.10.1.40-0", "state": "off"},
    }

    snapshot = coord.devices_snapshot()
    assert [d["id"] for d in snapshot] == ["10.10.1.30-0", "10.10.1.40-0"]


def test_devices_snapshot_handles_empty_caches():
    """A coordinator with no devices returns an empty list, never raises."""
    coord = _build_coordinator(data=[])

    assert coord.devices_snapshot() == []


def test_async_update_data_populates_data_dict(monkeypatch):
    """The REST fallback must cache by id and return a dict, not a list.

    The platforms consume ``devices_snapshot()`` / ``coordinator.data`` at
    setup time; if the REST path leaves ``data`` as a list, those four
    platform loops iterate over an empty dict and zero entities get added.
    """
    coord = _build_coordinator(data=[])

    # Stub out the aiohttp call: return a fixed JSON body.
    class _StubSession:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_StubSession":
            return self

        async def __aexit__(self, *args) -> None:
            return None

        def get(self, url, timeout=None):
            return _StubResponse()

    class _StubResponse:
        status = 200

        async def __aenter__(self) -> "_StubResponse":
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def json(self) -> dict:
            return {
                "devices": [
                    {"id": "10.10.1.30-0", "state": "off"},
                    {"id": "10.10.1.40-0", "state": "on"},
                    # An entry without an ``id`` must be filtered out.
                    {"state": "ignored"},
                ]
            }

    async def _noop() -> None:
        return None

    monkeypatch.setattr(coordinator_mod.aiohttp, "ClientSession", _StubSession)
    monkeypatch.setattr(coord, "async_fetch_gateway_status", _noop)
    monkeypatch.setattr(coord, "async_fetch_modules", _noop)

    import asyncio

    result = asyncio.run(coord._async_update_data())

    # Returned value is a dict (matches the post-fix contract and the type
    # hint ``dict[str, Any]``).
    assert isinstance(result, dict)
    # And the internal cache is keyed by id so the WS-handler contract is
    # mirrored on the REST path.
    assert set(result.keys()) == {"10.10.1.30-0", "10.10.1.40-0"}
    assert coord._data == result


def test_async_update_data_failure_leaves_data_dict():
    """A failed REST fetch returns an empty dict and clears stale cache entries."""
    coord = _build_coordinator(data=[])
    coord._data = {"stale": {"id": "stale"}}

    class _RaisingSession:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_RaisingSession":
            return self

        async def __aexit__(self, *args) -> None:
            return None

        def get(self, url, timeout=None):
            raise RuntimeError("boom")

    async def _noop() -> None:
        return None

    import asyncio

    import pytest

    coordinator_mod.aiohttp.ClientSession = _RaisingSession
    coord.async_fetch_gateway_status = _noop  # type: ignore[method-assign]
    coord.async_fetch_modules = _noop  # type: ignore[method-assign]

    result = asyncio.run(coord._async_update_data())

    assert result == {}
    assert coord._data == {}
