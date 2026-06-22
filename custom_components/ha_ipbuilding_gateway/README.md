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

The gateway `room` field on a channel is forwarded as `suggested_area` so
Home Assistant's native device-assignment UI offers the matching HA area
as a preselect option even before any mapping has been saved.

After setup, `_suggest_channel_areas` silently links devices to an
existing HA area with the same name (without overwriting manual
assignments). Operators who want to map every gateway room at once use
the options flow:

**Settings → Devices & services → IPBuilding Gateway → Configure →
Ruimtes koppelen** (`map_rooms` step). The form shows one
`AreaSelector` per unique gateway room; an empty field falls back to an
HA area with the gateway room name (existing or newly created). The
mapping is stored in `entry.options[CONF_ROOM_MAPPINGS]` and
re-applied on every reload by `_apply_stored_room_mappings`, picking up
new devices that did not exist when the mapping was first saved.

> The previous onboarding wizard (config-flow + button import) was
> removed in v1.2.0. The last release with the wizard is tagged
> `v1.1.0-with-onboarding-wizard`.

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
| `ha_ipbuilding_gateway.button_pressed` | Short press |
| `ha_ipbuilding_gateway.button_long_pressed` | Held past the per-button threshold (default 1.5s, seeded from `getButtons.func2.holdSeconds`) |
| `ha_ipbuilding_gateway.button_released` | Let go — always fires, even on short presses |

The companion also exposes three device triggers in the automation
editor UI: **Button pressed**, **Long pressed**, **Released**.

### Button blueprints

Packaged automation blueprints for IP1100PoE wall buttons live at
`blueprints/automation/ha_ipbuilding_gateway/`. On integration setup they
are copied (or upgraded) into your HA config folder
`config/blueprints/automation/ha_ipbuilding_gateway/` so they appear in
**Settings → Automations & scenes → Blueprints**.

| Blueprint | Purpose |
|-----------|---------|
| `button_standard` | Short + long press → full action-editor (scenes, lights, scripts, any service) |
| `button_dim` | Toggle + dim while held — **native ramp**, no helper (gateway sends `dim_start`/`dim_stop`, module ramps + auto-reverses) |
| `button_dim_stepwise` | Alternative: HA-driven stepwise dimming (needs `input_boolean` direction helper) |

> **Belangrijk (2026-06-20):** de state-triggers in alle blueprints
> gebruiken `attribute: event_type`. Event entities slaan de
> press/long_press/release waarde op in het attribuut (niet in de
> state, dat is een timestamp). Een kale `to: "press"` trigger vuurt
> nooit; dat is de oorzaak van "Hal R → bureau toggle werkt niet"
> (zie CHANGELOG v0.x).

#### `button_dim` (native)

- Short press → toggle the light.
- Long press → `dim_start`; the IP0300PoE ramps and auto-reverses direction
  on each successive hold (no helper, no HA-side loop).
- Release → `dim_stop`; the dimmer reports the level reached.

#### `button_dim_stepwise` (alternative)

- Short press → toggle (no direction flip).
- Long press → HA dim loop. First hold on an off lamp turns it on at 1 % and
  continues dimming.
- Release after a long press → flip the dim direction for the next hold.
- Release after a short press → no flip.
- Hitting 1 % / 100 % during a dim → flip the direction automatically.

Add `# user_modified: true` at the top of a blueprint file in your HA
config folder to opt out of automatic upgrades on companion updates.

Event semantics: `press`, `long_press` (after ~1.5 s hold), `release`
(always fires, including after short presses). Blueprints use state
triggers on the `event.<hardware_id>` entity.

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
