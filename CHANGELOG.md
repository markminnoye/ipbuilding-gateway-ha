# Changelog

Alle notable wijzigingen aan deze custom component worden hier gedocumenteerd.

Het format is gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/),
en dit project volgt [Semantic Versioning](https://semver.org/lang/nl/).

## [Unreleased]

## [0.1.5] — 2026-06-15

### Fixed
- Power-sensor entities no longer have the device name embedded in the
  entity's display name. The previous `f"{name} Power"` description combined
  with `has_entity_name=True` produced names like
  `achterdeur_licht achterdeur_licht Power`, which HA slugged to
  `sensor.achterdeur_licht_achterdeur_licht_power`. The description now
  uses `name="Power"`, so a device named "achterdeur_licht" produces a
  clean `sensor.achterdeur_licht_power`.

## [0.1.4] — 2026-06-14

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

### Fixed
- Dimmer lights no longer declare both `BRIGHTNESS` and `ONOFF` in
  `supported_color_modes` — Home Assistant 2026.3 rejects that combination.
- Light entity names are derived from the device registry (`name=None` +
  `has_entity_name=True`) instead of duplicating the device name on the entity.

### Changed
- Consolidated `LightEntityDescription` / `SwitchEntityDescription` imports
  to match Home Assistant 2026.3 module layout.

## [0.1.0] — 2026-06-05

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

[Unreleased]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/markminnoye/ipbuilding-gateway-ha/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/markminnoye/ipbuilding-gateway-ha/releases/tag/v0.1.0
