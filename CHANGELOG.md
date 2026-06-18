# Changelog

Alle notable wijzigingen aan deze custom component worden hier gedocumenteerd.

Het format is gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/),
en dit project volgt [Semantic Versioning](https://semver.org/lang/nl/).

## Versiebeleid

De `ipbuilding-gateway-ha` companion en de **IPBuilding Gateway** add-on
volgen **onafhankelijk semver**. Een bump in de ene repo betekent
niet automatisch een bump in de andere.

- **Patch (0.3.x)**: cosmetisch, geen impact op de REST/WS wire.
  Werkt met alle gateway-versies die de huidige wire ondersteunen.
- **Minor (0.x.0)**: nieuwe velden of optionele WS-events. De oude
  gateway blijft werken, maar de companion gebruikt de nieuwe
  velden niet tenzij de gateway ze levert.
- **Major (x.0.0)**: breaking change. De CHANGELOG bevat dan een
  `### Breaking:` entry die de incompatibele combinaties opsomt.

Backward compatibiliteit is de norm — een versie van deze companion
blijft werken met de huidige gateway tot een `### Breaking:`-regel
anders meldt.

## [Unreleased]

## [0.4.0-rc.5] - 2026-06-18

### Fixed
- **hassfest:** `automation` en `blueprint` toegevoegd aan `manifest.json` `dependencies` (vereist voor packaged blueprint-installatie).
- **Manual config flow pre-fills the host with `127.0.0.1`** — the Supervisor add-on contract. Operators adding the integration by hand used to see an empty host field; the loopback hint now matches the HassIO discovery flow, so a fresh add-on install confirms out of the box. Standalone installs (Docker, Pi, remote) can still override the value.
- **discovery_completed + bootstrap one-shot** — robuuster afhandelen van discovery-events en eerste REST-bootstrap.

### Removed
- **Debug switch om gateway veld-bus polling te togglen.** De `Fieldbus polling (debug)` entity en de bijbehorende coordinator-helpers zijn verwijderd. De gateway-side `POST /api/v1/debug/fieldbus-polling` endpoint is eveneens verwijderd (zie [`IPBuilding-Gateway` v0.4.3](../../IPBuilding-Gateway/blob/main/ipbuilding_gateway/CHANGELOG.md)).

## [0.4.0] - 2026-06-17

### Added
- **Dim-button blueprint** (`ipbuilding_gateway_ha/dim_button.yaml`): toggle op korte druk, dimmen tijdens hold met automatische direction-flip bij loslaten en op 1 % / 100 %.
- Packaged automation-blueprints worden bij integratie-setup automatisch naar `config/blueprints/automation/` gekopieerd wanneer ze daar nog ontbreken; bestaande bestanden worden niet overschreven.
- IP1100PoE-knoppen: `long_press`- en `release`-eventtypes op de event-entity, plus bus-events `ipbuilding_gateway_ha.button_long_pressed` en `ipbuilding_gateway_ha.button_released` (naast het bestaande `button_pressed`).
- Drie device triggers per knop in de automation-editor: **Button pressed**, **Long pressed**, **Released**.

### Changed
- Fysieke knoppen en de discovery-sweepknop zijn gesplitst over het `event`- en `button`-platform; hardware-knoppen krijgen een stabiele `event.<hardware_id>` entity_id.
- **Vernieuwde iconenset voor de integratie.** Het icoon van de companion (HACS-categorie, Apparaten & diensten) en de merkiconen in `brand/` zijn vervangen door een nieuwe set. De weergave in Instellingen → Apparaten & diensten en de merk-icon-grid gebruiken voortaan het nieuwe ontwerp; gedrag van entiteiten verandert niet.

### Fixed
- Dim-button blueprint: entity selector gebruikt het `filter:`-formaat (HA 2026.3+); `direction_helper`-variabele in de dim-repeat-actie.

## [0.3.8] - 2026-06-16

### Fixed
- **Channel entities (lights, switches, power sensors, IP1100PoE button events) failed to appear on startup**: the REST fallback left `coordinator.data` as a list while the four platforms (and the area-suggestion helper) read it as a dict, so only the three module devices were ever registered. Platforms now go through `IPBuildingCoordinator.devices_snapshot()`, and the REST fetch also populates the internal device cache so `coordinator.data` matches the WebSocket shape.

## [0.3.7] - 2026-06-16

### Changed
- **Apparaatnaam voor de drie field modules toont nu `Relay module`, `Dimmer module`, `Input module`** in plaats van `Relay` / `Dimmer` / `Input`. De suffix maakt expliciet dat de kaart in de onboarding "Naam geven en toewijzen" de fysieke module voorstelt, niet één van de kanalen. De kanaal-apparaten in "Apparaat-info" houden hun korte rol-label (`Relay` / `Dimmer` / `Input`) zodat het overzicht bij 16+ kanalen compact blijft. De SKU-titel (`IP0200PoE` / `IP0300PoE` / `IP1100PoE`) verandert niet.

## [0.3.6] - 2026-06-16

### Fixed
- **IP1100PoE-knoppen verschijnen nu als uitgeschakeld** in plaats van niet beschikbaar. Nieuwe knoppen uit de gateway-snapshot worden standaard verborgen en uitgeschakeld geregistreerd; je schakelt ze zelf in onder Instellingen → Apparaten & entiteiten.

## [0.3.5] - 2026-06-16

### Notes
- **Lockstep bump** met de add-on. Geen code-wijzigingen in de companion. Vereist add-on **v0.3.5** voor automatische Supervisor-updates.

## [0.3.3] - 2026-06-16

### Fixed
- **Button entities failed to load** with `UnboundLocalError: cannot access local variable 'callback'`: the WS listener inside `async_added_to_hass` was named `callback`, which shadowed the imported `@callback` decorator from Home Assistant.
- **Duplicate unique ID errors** for lights, sensors and buttons on startup: the debounced diff triggered by the first WebSocket `snapshot` treated every channel as new because `_known_devices` was still empty after the initial REST/platform setup. The coordinator now seeds known devices once all platforms have finished loading.

### Changed
- **Module names are now consistent across all three field modules.** A new `module_device_model` helper returns the canonical hardware SKU (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) as the `model` field even when the gateway snapshot lacks a factory product label. The Tier-2 module registration and `build_module_hub_device_info` both use it, so onboarding's "Apparaat-info" always shows the SKU as title.
- `module_device_name` now treats the module's IP address and the bare hardware SKU as auto-discovery placeholders. Operators who set a real name in `devices.json` (e.g. `Kelder relais`) are unaffected; auto-discovery and pre-provisioned installs (e.g. legacy `name: "10.10.1.50"`) now show the role label (`Relay` / `Dimmer` / `Input`) instead of an IP.

### Notes
- Vereist add-on **v0.3.3** voor de SKU-backfill; oudere add-ons blijven werken dankzij de defensive fallback in de companion, maar krijgen geen automatische `devices.json`-correctie.

## [0.3.1] — 2026-06-16

### Changed
- Companion version bumped to **0.3.1** to keep lockstep with the gateway add-on. This is a build-only release on the add-on side: the add-on image at tag `v0.3.0` was missing the `zeroconf` package at runtime because the build context picked up a stale copy of `requirements-gateway.txt`. The companion code itself is unchanged from 0.3.0.

## [0.3.0] — 2026-06-16

Bundelrelease: alles sinds **0.1.0** (plus wijzigingen die alleen onder
0.1.1–0.2.2 stonden) zit in deze versie. Tussenliggende tags zijn niet
allemaal als aparte release gepubliceerd — upgrade in één stap naar
**v0.3.0** samen met add-on **v0.3.0**.

### Added
- De integratie verschijnt in **Instellingen → Apparaten & Diensten → Ontdekt** (zelfde UX als Shelly, ESPHome, Music Assistant). Op HA OS via Supervisor-discovery; bij een standalone gateway via mDNS (`_ipbgw._tcp.local.`). Beide paden worden gededupliceerd tot één vermelding.
- **Gateway status sensor** (diagnostisch): toont `ok` / `degraded` / `unhealthy`, versie, uptime en open issues van de gateway. Werkt via `GET /api/v1/status` en live WebSocket-updates.
- **Discovery sweep-knop** op het gateway-apparaat: start een geforceerde veldbus-scan (`POST /api/v1/discover`) vanuit Home Assistant.
- **Fysieke IP1100PoE-knoppen als routeerbare event-entities** (issue #4): elke knop uit `getButtons` verschijnt als `event.<naam>` onder het IP1100PoE-apparaat, drukken triggert het entity-state-event plus het bus-event `ipbuilding_gateway_ha.button_pressed`. Entities worden dynamisch aangemaakt na een discovery sweep of `POST /api/v1/modules/refresh` (gateway zorgt voor de snapshot-broadcast). Gebruik een **state trigger** op `to: "press"` in automations.
- Inactieve kanalen (`active: false`) verschijnen als uitgeschakelde, verborgen entiteiten — inschakelen via **Instellingen → Apparaten & entiteiten** wanneer de bedrading klaar is (sinds 0.1.2).
- Dashboard-voorbeeld (`dashboard.md`) met Lovelace-glance, discover-knop en issues-kaart.

### Changed
- Config flow herschreven naar het Music Assistant-patroon: aparte `hassio`- en `zeroconf`-stappen met bevestiging; handmatige host/poort blijft fallback.
- **Apparaatboom in drie lagen:** IPBuilding Gateway → module (Relay / Dimmer / Input) → kanaal-entiteit. Modules worden expliciet geregistreerd; `sw_version` komt van de gateway-status-API.
- Kanaal-apparaten tonen **Relay** / **Dimmer** / **Input** i.p.v. hardware-SKU in de UI; hardwaremodel blijft op het module-apparaat.
- Kamers uit `devices.json` (`room`) worden als **suggested area** voorgesteld bij onboarding; bestaande handmatige area-toewijzingen worden niet overschreven.
- Passende iconen voor lights en switches (dimmer, lamp, ventilator, stopcontact, …).
- WebSocket-verbinding rustiger: server-side keep-alive 60 s, kortere reconnect-backoff, minder ruis in het HA-log bij normale cycli.
- Add-on en companion worden in lockstep uitgebracht op hetzelfde versienummer.

### Fixed
- **Ontdekt-lijst werkt:** zeroconf-parser gebruikt SRV host/poort (niet alleen TXT); zonder deze fix verscheen er niets in Ontdekt ondanks een correcte broadcast.
- **Dimmers werken:** licht- en switch-entiteiten sturen `DIM` i.p.v. `ON`/`OFF`; helderheid uit de service call of laatste bekende niveau.
- **Inactieve kanalen:** `active: false` schakelt entiteiten uit i.p.v. ze te verwijderen; registry-sync past disable/hide correct toe.
- **Power-sensors:** geen dubbele apparaatnaam meer in de weergavenaam (bijv. `sensor.achterdeur_licht_power` i.p.v. dubbeling).
- Home Assistant **2026.3**-compatibiliteit voor dimmer `color_modes` en entity naming.
- Vertalingen en manifest voldoen aan hassfest/HACS (schema `strings.json`, repo-topics).

### Notes
- Installeer **companion v0.3.0** en **add-on v0.3.0** samen. Vanaf **0.1.0** is dit de enige upgrade-stap die je nodig hebt.
- Vereist een gateway die `modules` en status in de API/ WebSocket exposeert (add-on v0.3.0).

## [0.2.2] — 2026-06-15

> Opgenomen in **[0.3.0]** hierboven.

### Changed
- Module and channel devices now show **Relay** / **Dimmer** / **Input** instead of the hardware SKU (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) in Apparaat-info and the “Verbonden via …” chain. The hardware model remains on the parent module device's `model` field; operator-configured module names in `devices.json` are still respected (issue #2 follow-up).
- Channel `device_info` now forwards the gateway's `room` field as `suggested_area`, so the onboarding “Naam geven en toewijzen” screen preselects the matching HA area. After platform setup, `_suggest_channel_areas` resolves existing HA areas by name and assigns the `area_id` automatically — without overwriting an operator's manual area assignment (issue #2).
- Light entities now pick their icon from the channel's `semantic_type` and `device_type` via `entity_icon()` in `entity.py`: `mdi:brightness-6` for dimmer-driven lights, `mdi:lightbulb` otherwise. Switch entities now set the same icon mapping, picking between `mdi:fan`, `mdi:power-plug`, `mdi:toggle-switch-variant`, etc., instead of the default switch icon.

## [0.2.1] — 2026-06-15

> Opgenomen in **[0.3.0]** hierboven.

### Fixed
- The three field modules (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) now appear as devices in Home Assistant. The previous release relied on the `via_device` link to auto-create the module devices, but Home Assistant does not create a parent device from a `via_device` reference alone — a hub that fronts other devices must register them explicitly. The companion now fetches `GET /api/v1/modules` at setup and registers the gateway plus each module device, so the full gateway → module → channel tree is built even for modules whose channels are all inactive (e.g. the input module).

## [0.2.0] — 2026-06-15

> Opgenomen in **[0.3.0]** hierboven.

### Changed
- Companion now builds a 3-tier device tree: `IPBuilding Gateway` → per-module device (e.g. `IP0200PoE`) → per-channel entity. Channels reference their parent module via `via_device` (module devices are registered explicitly in v0.2.1).
- Channel `device_info` now uses the parent module's product model (`IP0200PoE` / `IP0300PoE` / `IP1100PoE`) instead of the channel's `semantic_type` or `device_type`.
- Tier-1 gateway device now shows `model="IPBuilding Gateway Software"` and `sw_version` from the gateway's `/api/v1/status` (issue #14).
- Manifest metadata updated: `iot_class: local_push` (was `local_polling`), and added `quality_scale`, `issue_tracker`, `documentation`.
- The companion coordinator now consumes the `modules` field from the WebSocket `snapshot` payload (previously dropped) and exposes it via a `modules` property plus a `module_for_channel` helper for the entity platforms.

### Notes
- Requires the IPBuilding Gateway add-on (or standalone gateway) to expose `modules` in its `GET /api/v1/modules` and WebSocket `snapshot` response. This is already shipped in the gateway repo.

## [0.1.5] — 2026-06-15

> Opgenomen in **[0.3.0]** hierboven.

### Fixed
- Power-sensor entities no longer have the device name embedded in the
  entity's display name. The previous `f"{name} Power"` description combined
  with `has_entity_name=True` produced names like
  `achterdeur_licht achterdeur_licht Power`, which HA slugged to
  `sensor.achterdeur_licht_achterdeur_licht_power`. The description now
  uses `name="Power"`, so a device named "achterdeur_licht" produces a
  clean `sensor.achterdeur_licht_power`.

## [0.1.4] — 2026-06-14

> Opgenomen in **[0.3.0]** hierboven.

### Fixed
- Dimmer light and switch entities now send `DIM` commands to the gateway
  instead of `ON`/`OFF`. The northbound API only accepts `DIM` for dimmer
  modules; relay-style commands were rejected with HTTP 400, so dimmers
  appeared broken while relays worked.
- Dimmer turn-on uses the brightness from the service call (`kwargs`) when
  present, otherwise the last known level, otherwise 100%.
- Dimmer detection uses `device_type == "dimmer"` instead of the presence of
  a `level` field in the initial snapshot.

## [0.1.3] — 2026-06-14

> Opgenomen in **[0.3.0]** hierboven.

### Fixed
- Channels with `active: false` are now correctly **disabled** in Home
  Assistant instead of being deleted. The runtime diff in `coordinator`
  detected active-flips via `added & removed`, which is always empty (the two
  sets are disjoint by construction), so flipping a channel to `active: false`
  removed its entity and registry entry instead of disabling it. Flips are now
  detected on the device id alone.
- `coordinator` registry sync no longer no-ops: it matched entries with
  `async_get_entity_id(DOMAIN, DOMAIN, …)` (wrong entity domain), so the
  disable/hide flags were never applied. Reconciliation now scans the registry
  by `platform` + `unique_id`.
- Cold start: a channel already set to `active: false` whose entity was
  previously registered *enabled* is now disabled on the next snapshot
  (`apply_active_registry_defaults` only affects brand-new registry entries).
  A user who manually re-enables a disabled entity is no longer fought on every
  steady-state snapshot — only freshly-seen and flipped ids are reconciled.

### Changed
- WebSocket keep-alive: client-side `heartbeat` and `receive_timeout` are
  disabled. The gateway (server-side) drives the PINGs at 60s intervals.
  This avoids a known aiohttp 3.13.5 client-PONG race (aio-libs/aiohttp#12030)
  that caused a reconnect every 30s in simulated mode.
- Reconnect backoff capped at 5s (was 30s) and a ±20% jitter is applied to
  each sleep so simultaneous gateway restarts don't produce a thundering
  herd of reconnects.
- `_receive_loop` now distinguishes graceful server-initiated closes
  (DEBUG log) from real errors (WARNING), so the HA log stays readable
  during normal keep-alive cycles.

### Notes
- Gateway must also be updated: `gateway_api.py` heartbeat raised 30 → 60.

## [0.1.2] — 2026-06-14

> Opgenomen in **[0.3.0]** hierboven.

### Added
- Shared `entity.apply_active_registry_defaults` helper. Channels reported by
  the gateway with `active: false` (e.g. relays that are wired-up but not yet
  configured) are now registered in Home Assistant as
  `entity_registry_enabled_default=False` and
  `entity_registry_visible_default=False`, matching the HA-IPBuilding button
  pattern. The operator enables them from Instellingen → Apparaten & entiteiten
  when the wiring is done.

### Changed
- Requires the IPBuilding Gateway add-on to expose inactive channels in its
  `GET /api/v1/devices` and WebSocket `snapshot.devices` response.

## [0.1.1] — 2026-06-12

> Opgenomen in **[0.3.0]** hierboven.

### Fixed
- Dimmer lights no longer declare both `BRIGHTNESS` and `ONOFF` in
  `supported_color_modes` — Home Assistant 2026.3 rejects that combination.
- Light entity names are derived from the device registry (`name=None` +
  `has_entity_name=True`) instead of duplicating the device name on the entity.

### Changed
- Consolidated `LightEntityDescription` / `SwitchEntityDescription` imports
  to match Home Assistant 2026.3 module layout.

## [0.1.0] — 2026-06-05

> Vervangen door **[0.3.0]** voor upgrades; bewaard als historie.

### Added
- Eerste publicatie als zelfstandige HACS Integration
- Light entities (relay ON/OFF + dimmer BRIGHTNESS)
- Switch entities (relay/dimmer met semantic_type switch/plug/fan)
- Button event entities (IP1100PoE fysieke knop → `ipbuilding_gateway_ha.button_pressed` event)
- Sensor entities (per-kanaal current_watt)
- Supervisor auto-detectie (geen handmatige host/poort nodig wanneer add-on actief is)
- Handmatige config flow met validatie via `GET /api/v1/devices`
- WebSocket-coordinator met automatische reconnect
- Nederlandse en Engelse vertalingen

[Unreleased]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.0...v0.3.0
[0.2.2]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.5...v0.2.0
[0.1.5]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/markminnoye/ipbuilding-gateway-ha/releases/tag/v0.1.0
