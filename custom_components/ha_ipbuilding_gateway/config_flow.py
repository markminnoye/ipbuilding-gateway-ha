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
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
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


def _is_ipbuilding_gateway_addon(slug: str) -> bool:
    """Return True for an IPBuilding Gateway add-on slug, including custom-repo slugs.

    Custom add-on repositories prefix the slug with a short hash (e.g.
    ``3059e002_ipbuilding_gateway``); we accept any slug that ends with
    ``ADDON_SLUG`` so Supervisor discovery works whether the add-on is
    installed from the official store or from a custom repository.
    """
    return slug.endswith(ADDON_SLUG)

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
                self._abort_if_unique_id_configured(
                    updates=user_input, reload_on_update=False
                )
                return self.async_create_entry(
                    title=f"IPBuilding Gateway ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: int(port),
                    },
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
        if not _is_ipbuilding_gateway_addon(discovery_info.slug):
            return self.async_abort(reason="not_ipbuilding_gateway_addon")

        host = discovery_info.config.get("host")
        port = discovery_info.config.get("port", DEFAULT_API_PORT)
        if not host:
            return self.async_abort(reason="invalid_discovery_info")

        instance_id = discovery_info.config.get("instance_id") or discovery_info.uuid
        await self.async_set_unique_id(instance_id)
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: host, CONF_PORT: port}, reload_on_update=False
        )

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=int(port),
            instance_id=instance_id,
            base_url=f"http://{host}:{port}",
            is_addon=True,
            version=None,
            sw_version=None,
            mac=None,
            schema_version=DISCOVERY_SCHEMA_VERSION,
        )
        return await self.async_step_confirm()

    # ------------------------------------------------------------------
    # Zeroconf discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a Zeroconf discovery broadcast from the gateway.

        mDNS is the primary discovery channel; we no longer abort when the
        gateway identifies itself as a Supervisor add-on (was a duplicate
        guard when the HassIO flow was the only path). Both standalone and
        add-on installs use the same ``async_step_confirm`` form.
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
            "Parsed zeroconf: host=%s port=%d is_addon=%s schema=%d instance_id=%s",
            parsed.host, parsed.port, parsed.is_addon,
            parsed.schema_version, parsed.instance_id,
        )

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
            updates={CONF_HOST: host, CONF_PORT: port}, reload_on_update=False
        )

        self._discovery_info = GatewayDiscoveryInfo(
            host=host,
            port=port,
            instance_id=parsed.instance_id,
            base_url=parsed.base_url,
            is_addon=parsed.is_addon,
            version=parsed.version,
            sw_version=parsed.sw_version,
            mac=parsed.mac,
            schema_version=parsed.schema_version,
        )
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered gateway (Zeroconf or HassIO) and pick a name.

        Used by both discovery paths. The operator can rename the gateway
        or accept the default (``instance_id[:8]``). The chosen name is
        embedded in the config-entry title and the flow header.
        """
        assert self._discovery_info is not None
        info = self._discovery_info
        default_name = (
            (info.instance_id or "")[:8] if info.instance_id else ""
        ) or "gateway"
        url = info.base_url or f"http://{info.host}:{info.port}"
        version_label = info.sw_version or info.version or "onbekend"

        if user_input is not None:
            name = (user_input.get("name") or "").strip() or default_name
            valid, error, _ = await _validate_gateway(info.host, info.port)
            if not valid:
                return self.async_abort(reason="cannot_connect")
            self.context["title_placeholders"] = {"name": name}
            return self.async_create_entry(
                title=f"IPBuilding Gateway ({name})",
                data={
                    CONF_HOST: info.host,
                    CONF_PORT: int(info.port),
                },
            )

        self.context["title_placeholders"] = {"name": default_name}
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {vol.Optional("name", default=default_name): str}
            ),
            description_placeholders={
                "url": url,
                "version": version_label,
                "addon": "IPBuilding Gateway",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler.

        Must be defined on the ``ConfigFlow`` subclass — HA looks up
        options flow via ``handler.async_get_options_flow(entry)`` on
        the class that owns the domain, and falls back to
        ``data_entry_flow.UnknownHandler`` when only a module-level
        function is provided.

        In HA 2026.6+ the flow manager injects the config entry id
        through ``self.handler`` after construction; the handler class
        reads the entry via the read-only ``OptionsFlow.config_entry``
        property. We therefore do not pass ``config_entry`` to the
        handler's constructor.
        """
        from .options_flow import IPBuildingOptionsFlowHandler

        return IPBuildingOptionsFlowHandler()
