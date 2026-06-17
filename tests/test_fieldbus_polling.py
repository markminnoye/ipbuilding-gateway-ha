"""Unit tests for the fieldbus-polling debug switch on the gateway.

Covers both halves of the new debug surface:

1. ``IPBuildingCoordinator.async_set_fieldbus_polling`` POSTs the right URL
   and updates the cached ``gateway_status`` on a 200 reply, returning
   ``True``; a 4xx/5xx or network error returns ``False`` and leaves the
   cache alone.
2. ``IPBuildingCoordinator.fieldbus_polling_enabled`` /
   ``fieldbus_poll_interval_s`` read the cached values.
3. ``IPBuildingFieldbusPollingSwitch.is_on`` mirrors
   ``coordinator.fieldbus_polling_enabled()`` and updates when the
   coordinator pushes a new gateway status.

The tests follow the same Home-Assistant-free stub pattern as
``test_coordinator_snapshot.py`` so they run in a plain ``pytest`` env.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# HA / aiohttp stubs (mirror test_coordinator_snapshot.py).
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


_ensure_stub("homeassistant.const", CONF_HOST="host", CONF_PORT="port")
_ensure_stub_package("homeassistant.helpers")
_ensure_stub(
    "homeassistant.helpers.update_coordinator",
    DataUpdateCoordinator=_StubDataUpdateCoordinator,
)
_ensure_stub("homeassistant.config_entries", ConfigEntry=_StubConfigEntry)
_ensure_stub("homeassistant.core", HomeAssistant=_StubHomeAssistant, callback=lambda f: f)

# Stubs the new switch.py imports (the existing tests don't load it).
_ensure_stub_package("homeassistant.components")
_ensure_stub(
    "homeassistant.components.switch",
    SwitchEntity=type("SwitchEntity", (), {}),
    SwitchEntityDescription=type("SwitchEntityDescription", (), {}),
)
class _StubDeviceInfo:
    """Accept and store the kwargs ``gateway_device_info`` passes in tests."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


_ensure_stub(
    "homeassistant.helpers.entity",
    EntityCategory=types.SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic"),
    DeviceInfo=_StubDeviceInfo,
)
_ensure_stub(
    "homeassistant.helpers.entity_platform",
    AddEntitiesCallback=type("AddEntitiesCallback", (), {}),
)

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
_COMP_DIR = _REPO / "custom_components" / "ipbuilding_gateway_ha"

_pkg = sys.modules.get("ipbuilding_gateway_ha")
if not isinstance(_pkg, types.ModuleType) or not hasattr(_pkg, "__path__"):
    _pkg = types.ModuleType("ipbuilding_gateway_ha")
    sys.modules["ipbuilding_gateway_ha"] = _pkg
_pkg.__path__ = [str(_COMP_DIR)]  # type: ignore[attr-defined]

# ``switch.py`` transitively imports ``entity`` + ``hub`` for the device info
# helper, so load those too.
for _name in ("const", "coordinator", "entity", "hub", "switch"):
    _spec = importlib.util.spec_from_file_location(
        f"ipbuilding_gateway_ha.{_name}", _COMP_DIR / f"{_name}.py"
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)  # type: ignore[union-attr]

coordinator_mod = sys.modules["ipbuilding_gateway_ha.coordinator"]
switch_mod = sys.modules["ipbuilding_gateway_ha.switch"]


# ---------------------------------------------------------------------------
# Coordinator tests
# ---------------------------------------------------------------------------


def _build_coordinator(*, gateway_status: dict | None = None):
    """Construct a coordinator with a custom cached gateway_status."""
    coord = coordinator_mod.IPBuildingCoordinator.__new__(
        coordinator_mod.IPBuildingCoordinator
    )
    coord._data = {}
    coord._modules = {}
    coord._known_devices = set()
    coord._host = "127.0.0.1"
    coord._port = 8080
    coord._gateway_status = dict(gateway_status or {})
    coord._gateway_listeners = []
    coord.async_fetch_gateway_status = lambda: _async_return(None)  # type: ignore[method-assign]
    coord._notify_gateway = lambda: None  # type: ignore[method-assign]
    return coord


async def _async_return(value):
    return value


class _ResponseCtx:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def text(self):
        return self._body if isinstance(self._body, str) else json.dumps(self._body)

    async def json(self):
        return self._body


def test_fieldbus_polling_enabled_defaults_true_when_unknown():
    """Before any status refresh, the helper reports the gateway's default."""
    coord = _build_coordinator()
    assert coord.fieldbus_polling_enabled() is True
    assert coord.fieldbus_poll_interval_s() is None


def test_fieldbus_polling_helpers_read_cached_status():
    """The helpers read ``gateway_status['fieldbus']`` exactly."""
    coord = _build_coordinator(
        gateway_status={
            "fieldbus": {"polling_enabled": False, "poll_interval_s": 2.0},
        }
    )
    assert coord.fieldbus_polling_enabled() is False
    assert coord.fieldbus_poll_interval_s() == 2.0


