"""Unit tests for the companion's discovery payload parser.

Pure-Python tests that do not require a real Home Assistant install.
The flow handlers themselves (which depend on HA's ``ConfigFlow``) are
validated manually on a real HA OS install.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Minimal ``homeassistant.const`` stub so the companion's ``const`` module
# can be imported without a real HA install.
# ---------------------------------------------------------------------------
if "homeassistant" not in sys.modules:
    sys.modules["homeassistant"] = types.ModuleType("homeassistant")
    const_mod = types.ModuleType("homeassistant.const")
    const_mod.CONF_HOST = "host"
    const_mod.CONF_PORT = "port"
    sys.modules["homeassistant.const"] = const_mod


# Load the companion's discovery parser (which depends only on ``const``).
_REPO = Path(__file__).resolve().parents[1]
_COMP_DIR = _REPO / "custom_components" / "ha_ipbuilding_gateway"

# Build a synthetic package so ``from .const import`` inside
# discovery_parser resolves correctly.
fake_pkg_name = "ha_ipbuilding_gateway"
fake_pkg = types.ModuleType(fake_pkg_name)
fake_pkg.__path__ = [str(_COMP_DIR)]
sys.modules[fake_pkg_name] = fake_pkg

import importlib.util

for name in ("const", "discovery_parser"):
    spec = importlib.util.spec_from_file_location(
        f"{fake_pkg_name}.{name}", _COMP_DIR / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

discovery_parser = sys.modules[f"{fake_pkg_name}.discovery_parser"]
const_mod = sys.modules[f"{fake_pkg_name}.const"]

DISCOVERY_PROP_ADDON = const_mod.DISCOVERY_PROP_ADDON
DISCOVERY_PROP_BASE_URL = const_mod.DISCOVERY_PROP_BASE_URL
DISCOVERY_PROP_INSTANCE_ID = const_mod.DISCOVERY_PROP_INSTANCE_ID
DISCOVERY_PROP_SCHEMA_VERSION = const_mod.DISCOVERY_PROP_SCHEMA_VERSION
DISCOVERY_PROP_VERSION = const_mod.DISCOVERY_PROP_VERSION
DISCOVERY_SCHEMA_VERSION = const_mod.DISCOVERY_SCHEMA_VERSION


def _full_properties(
    *,
    host: str = "192.168.1.10",
    port: str = "8080",
    instance_id: str = "abc123",
    base_url: str = "http://192.168.1.10:8080",
    is_addon: bool = False,
    version: str = "0.1.4",
    schema_version: int = DISCOVERY_SCHEMA_VERSION,
) -> dict[str, str]:
    return {
        "host": host,
        "port": port,
        DISCOVERY_PROP_INSTANCE_ID: instance_id,
        DISCOVERY_PROP_BASE_URL: base_url,
        DISCOVERY_PROP_ADDON: "true" if is_addon else "false",
        DISCOVERY_PROP_VERSION: version,
        DISCOVERY_PROP_SCHEMA_VERSION: str(schema_version),
    }


class TestParseZeroconfProperties:
    def test_happy_path(self) -> None:
        # Real-world shape: HA passes the SRV-level host/port separately
        # from the TXT properties, and the TXT only carries the IPBuilding
        # gateway's own metadata (instance_id, base_url, addon flag, …).
        info = discovery_parser.parse_zeroconf_properties(
            _full_properties(is_addon=False),
            host="192.168.1.10",
            port=8080,
        )
        assert isinstance(info, discovery_parser.GatewayDiscoveryInfo)
        assert info.host == "192.168.1.10"
        assert info.port == 8080
        assert info.instance_id == "abc123"
        assert info.base_url == "http://192.168.1.10:8080"
        assert info.is_addon is False
        assert info.version == "0.1.4"
        assert info.schema_version == DISCOVERY_SCHEMA_VERSION

    def test_addon_true(self) -> None:
        info = discovery_parser.parse_zeroconf_properties(
            _full_properties(is_addon=True),
            host="10.0.0.5",
            port=9090,
        )
        assert info.is_addon is True
        assert info.host == "10.0.0.5"
        assert info.port == 9090

    def test_addon_default_false_when_missing(self) -> None:
        props = _full_properties()
        props.pop(DISCOVERY_PROP_ADDON)
        info = discovery_parser.parse_zeroconf_properties(
            props, host="192.168.1.10", port=8080,
        )
        assert info.is_addon is False

    def test_srv_host_port_takes_precedence_over_txt(self) -> None:
        # The gateway may include a host/port key in its TXT record for
        # older clients; HA's SRV-level values are the canonical source
        # and must win.
        props = _full_properties()
        props["host"] = "10.10.10.10"  # would-be legacy/wrong value
        props["port"] = "9999"
        info = discovery_parser.parse_zeroconf_properties(
            props, host="192.168.1.10", port=8080,
        )
        assert info.host == "192.168.1.10"
        assert info.port == 8080

    def test_falls_back_to_txt_when_srv_missing(self) -> None:
        # Older gateway versions (or alternative clients) may put host/port
        # in the TXT record. Accept that as a fallback.
        props = _full_properties()
        info = discovery_parser.parse_zeroconf_properties(props)
        assert info.host == "192.168.1.10"
        assert info.port == 8080

    def test_missing_host_and_port_raises(self) -> None:
        props = _full_properties()
        props.pop("host")
        props.pop("port")
        with pytest.raises(KeyError):
            discovery_parser.parse_zeroconf_properties(props)

    def test_non_integer_port_raises(self) -> None:
        props = _full_properties(port="not-a-number")
        with pytest.raises(ValueError):
            discovery_parser.parse_zeroconf_properties(
                props, host="192.168.1.10",
            )

    def test_missing_schema_version_defaults_to_zero(self) -> None:
        props = _full_properties()
        props.pop(DISCOVERY_PROP_SCHEMA_VERSION)
        info = discovery_parser.parse_zeroconf_properties(props)
        assert info.schema_version == 0

    def test_malformed_schema_version_defaults_to_zero(self) -> None:
        props = _full_properties(schema_version="bogus")  # type: ignore[arg-type]
        info = discovery_parser.parse_zeroconf_properties(props)
        assert info.schema_version == 0


# ---------------------------------------------------------------------------
# RFC 6763 §7.2 — service type label must be ≤ 15 bytes (after the
# leading underscore), or zeroconf's strict validator rejects the
# broadcast and the gateway goes silent on the LAN.
# ---------------------------------------------------------------------------


def test_zeroconf_service_type_label_within_rfc_limit() -> None:
    # Service type from the companion's const module.
    import json
    import os
    service_type = const_mod.ZEROCONF_SERVICE_TYPE
    label = service_type[1:].split(".")[0]
    assert len(label.encode("utf-8")) <= 15, (
        f"companion service type label {label!r} is {len(label)} bytes; "
        "RFC 6763 §7.2 limits it to 15"
    )
    # And the companion's manifest.json value must match the const value,
    # so HA's mDNS listener and the gateway's broadcast line up.
    manifest_path = os.path.join(os.path.dirname(const_mod.__file__), "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    assert service_type in manifest["zeroconf"], (
        f"manifest.json zeroconf={manifest['zeroconf']!r} does not include "
        f"const.ZEROCONF_SERVICE_TYPE={service_type!r}"
    )
