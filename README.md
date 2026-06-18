# Home Assistant Compannion App for IPBuilding Gateway

[![Version](https://img.shields.io/github/v/release/markminnoye/ha-ipbuilding-gateway)](https://github.com/markminnoye/ha-ipbuilding-gateway/releases/latest)
[![License](https://img.shields.io/github/license/markminnoye/ha-ipbuilding-gateway)](LICENSE)
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
> VLAN). Add-on and companion follow independent semver; use the
> [latest gateway release](https://github.com/markminnoye/IPBuilding-Gateway/releases)
> and the [latest companion release](https://github.com/markminnoye/ha-ipbuilding-gateway/releases).

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
- [**IPBuilding Gateway**](https://github.com/markminnoye/IPBuilding-Gateway) —
  any recent release (add-on or standalone) with WebSocket `/ws` and
  REST `/api/v1/` on port **8080**
- Network path from Home Assistant to the gateway API (host networking /
  VLAN routing as required by your install)
- A populated `devices.json` on the gateway (from discovery or migration)

## Installation

Install the **gateway** and **companion** together. Version numbers are not
kept in lockstep — the two repos follow independent semver. A release of
one does not require a release of the other. Breaking changes (if any)
are called out in each `CHANGELOG.md` under a `### Breaking:` section.

### Upgrading from a pre-1.0 install?

This is a breaking release. The integration's Home Assistant domain changed from `ipbuilding_gateway_ha` to `ha_ipbuilding_gateway`, and bus event-types changed accordingly.

Before updating:

1. **Settings → Devices & Services → Integrations → IPBuilding Gateway HA** → ⋯ → Delete. Confirm when prompted.
2. Update the integration in HACS (the repository is now `markminnoye/ha-ipbuilding-gateway`).
3. Restart Home Assistant.
4. Re-add the integration from the **Discovered** list (or manually). All entities re-appear with new IDs (`light.ha_ipbuilding_gateway_*`, `switch.ha_ipbuilding_gateway_*`, `event.ha_ipbuilding_gateway_*`, `sensor.ha_ipbuilding_gateway_*`).
5. Move any custom blueprints from `config/blueprints/automation/ipbuilding_gateway_ha/` to `config/blueprints/automation/ha_ipbuilding_gateway/` (or recreate them in the UI).
6. Update Lovelace cards, scripts, and automations that reference the old entity IDs or the old bus event-types (`ipbuilding_gateway_ha.button_*` → `ha_ipbuilding_gateway.button_*`).
7. If you imported button mappings via `scripts/import_ipbox_to_ha.py` in the gateway repo, re-run it: the gateway script now writes the new event-types automatically.

No data is lost in the gateway itself (`devices.json` is on the gateway filesystem, not in HA), and the gateway add-on's `discovery:` key is updated to match the new domain.

### 1. Gateway add-on (HA OS / Supervised)

[![Add add-on repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmarkminnoye%2FIPBuilding-Gateway)

See the [add-on documentation](https://github.com/markminnoye/IPBuilding-Gateway/blob/main/ipbuilding_gateway/DOCS.md)
for `devices.json`, options, and field-bus networking.

### 2. Companion integration (HACS, recommended)

Make sure the [prerequisites](#prerequisites) are met before installing.

This integration is a **HACS custom repository** (not in the default store). Use
the link below to add it in HACS, then download **IPBuilding Gateway HA** and
restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ha-ipbuilding-gateway&category=integration)

Direct link (same target):

```text
https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ha-ipbuilding-gateway&category=integration
```

If HACS shows *Repository … not found* or a broken confirmation dialog, add the
repo manually: **HACS → Integrations → ⋮ → Custom repositories** →
`https://github.com/markminnoye/ha-ipbuilding-gateway` (type **Integration**),
then search and download **IPBuilding Gateway HA**.

### Manual installation

1. Copy the `custom_components/ha_ipbuilding_gateway` directory from this
   repository into your Home Assistant `config/custom_components` folder.

   Final path: `config/custom_components/ha_ipbuilding_gateway`

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
[`custom_components/ha_ipbuilding_gateway/dashboard.md`](custom_components/ha_ipbuilding_gateway/dashboard.md)
(includes optional HACS **button-card** notes).

## Button automations

The companion does **not** ship automation blueprints to the operator's
HA Blueprint picker as of `v0.4.0-rc.11`. The packaged blueprint files
remain in this repository for reference and for the source-only tests:
[`blueprints/automation/ha_ipbuilding_gateway/`](custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/).

To wire an IP1100PoE physical button to a lamp, dimmer, cover, or
scene, use one of the following paths.

### 1. Community blueprint (recommended for most users)

The HA community maintains a number of blueprints that work with the
event entities this companion creates (`event.<hardware_id>` with
`press`, `long_press`, and `release` event types):

- **[Philips Hue Dimmer Switch (Z2M) — Ultimate Controller](https://community.home-assistant.io/t/z2m-philips-hue-dimmer-switch-ultimate-controller-device-triggers-double-clicks/977875)**
  matches our `press` / `long_press` / `release` semantics and supports
  on/off buttons, dim-up, dim-down, and double-click.
- **[IKEA STYRBAR 4-Button Remote (ZHA / MQTT)](https://gist.github.com/ivvil/08c95674732b51bc4ccf79938471cdc9)**
  is configurable per button with press and press-and-hold actions.

Install via HACS → Frontend → "Add repository" → import by URL, or via
`ha_import_blueprint`. Then pick the event entity of your physical
button as the trigger.

### 2. Standard HA UI flow

From the device page (`Instellingen → Apparaten & entiteiten →
<jouw knop> → ... → '+ Toevoegen aan' → Maak automatisering`), or
from `Instellingen → Automatiseringen & scènes → + Maak automatisering
→ Maak nieuwe automatisering`, build the automation manually:

- **Trigger**: state trigger on the event entity, `to: "press"`
  (and optionally `to: "long_press"`, `to: "release"`).
- **Action**: `light.toggle` (short press), or for smooth dim
  during hold:
  ```yaml
  - repeat:
      while:
        - condition: trigger
          id: hold
      sequence:
        - action: light.turn_on
          target:
            entity_id: !input target_light
          data:
            brightness_step_pct: -10
            transition: 0.2
        - delay:
            milliseconds: 200
  ```
- **Save**: the popup asks for a name. Use the friendly button name
  (e.g. "Keuken wandknop → Keuken LED") instead of the `event.<id>`.

### 3. YAML reference (advanced)

The packaged blueprints in this repo (`button_toggle`,
`button_standard`, `button_dim`, `button_cover`) demonstrate the
patterns. Copy the `trigger` and `action` blocks into your own
`automations.yaml` and adapt the entity IDs and selectors.

## Actions

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
`ha_ipbuilding_gateway.button_pressed` with `{"hardware_id": "...", "action": "press"}`:

```yaml
trigger:
  - platform: event
    event_type: ha_ipbuilding_gateway.button_pressed
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

Use the [issue tracker](https://github.com/markminnoye/ha-ipbuilding-gateway/issues).
When reporting a bug, include:

- Home Assistant version
- Integration version (**Settings → Devices & Services → IPBuilding Gateway HA**)
- Gateway add-on / standalone version (`GET /api/v1/status` → `version`)
- Relevant logs (**Settings → System → Logs**, filter `ha_ipbuilding_gateway`)

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file.
