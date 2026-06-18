"""Constants for ha_ipbuilding_gateway."""

from homeassistant.const import CONF_HOST, CONF_PORT

DOMAIN = "ha_ipbuilding_gateway"

CONF_API_HOST = CONF_HOST
CONF_API_PORT = CONF_PORT

DEFAULT_API_PORT = 8080
#: Default host for the manual config flow. ``127.0.0.1`` is the
#: Supervisor add-on contract (the companion runs in HA Core, the
#: gateway in the same host network namespace on port 8080). Operators
#: running the gateway standalone (Docker / Pi / remote) override this
#: in the form. HassIO and Zeroconf discovery flows still take
#: precedence — they fill ``CONF_HOST`` automatically from the add-on's
#: Supervisor token or the gateway's mDNS TXT record, so this default
#: only matters for the manual fallback ``async_step_user``.
DEFAULT_API_HOST = "127.0.0.1"

# Entity device types
DEVICE_TYPE_RELAY = "relay"
DEVICE_TYPE_DIMMER = "dimmer"
DEVICE_TYPE_INPUT = "input"

# Semantic types
SEMANTIC_TYPE_LIGHT = "light"
SEMANTIC_TYPE_SWITCH = "switch"
SEMANTIC_TYPE_FAN = "fan"
SEMANTIC_TYPE_PLUG = "plug"
SEMANTIC_TYPE_COVER = "cover"
SEMANTIC_TYPE_SENSOR = "sensor"
SEMANTIC_TYPE_BUTTON = "button"

# WS reconnect delays (seconds)
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 5.0
RECONNECT_BACKOFF_MULT = 2.0
# Jitter (±) applied to each reconnect sleep to avoid thundering-herd
# reconnects when the gateway restarts and several clients are waiting.
RECONNECT_JITTER = 0.2

# Polling interval for REST fallback (if WS unavailable)
REST_POLL_INTERVAL = 20.0  # seconds

# ---------------------------------------------------------------------------
# HA discovery
# ---------------------------------------------------------------------------

#: Zeroconf service type. Must match ``SERVICE_TYPE`` in the gateway.
#: Per RFC 6763 §7.2 the leading label (after the underscore) must be
#: ≤ 15 bytes; ``ipbuilding-gateway`` is 18 bytes and is rejected by
#: zeroconf's strict validator.
ZEROCONF_SERVICE_TYPE = "_ipbgw._tcp.local."

#: Discovery TXT schema version. Bump when the gateway changes the wire
#: format in a way the companion needs to react to.
DISCOVERY_SCHEMA_VERSION = 1

#: TXT property names.
DISCOVERY_PROP_INSTANCE_ID = "instance_id"
DISCOVERY_PROP_BASE_URL = "base_url"
DISCOVERY_PROP_ADDON = "homeassistant_addon"
DISCOVERY_PROP_SCHEMA_VERSION = "schema_version"
DISCOVERY_PROP_VERSION = "version"

# ---------------------------------------------------------------------------
# Onboarding wizard
# ---------------------------------------------------------------------------

CONF_ONBOARDING_COMPLETED = "onboarding_completed"
CONF_ONBOARDING_SKIPPED = "onboarding_skipped"
CONF_ROOM_MAPPINGS = "room_mappings"
CONF_BUTTON_AUTOMATIONS = "button_automations"