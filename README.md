# Home Assistant integration for IPBuilding Gateway

[![Version](https://img.shields.io/github/v/release/markminnoye/ipbuilding-gateway-ha)](https://github.com/markminnoye/ipbuilding-gateway-ha/releases/latest)
[![License](https://img.shields.io/github/license/markminnoye/ipbuilding-gateway-ha)](LICENSE)
[![Quality Scale](https://img.shields.io/badge/quality%20scale-bronze-brightgreen)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)

Control your **IPBuilding** field bus from Home Assistant through the open
**IPBuilding Gateway** — relays, dimmers, and physical buttons on the
UDP/1001 bus, without the proprietary IPBox REST API or cloud services.

Scenes, automations, and button-to-action logic belong in **Home Assistant**,
not in the gateway. The gateway is a thin field-bus hub; this companion turns
its northbound WebSocket API into standard HA entities.

## How it works

This integration talks to the [**IPBuilding Gateway**](https://github.com/markminnoye/IPBuilding-Gateway)
add-on (or a standalone gateway) on port **8080** via WebSocket and REST.
The gateway replaces the IPBox as the **hub on the field bus** (UDP/1001 to
IP0200PoE relays, IP0300PoE dimmers, and IP1100PoE inputs). IPBuilding
modules are not contacted directly from Home Assistant.

> **Requirement:** A running IPBuilding Gateway reachable from Home Assistant
> (typically the HA add-on on the same host, or a gateway on your IPBuilding
> VLAN). Install **add-on and companion at the same version** (currently
> **v0.3.0**).

## Features

- **Auto-discovery** in **Settings → Devices & Services → Discovered**
  (Supervisor discovery when the add-on runs on HA OS; mDNS `_ipbgw._tcp.local.`
  for standalone gateways)
- **Lights** — relays (on/off) and dimmers (brightness)
- **Switches** — relays/dimmers with semantic types (plug, fan, …)
- **Sensors** — per-channel power (`current_watt`) and gateway health status
- **Buttons** — physical IP1100PoE presses as HA events; gateway discovery
  sweep as a config button on the hub device
- **Three-tier device tree** — Gateway → module (Relay / Dimmer / Input) →
  channel entity, with optional room → HA area mapping from `devices.json`
- English and Dutch UI translations

Platforms created by this integration: `light`, `switch`, `button`, `sensor`.

## Requirements {#prerequisites}

- Home Assistant **2023.8** or newer (tested with **2026.3** for dimmer
  `color_modes`)
- [**IPBuilding Gateway**](https://github.com/markminnoye/IPBuilding-Gateway)
  **v0.3.0** (add-on or standalone) with WebSocket `/ws` and REST `/api/v1/`
  on port **8080**
- Network path from Home Assistant to the gateway API (host networking /
  VLAN routing as required by your install)
- A populated `devices.json` on the gateway (from discovery or migration)

## Installation

Install the **gateway** and **companion** together. Version numbers are not
kept in lockstep — the two repos follow independent semver. A release of
one does not require a release of the other. Breaking changes (if any)
are called out in each `CHANGELOG.md` under a `### Breaking:` section.

### 1. Gateway add-on (HA OS / Supervised)

[![Add add-on repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway)

See the [add-on documentation](https://github.com/markminnoye/IPBuilding-Gateway/blob/main/ipbuilding_gateway/DOCS.md)
for `devices.json`, options, and field-bus networking.

### 2. Companion integration (HACS, recommended)

Make sure the [prerequisites](#prerequisites) are met before installing.

This integration is a **HACS custom repository** (not in the default store). Use
the link below to add it in HACS, then download **IPBuilding Gateway HA** and
restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ipbuilding-gateway-ha&category=integration)

Direct link (same target):

```text
https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ipbuilding-gateway-ha&category=integration
```

If HACS shows *Repository … not found* or a broken confirmation dialog, add the
repo manually: **HACS → Integrations → ⋮ → Custom repositories** →
`https://github.com/markminnoye/ipbuilding-gateway-ha` (type **Integration**),
then search and download **IPBuilding Gateway HA**.

### Manual installation

1. Copy the `custom_components/ipbuilding_gateway_ha` directory from this
   repository into your Home Assistant `config/custom_components` folder.

   Final path: `config/custom_components/ipbuilding_gateway_ha`

2. Restart Home Assistant.

## Configuration

The integration is configured entirely through the Home Assistant UI — no YAML
is required for setup.

### Discovered (recommended)

1. Start the **IPBuilding Gateway** add-on (or standalone gateway).
2. Go to **Settings → Devices & Services → Discovered**.
3. Select **IPBuilding Gateway HA** and confirm.

On HA OS the add-on registers via **Supervisor discovery**. On a standalone
gateway the companion listens for **mDNS** (`_ipbgw._tcp.local.`). When both
apply, duplicate entries are suppressed automatically.

### Manual fallback

Use **Settings → Devices & Services → Add integration → IPBuilding Gateway HA**
when discovery is blocked (VLAN without mDNS reflector, remote host, etc.):

- **Host** — IP address or hostname of the gateway
- **Port** — API port (default **8080**)

The config flow validates `GET /api/v1/status` before saving. Only one config
entry per gateway instance is allowed.

## Dashboard

A ready-to-paste Lovelace snippet for gateway status and the discovery-sweep
button is in
[`custom_components/ipbuilding_gateway_ha/dashboard.md`](custom_components/ipbuilding_gateway_ha/dashboard.md)
(includes optional HACS **button-card** notes).

## Actions

The integration does not register custom services for device control. Use
standard Home Assistant services on the created entities:

- `light.turn_on` / `light.turn_off` — relays and dimmers (dimmers use `DIM`
  on the field bus)
- `switch.turn_on` / `switch.turn_off` — switch-class channels
- `button.press` — gateway discovery sweep (hub device)

Physical IP1100PoE buttons are exposed as `event.<naam>` entities under the
IP1100PoE device. Use a **state trigger** on the entity (preferred — shows up
in the UI trace):

```yaml
triggers:
  - trigger: state
    entity_id: event.badkamer_knop
    to: "press"
actions:
  - action: light.turn_on
    target:
      entity_id: light.badkamer
```

For backward compatibility, the integration also fires the bus event
`ipbuilding_gateway_ha.button_pressed` with `{"hardware_id": "...", "action": "press"}`:

```yaml
trigger:
  - platform: event
    event_type: ipbuilding_gateway_ha.button_pressed
    event_data:
      hardware_id: "2f8185190000df"
```

Build scenes and automations in Home Assistant — the gateway does not store
IPBox-style moods or button→relay mappings.

## Inactive channels

Channels marked `active: false` in the gateway `devices.json` appear as
**disabled, hidden** entities. Enable them under
**Settings → Devices & Services → Entities** when wiring is complete.

## Security notes

- The gateway API has **no authentication** — anyone on the LAN who can reach
  port 8080 can control the field bus. **Do not expose the gateway outside your
  LAN.**
- Traffic is **unencrypted HTTP/WebSocket**. Use only on a trusted network
  segment (e.g. your IPBuilding VLAN).
- Replacing the IPBox hub on UDP/1001 requires correct L2/L3 placement; see
  gateway docs before cutting over production wiring.

## Removing the integration

Go to **Settings → Devices & Services → IPBuilding Gateway HA**, select your
entry, and click **Delete**. This removes Home Assistant entities and the
config entry only — the gateway add-on and `devices.json` are unchanged.

## Migrating from HA-IPBuilding (IPBox REST)

The legacy [**HA-IPBuilding**](https://github.com/markminnoye/HA-IPBuilding)
integration talks to the IPBox REST API on port **30200**. This companion uses
the open gateway on **8080** instead. See the
[gateway architecture / migration notes](https://github.com/markminnoye/IPBuilding-Gateway/blob/main/ARCHITECTURE.md)
for a cutover path (import devices → run gateway → install companion → move
automations to HA → retire IPBox on the field bus).

## Issues and feature requests

Use the [issue tracker](https://github.com/markminnoye/ipbuilding-gateway-ha/issues).
When reporting a bug, include:

- Home Assistant version
- Integration version (**Settings → Devices & Services → IPBuilding Gateway HA**)
- Gateway add-on / standalone version (`GET /api/v1/status` → `version`)
- Relevant logs (**Settings → System → Logs**, filter `ipbuilding_gateway_ha`)

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.
