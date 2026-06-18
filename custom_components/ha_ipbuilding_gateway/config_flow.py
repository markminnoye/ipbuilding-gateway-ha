"""Config flow for IPBuilding Gateway HA.

Three discovery paths are supported, modelled after the Music Assistant
pattern:

1. **Supervisor add-on** (``async_step_hassio``) — the add-on posts to
   ``/supervisor/discovery`` and Home Assistant invokes this step with
   the add-on's host and port.
2. **Zeroconf / mDNS** (``async_step_zeroconf``) — the gateway broadcasts
   ``_ipbgw._tcp.local.`` on the LAN. The companion parses
   the TXT record; when the gateway is running as a Supervisor add-on
   (``homeassistant_addon=true``) we abort to avoid duplicate entries.
3. **Manual** (``async_step_user``) — operator enters host and port
   themselves (standalone Docker, remote setup, or a LAN discovery that
   never reached HA's mDNS listener).
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DISCOVERY_SCHEMA_VERSION,
    DOMAIN,
)
from .discovery_parser import (
    GatewayDiscoveryInfo,
    parse_zeroconf_properties as _parse_zeroconf_properties,
)

log = logging.getLogger(__name__)

ADDON_SLUG = "ipbuilding_gateway"

# Voluptuous schema for the manual fallback form.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_API_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_API_PORT): int,
    }
)


async def _validate_gateway(host: str, port: int) -> tuple[bool, str | None, str | None]:
    """Check the gateway is reachable and fetch its ``instance_id``.

    Returns ``(ok, error, instance_id)``. ``instance_id`` is the gateway's
    stable HA-discovery UUID when available, used as ``unique_id`` for
    the manual config flow.
    """
    url = f"http://{host}:{port}/api/v1/status"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return False, "gateway_unreachable", None
                data = await resp.json()
                instance_id = data.get("instance_id") or None
                log.info("Gateway validated: instance_id=%s", instance_id)
                return True, None, instance_id
    except aiohttp.ClientConnectorError:
        return False, "connection_refused", None
    except Exception as exc:
        log.debug("Gateway validation failed: %s", exc)
        return False, "gateway_unreachable", None


class IPBuildingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPBuilding Gateway HA."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: GatewayDiscoveryInfo | None = None

    # ------------------------------------------------------------------
    # User (manual) step
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual host/port entry (fallback / remote)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            valid, error, instance_id = await _validate_gateway(host, port)
            if valid:
                unique_id = instance_id or f"{host}:{port}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=f"IPBuilding Gateway ({host})",
                    data=user_input,
                )
            errors["base"] = error or "gateway_unreachable"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "host": user_input.get(CONF_HOST, "") if user_input else "",
                "port": str(user_input.get(CONF_PORT, DEFAULT_API_PORT))
                if user_input
                else "",
            },
        )

    # ------------------------------------------------------------------
    # Supervisor add-on discovery
    # ------------------------------------------------------------------

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Supervisor add-on discovery.

        The companion's unique_id is the add-on's discovery UUID. The
        entry is created only after the operator explicitly clicks
        *Toevoegen* in the **Discovered** UI.
        """
        if discovery_info.slug != ADDON_SLUG:
            return self.async_abort(reason="not_ipbuilding_gateway_addon")

        host = discovery_info.config.get("host")
        port = discovery_info.config.get("port", DEFAULT_API_PORT)
        if not host:
            return self.async_abort(reason="invalid_discovery_info")

        await self.async_set_unique_id(discovery_info.uuid)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=int(port),
            instance_id=None,
            base_url=None,
            is_addon=True,
            version=None,
            schema_version=0,
        )
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the add-on discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            host = self._discovery_info.host
            port = self._discovery_info.port
            valid, error, _ = await _validate_gateway(host, port)
            if not valid:
                return self.async_abort(reason="cannot_connect")

            return self.async_create_entry(
                title="IPBuilding Gateway (add-on)",
                data={CONF_HOST: host, CONF_PORT: port},
            )

        return self.async_show_form(
            step_id="hassio_confirm",
            description_placeholders={"addon": "IPBuilding Gateway"},
        )

    # ------------------------------------------------------------------
    # Zeroconf discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Zeroconf discovery broadcast from the gateway.

        The TXT record carries the same fields as the HassIO payload so
        the same parsing path works. When the gateway identifies itself
        as a Supervisor add-on, we abort — that case is handled by
        ``async_step_hassio`` and we don't want a duplicate entry.
        """
        log.info(
            "Zeroconf discovery received: type=%s name=%s srv_host=%s srv_port=%s properties=%s",
            discovery_info.type,
            discovery_info.name,
            getattr(discovery_info, "host", None),
            getattr(discovery_info, "port", None),
            discovery_info.properties,
        )
        try:
            parsed = _parse_zeroconf_properties(
                discovery_info.properties,
                host=discovery_info.host,
                port=discovery_info.port,
            )
        except (KeyError, ValueError) as exc:
            log.warning(
                "Invalid zeroconf payload (%s): %s",
                exc, discovery_info.properties,
            )
            return self.async_abort(reason="invalid_discovery_info")

        log.info(
            "Parsed zeroconf: host=%s port=%d is_addon=%s schema=%d",
            parsed.host, parsed.port, parsed.is_addon, parsed.schema_version,
        )

        # Deduplicate: when the gateway is running as an HA add-on, the
        # HassIO flow is the authoritative one.
        if (
            parsed.schema_version >= DISCOVERY_SCHEMA_VERSION
            and parsed.is_addon
        ):
            log.debug("Ignoring add-on gateway in zeroconf discovery")
            return self.async_abort(reason="already_discovered_addon")

        host = parsed.host or discovery_info.host
        port = parsed.port or discovery_info.port
        if not host or not port:
            return self.async_abort(reason="invalid_discovery_info")

        # Validate that the gateway actually answers on the advertised address.
        valid, error, _ = await _validate_gateway(host, port)
        if not valid:
            log.info("Discovered gateway %s:%d unreachable: %s", host, port, error)
            return self.async_abort(reason="cannot_connect")

        unique_id = parsed.instance_id or f"{host}:{port}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: host, CONF_PORT: port}
        )

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=port,
            instance_id=parsed.instance_id,
            base_url=parsed.base_url,
            is_addon=parsed.is_addon,
            version=parsed.version,
            schema_version=parsed.schema_version,
        )
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a Zeroconf (standalone) discovery."""
        assert self._discovery_info is not None
        info = self._discovery_info
        url = info.base_url or f"http://{info.host}:{info.port}"

        if user_input is not None:
            return self.async_create_entry(
                title="IPBuilding Gateway",
                data={CONF_HOST: info.host, CONF_PORT: info.port},
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"url": url},
        )
