"""Pure helpers for parsing gateway discovery payloads.

Lives in its own module (no Home Assistant imports) so it can be
unit-tested without spinning up a full HA harness. The HA config flow
imports these helpers and adds the HA-specific plumbing (ConfigFlow,
abort reasons, …) on top.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DISCOVERY_PROP_ADDON,
    DISCOVERY_PROP_BASE_URL,
    DISCOVERY_PROP_INSTANCE_ID,
    DISCOVERY_PROP_SCHEMA_VERSION,
    DISCOVERY_PROP_VERSION,
)


@dataclass(frozen=True)
class GatewayDiscoveryInfo:
    """Parsed view of a gateway's discovery payload (HassIO or Zeroconf)."""

    host: str
    port: int
    instance_id: str | None
    base_url: str | None
    is_addon: bool
    version: str | None
    schema_version: int


def parse_zeroconf_properties(
    properties: dict[str, str],
    *,
    host: str | None = None,
    port: int | None = None,
) -> GatewayDiscoveryInfo:
    """Build a :class:`GatewayDiscoveryInfo` from a Zeroconf TXT record.

    ``host`` and ``port`` are the canonical SRV/A-record values that HA
    exposes as ``ZeroconfServiceInfo.host`` and ``.port``. They take
    precedence over any ``host``/``port`` keys that happen to live in
    the TXT properties (some gateways include them there for older
    clients; we accept either, but the object-level values win).

    Raises:
        KeyError: when neither the object-level host/port nor the
            TXT ``host``/``port`` properties can supply a value.
        ValueError: when a property is malformed.
    """
    # Prefer the SRV-level values (always present on HA's
    # ZeroconfServiceInfo) and only fall back to TXT for back-compat.
    resolved_host = host if host else properties.get("host")
    resolved_port = port if port is not None else properties.get("port")
    if resolved_port is not None and not isinstance(resolved_port, int):
        try:
            resolved_port = int(resolved_port)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"port {resolved_port!r} is not an integer") from exc
    if not resolved_host or resolved_port is None:
        raise KeyError(
            "host or port missing from zeroconf discovery "
            "(neither object-level nor TXT)"
        )

    schema_raw = properties.get(DISCOVERY_PROP_SCHEMA_VERSION, "0")
    try:
        schema_version = int(schema_raw)
    except ValueError:
        schema_version = 0

    return GatewayDiscoveryInfo(
        host=resolved_host,
        port=resolved_port,
        instance_id=properties.get(DISCOVERY_PROP_INSTANCE_ID),
        base_url=properties.get(DISCOVERY_PROP_BASE_URL),
        is_addon=properties.get(DISCOVERY_PROP_ADDON, "false").lower() == "true",
        version=properties.get(DISCOVERY_PROP_VERSION),
        schema_version=schema_version,
    )
