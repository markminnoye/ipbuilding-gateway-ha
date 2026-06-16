# Changelog

Alle notable wijzigingen aan deze custom component worden hier gedocumenteerd.

Het format is gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/),
en dit project volgt [Semantic Versioning](https://semver.org/lang/nl/).

## [Unreleased]

## [0.3.0] — 2026-06-16

### Added
- The integration now appears in **Instellingen → Apparaten & Diensten → Ontdekt** (same UX as Shelly, ESPHome, Music Assistant). On HA OS the add-on uses Supervisor discovery; on a standalone gateway the broadcast over mDNS (`_ipbgw._tcp.local.`) is picked up. Both channels are deduplicated automatically so the operator only sees a single entry.

### Changed
- Config flow rewritten along the Music Assistant pattern. Discovery is now done by dedicated `async_step_hassio` and `async_step_zeroconf` handlers with explicit confirmation steps, instead of the previous silent auto-create in the manual step. The manual step remains as a fallback for remote or unreachable setups.

### Fixed
- The Discovered entry now actually shows up. An earlier draft of the zeroconf flow tried to read host and port from the TXT record properties, but Home Assistant puts those on the SRV/A-record instead (as `ZeroconfServiceInfo.host` and `.port`). The parser now uses the SRV values as the source of truth and only falls back to the TXT for back-compat with older gateways. Without this fix, the discovery log showed `Invalid zeroconf payload ('host or port missing from zeroconf properties')` and nothing reached the Discovered list, even though the broadcast itself was correct.

## [0.2.2] — 2026-06-15

### Changed
- Module and channel devices now show **Relay** / **Dimmer** / **Input** instead of the hardware SKU (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) in Apparaat-info and the “Verbonden via …” chain. The hardware model remains on the parent module device's `model` field; operator-configured module names in `devices.json` are still respected (issue #2 follow-up).
- Channel `device_info` now forwards the gateway's `room` field as `suggested_area`, so the onboarding “Naam geven en toewijzen” screen preselects the matching HA area. After platform setup, `_suggest_channel_areas` resolves existing HA areas by name and assigns the `area_id` automatically — without overwriting an operator's manual area assignment (issue #2).
- Light entities now pick their icon from the channel's `semantic_type` and `device_type` via `entity_icon()` in `entity.py`: `mdi:brightness-6` for dimmer-driven lights, `mdi:lightbulb` otherwise. Switch entities now set the same icon mapping, picking between `mdi:fan`, `mdi:power-plug`, `mdi:toggle-switch-variant`, etc., instead of the default switch icon.

## [0.2.1] — 2026-06-15

### Fixed
- The three field modules (`IP0200PoE`, `IP0300PoE`, `IP1100PoE`) now appear as devices in Home Assistant. The previous release relied on the `via_device` link to auto-create the module devices, but Home Assistant does not create a parent device from a `via_device` reference alone — a hub that fronts other devices must register them explicitly. The companion now fetches `GET /api/v1/modules` at setup and registers the gateway plus each module device, so the full gateway → module → channel tree is built even for modules whose channels are all inactive (e.g. the input module).

## [0.2.0] — 2026-06-15

### Changed
- Companion now builds a 3-tier device tree: `IPBuilding Gateway` → per-module device (e.g. `IP0200PoE`) → per-channel entity. Channels reference their parent module via `via_device` (module devices are registered explicitly in v0.2.1).
- Channel `device_info` now uses the parent module's product model (`IP0200PoE` / `IP0300PoE` / `IP1100PoE`) instead of the channel's `semantic_type` or `device_type`.
- Tier-1 gateway device now shows `model="IPBuilding Gateway Software"` and `sw_version` from the gateway's `/api/v1/status` (issue #14).
- Manifest metadata updated: `iot_class: local_push` (was `local_polling`), and added `quality_scale`, `issue_tracker`, `documentation`.
- The companion coordinator now consumes the `modules` field from the WebSocket `snapshot` payload (previously dropped) and exposes it via a `modules` property plus a `module_for_channel` helper for the entity platforms.

### Notes
- Requires the IPBuilding Gateway add-on (or standalone gateway) to expose `modules` in its `GET /api/v1/modules` and WebSocket `snapshot` response. This is already shipped in the gateway repo.

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
