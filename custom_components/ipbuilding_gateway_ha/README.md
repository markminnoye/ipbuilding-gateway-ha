# IPBuilding Gateway HA — custom component

## Overview

Home Assistant custom component for the open
[IPBuilding Gateway](https://github.com/markminnoye/IPBuilding-Gateway). It
connects to the gateway northbound API (WebSocket `/ws`, REST `/api/v1/` on
port 8080) and exposes field-bus channels as standard HA entities.

Unlike the legacy **HA-IPBuilding** integration (IPBox REST on `:30200`), this
component does not implement IPBox scenes, moods, or button→relay provisioning.
That logic lives in Home Assistant automations and scenes.

## Quality scale

This integration targets the **bronze** tier of the Home Assistant integration
quality scale. It therefore:

- Configures entirely through the UI (config flow) with connection validation
- Sets a stable `unique_id` (gateway `instance_id` or `host:port`) and aborts
  duplicate entries
- Uses a `DataUpdateCoordinator` subclass (`IPBuildingCoordinator`) for
  WebSocket I/O and state caching
- Raises `ConfigEntryNotReady` on connectivity failures so HA retries with
  back-off
- Registers a three-tier device tree (gateway hub → module → channel) in the
  device registry
- Provides `strings.json` plus `translations/nl.json` (English is the default
  in `strings.json`)
- Has a unit-test suite under `tests/`

## Supported platforms

| Platform | Entity types | Source |
|----------|--------------|--------|
| `light` | Relay on/off, dimmer brightness | Gateway `state_changed` + commands |
| `switch` | Relay/dimmer with semantic switch types | Same |
| `button` | `EventEntity` (IP1100PoE press), `ButtonEntity` (discovery sweep) | WS `button_pressed` / REST discover |
| `sensor` | Per-channel `current_watt`, gateway `gateway_status` | WS snapshot + `gateway_status` |

Module types on the field bus: **IP0200PoE** (relay), **IP0300PoE** (dimmer),
**IP1100PoE** (input / buttons).

## Discovery

| Path | Handler | When |
|------|---------|------|
| Supervisor | `async_step_hassio` | Add-on posts to `/supervisor/discovery` |
| Zeroconf | `async_step_zeroconf` | Standalone gateway broadcasts `_ipbgw._tcp.local.` |
| Manual | `async_step_user` | Host + port fallback |

Zeroconf uses SRV host/port from `ZeroconfServiceInfo`; TXT carries metadata
(`instance_id`, `homeassistant_addon`, schema version). Add-on gateways set
`homeassistant_addon=true` so the zeroconf path aborts when Supervisor discovery
already applies.

## Northbound API (gateway)

The companion depends on these gateway surfaces (documented in the gateway repo
under `docs/api/`):

| Endpoint / message | Purpose |
|--------------------|---------|
| `GET /api/v1/status` | Health, version, uptime, issues (config-flow validation, status sensor) |
| `GET /api/v1/devices` | Channel snapshot |
| `GET /api/v1/modules` | Module list for device registry |
| `POST /api/v1/discover` | Forced field-bus sweep (discover button) |
| WebSocket `/ws` | `snapshot`, `state_changed`, `button_pressed`, `gateway_status` |
| WebSocket `command` | `ON` / `OFF` / `DIM` to channels |

Legacy IPBox REST (`:30200`) is optional on the gateway and is **not** used by
this integration.

## Entity behaviour

### Device tree

1. **IPBuilding Gateway** — hub device (`sw_version` from `/api/v1/status`)
2. **Module** — Relay / Dimmer / Input (from `/api/v1/modules`)
3. **Channel** — light, switch, sensor, or button entity (`via_device` → module)

### Inactive channels

Channels with `active: false` in gateway `devices.json` are registered with
`entity_registry_enabled_default=False` and
`entity_registry_visible_default=False`. Runtime flips to inactive disable
entities instead of deleting registry entries.

### Areas

The gateway `room` field on a channel is forwarded as `suggested_area`; after
setup, `_suggest_channel_areas` links to an existing HA area with the same name
without overwriting manual assignments.

### Dimmers

Light/switch entities send **`DIM`** commands (not relay-style `ON`/`OFF`) for
`device_type == "dimmer"`. Brightness follows the service call, last known
level, or 100%.

### Button events (v0.4.0+)

Physical buttons use `EventEntity` with
`event_types: ["press", "long_press", "release"]` and `device_class:
EventDeviceClass.BUTTON`. Three bus events are fired with the same
`{"hardware_id": "<id>", "action": "<press|long_press|release>"}` payload:

| Bus event | Trigger |
|-----------|---------|
| `ipbuilding_gateway_ha.button_pressed` | Short press |
| `ipbuilding_gateway_ha.button_long_pressed` | Held past the per-button threshold (default 1.5s, seeded from `getButtons.func2.holdSeconds`) |
| `ipbuilding_gateway_ha.button_released` | Let go — always fires, even on short presses |

The companion also exposes three device triggers in the automation
editor UI: **Button pressed**, **Long pressed**, **Released**.

### Dim-button blueprint

A packaged blueprint `IPBuilding button — toggle + dim during hold` is
shipped with the companion at
`blueprints/automation/ipbuilding_gateway_ha/dim_button.yaml`. It
handles Hue-style continuous dimming during hold with automatic
direction-flip on release and on hitting 1 % / 100 %.

From **Settings → Automations → Blueprints** (or **Create automation → Use
blueprint**) the blueprint appears as `ipbuilding_gateway_ha/dim_button.yaml`
after the integration has loaded once; missing files are copied automatically
from the companion package into your `config/blueprints/automation/` folder.
Pick it, fill in the input fields, and you have a working single-button dimmer.

## Development

Key modules:

| File | Role |
|------|------|
| `coordinator.py` | WebSocket client, snapshot cache, gateway listeners |
| `config_flow.py` | HassIO / zeroconf / manual flows |
| `discovery_parser.py` | Zeroconf TXT + Supervisor payload parsing |
| `hub.py` | Tier-1 gateway `device_info` |
| `entity.py` | Shared device_info, icons, inactive registry defaults |
| `light.py` / `switch.py` / `button.py` / `sensor.py` | Platforms |

Run tests from the repository root:

```bash
pytest tests/
```

For local gateway + HA development, see the gateway repository `local/README.md`.

## Related projects

- [IPBuilding Gateway](https://github.com/markminnoye/IPBuilding-Gateway) — add-on / standalone hub
- [HA-IPBuilding](https://github.com/markminnoye/HA-IPBuilding) — legacy IPBox REST integration (reference only)