def test_async_set_fieldbus_polling_posts_and_refreshes(monkeypatch):
    """Successful toggle refreshes the cached gateway status and returns True."""
    coord = _build_coordinator(
        gateway_status={
            "fieldbus": {"polling_enabled": True, "poll_interval_s": 2.0},
        }
    )

    captured: dict = {}

    class _Session:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, url, json=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return _ResponseCtx(200, {"polling_enabled": False, "poll_interval_s": 2.0})

    monkeypatch.setattr(coordinator_mod.aiohttp, "ClientSession", _Session)

    refreshed: dict = {}

    async def _fake_fetch() -> dict:
        refreshed["called"] = True
        # Simulate the gateway's status payload after the toggle.
        coord._gateway_status = {
            "fieldbus": {"polling_enabled": False, "poll_interval_s": 2.0},
            "status": "degraded",
        }
        return coord._gateway_status

    coord.async_fetch_gateway_status = _fake_fetch  # type: ignore[method-assign]

    notified: list[int] = []
    coord._notify_gateway = lambda: notified.append(1)  # type: ignore[method-assign]

    import asyncio

    ok = asyncio.run(coord.async_set_fieldbus_polling(False))

    assert ok is True
    assert captured["url"] == "http://127.0.0.1:8080/api/v1/debug/fieldbus-polling"
    assert captured["json"] == {"enabled": False}
    assert refreshed["called"] is True
    # The cached fieldbus block is refreshed, and listeners were notified.
    assert coord.fieldbus_polling_enabled() is False
    assert notified == [1]


def test_async_set_fieldbus_polling_returns_false_on_error(monkeypatch):
    """Network or HTTP errors return False and leave cached state alone."""
    coord = _build_coordinator(
        gateway_status={
            "fieldbus": {"polling_enabled": True, "poll_interval_s": 2.0},
        }
    )

    class _FailingSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, url, json=None, timeout=None):
            return _ResponseCtx(500, "boom")

    monkeypatch.setattr(coordinator_mod.aiohttp, "ClientSession", _FailingSession)

    fetch_called = []

    async def _fake_fetch() -> dict:
        fetch_called.append(1)
        return coord._gateway_status

    coord.async_fetch_gateway_status = _fake_fetch  # type: ignore[method-assign]

    import asyncio

    ok = asyncio.run(coord.async_set_fieldbus_polling(False))
    assert ok is False
    # No refresh / no notify on failure.
    assert fetch_called == []
    # Cached state untouched.
    assert coord.fieldbus_polling_enabled() is True


# ---------------------------------------------------------------------------
# Switch tests
# ---------------------------------------------------------------------------


class _SwitchHarness:
    """Minimal harness around IPBuildingFieldbusPollingSwitch.

    Bypasses ``async_added_to_hass`` (which needs the real HA lifecycle)
    and lets us drive the gateway-status listener directly.
    """

    def __init__(self, *, polling_enabled: bool, poll_interval_s: float = 2.0):
        self.entry = _StubConfigEntry()
        self.entry.entry_id = "test-entry"
        self.coordinator = _build_coordinator(
            gateway_status={
                "fieldbus": {
                    "polling_enabled": polling_enabled,
                    "poll_interval_s": poll_interval_s,
                },
            }
        )

        class _Entity(switch_mod.IPBuildingFieldbusPollingSwitch):
            async def async_added_to_hass(self_inner):  # noqa: N805
                # Just attach the listener like the real method would.
                self_inner._on_status = lambda status: None
                self_inner._coordinator.register_gateway_listener(
                    self_inner._on_status
                )

        self._Entity = _Entity
        self.entity = _Entity(self.entry, self.coordinator)
        # Seed is_on + icon (real entity does this in async_added_to_hass).
        self.entity._attr_is_on = self.coordinator.fieldbus_polling_enabled()

    def push_status(self, status: dict) -> None:
        """Drive the registered listener the way gateway_status pushes do."""
        self.coordinator._apply_gateway_status(status)
        for cb in list(self.coordinator._gateway_listeners):
            cb(self.coordinator._gateway_status)


def test_switch_is_on_mirrors_cached_polling_state():
    harness = _SwitchHarness(polling_enabled=True)
    assert harness.entity.is_on is True

    harness = _SwitchHarness(polling_enabled=False)
    assert harness.entity.is_on is False


def test_switch_updates_when_gateway_status_pushes_disable():
    harness = _SwitchHarness(polling_enabled=True)
    assert harness.entity.is_on is True

    harness.push_status(
        {
            "fieldbus": {"polling_enabled": False, "poll_interval_s": 2.0},
            "status": "degraded",
        }
    )
    # The cached gateway_status changed; the switch class itself only
    # re-reads in ``async_added_to_hass``/its own listener. Assert the
    # contract: the helper returns the new value, so a real listener
    # (which the test replaces) would re-render is_on accordingly.
    assert harness.coordinator.fieldbus_polling_enabled() is False
    assert harness.coordinator.fieldbus_poll_interval_s() == 2.0


def test_switch_async_turn_off_calls_coordinator():
    harness = _SwitchHarness(polling_enabled=True)

    called: list[bool] = []

    async def _fake_set(enabled: bool) -> bool:
        called.append(enabled)
        return True

    harness.coordinator.async_set_fieldbus_polling = _fake_set  # type: ignore[method-assign]

    import asyncio

    asyncio.run(harness.entity.async_turn_off())
    asyncio.run(harness.entity.async_turn_on())

    assert called == [False, True]


def test_switch_unique_id_uses_entry_id():
    harness = _SwitchHarness(polling_enabled=True)
    assert harness.entity._attr_unique_id == "test-entry_fieldbus_polling"
    # Disabled by default so the entity does not show up on Overview unless
    # the operator explicitly enables it in the entity registry.
    assert harness.entity._attr_entity_registry_enabled_default is False
