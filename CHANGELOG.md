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

## [1.7.2] - 2026-06-23

### Added
- **Tandwiel-menu: "Modules opzoeken op de veldbus"** — stuurt `POST /api/v1/discover` op de gateway en toont het resultaat (`{added} toegevoegd, {changed} bijgewerkt, {removed} verwijderd` + duur) in een vervolgscherm. Vervangt de noodzaak om de discover-knop op het gateway-apparaat te zoeken. Tot ~120 s timeout (zelfde budget als de bestaande knop).
- **Tandwiel-menu: "Knoppen en module-info bijwerken"** — stuurt `POST /api/v1/modules/refresh` op de gateway en toont het aantal bijgewerkte modules en knoppen. Gebruik dit nadat je een wandknop of IP1100PoE-instelling op de module zelf hebt gewijzigd; de gateway pusht dan een WS-snapshot zodat de companion nieuwe namen/drempels oppikt zonder integratie-reload. Vindt **geen** nieuwe modules — daarvoor blijft *Modules opzoeken*.

### Changed
- **`button.ipbuilding_gateway_run_discovery_sweep` hernoemd** van "Run discovery sweep" / "Discovery sweep starten" naar "Scan field bus for modules" / "Modules opzoeken op de veldbus" zodat de naam consistent is met het nieuwe menu-item. Geen functionele wijziging.

### Fixed
- **HA 2026.6 update-listener reload** — config flow gebruikt `reload_on_update=False`; de update listener plant reload via `async_schedule_reload` i.p.v. `async_reload`. Voorkomt dubbele reload en de deprecation-warning die vanaf HA 2026.12 een error wordt.

## [1.7.1] - 2026-06-23

### Added
- **`button_standard` v9 (universele 3-slot blueprint)** — derde actie-slot `Loslaten` toegevoegd (vuurt alleen op release ná een lange druk). Secties heten nu **Indrukken / Vasthouden / Loslaten**, waarbij Vasthouden en Loslaten optioneel zijn. De blueprint kan nu ook een dimmer volledig configureren (`light.toggle` / `dim_start` / `dim_stop`) zonder dat een aparte `button_dim`-blueprint nodig is — die blijft bestaan als preset. Blueprint-naam gewijzigd naar **"IPBuilding wandknop"**. `mode:` van `single` naar `queued` (twee triggers per vasthouden moeten in volgorde lopen). Bestaande instanties blijven werken: `release_action` default is `[]` en de nieuwe trigger is gescopet met `from: "long_press"`.

### Changed
- **Blueprint-teksten gereviseerd** — `button_standard` v9, `button_dim` v8 en `button_dim_stepwise` v1 zijn inhoudelijk op elkaar afgestemd. De `Knop` en `Lamp` input-beschrijvingen zijn geüniformeerd; de "Geen helper nodig"-zin in `button_dim` is weg; de Matter-patroon-verwijzing in de Loslaten-beschrijving is ingekort. Geen gedragswijziging.
- **Versie-header onderaan** — vanaf 1.7.1 staat de `# ipbuilding_blueprint_version: N`-regel onderaan de blueprint-file in kleine letters, niet meer bovenaan. De sync in `blueprints.py` scant nu de hele file. De `**Blueprint-versie: N.**`-marker in de description (operator-zichtbaar in HA) blijft ongewijzigd.
- **Dim-blueprint beschrijvingen verduidelijkt** — `button_dim` is expliciet gemarkeerd als aanbevolen native variant; `button_dim_stepwise` als experimenteel alternatief met `input_boolean`-helper (HA 2026.3 helper-create caveat van toepassing).

### Breaking
- **`dim_button.yaml` is verwijderd uit de companion.** De deprecation-stub die sinds 0.5.0 in het package zat is niet meer meegeleverd. Bestaande automations die deze blueprint referencen stoppen met werken zodra de stub uit `config/blueprints/automation/ha_ipbuilding_gateway/` is verwijderd. Migreer door een nieuwe automatisering te maken vanuit `button_dim` (of `button_dim_stepwise` als je de HA-stapsgewijze variant wilt) en de oude uit te zetten. Vóór deze release bestond de stub alleen nog als back-compat voor installaties die in de 0.5.0-tijd zijn begonnen.

## [1.7.0] - 2026-06-23

### Added
- **`ha_ipbuilding_gateway.dim_start` en `ha_ipbuilding_gateway.dim_stop` services** (entity-targeted, alleen `light.`). Starten/stoppen de native hold-to-dim ramp op een IP0300PoE-kanaal via de gateway-acties `DIM_START` / `DIM_STOP`. De IP0300PoE dimt zelf en draait de richting automatisch om bij elke volgende hold — geen `repeat`-lus, geen helper, geen step-configuratie in HA meer. Vereist gateway add-on met `DIM_START`/`DIM_STOP`-ondersteuning (branch `feature/dimmer-downstream-td`, gateway ≥ **1.1.0**).
- **`button_dim` v8** gebruikt de nieuwe services i.p.v. de oude `repeat` + `brightness_step_pct` + `direction_helper` + endpoint-trigger logica. Korte druk → `light.toggle`, vasthouden → `dim_start`, loslaten na hold → `dim_stop`. De `direction_helper` / `dim_step_pct` / `dim_interval_ms` / `dim_boundary_pct` inputs zijn verwijderd.
- **`button_dim_stepwise` blueprint (alternatief)** — de oude HA-gestuurde, stapsgewijze dim-loop (met `input_boolean` richting-helper) blijft beschikbaar als apart alternatief voor wie de native ramp niet wil. Native `button_dim` blijft de aanbevolen keuze.

### Changed
- **Dimmer-`light.toggle` gebruikt nu het native `TOGGLE`-commando** (`T<ch>991000`) i.p.v. `DIM <laatste>` / `DIM 0`. De light-entity overschrijft `async_toggle`: een korte druk (en elke `light.toggle`) schakelt via het eigen laatst-niveau-geheugen van de IP0300PoE — robuust ook als HA's gecachte helderheid verouderd is (bv. na een peer-knopdruk die de gateway niet zag). Relays en geparametriseerde toggles vallen terug op het standaardgedrag.

## [1.6.0] - 2026-06-22

### Removed
- **`button_cover` blueprint** — ongevalideerd voorbeeld zonder cover-hardware in de testopstelling. Hold-to-move / release-to-stop hoort in een eigen automatisering (device triggers op `long_press` + `release`) of via `button_standard` voor eenvoudig open/sluiten op druk.

### Breaking
- **`button_cover` is no longer shipped.** Bestaande instanties op een lokale kopie in `config/blueprints/…/button_cover.yaml` blijven werken tot je die file verwijdert. Voor gordijnen: `long_press` → `cover.open_cover` / `cover.close_cover`, `release` → `cover.stop_cover` op de knop-event-entity.

## [1.5.0] - 2026-06-22

### Removed
- **`button_scene` blueprint** — redundant with `button_standard`, which already supports `scene.turn_on` (and mixed actions) via the action-editor. New installs no longer receive this file from the companion package.

### Breaking
- **`button_scene` is no longer shipped.** Bestaande automation-instanties die op een eerder gesynchroniseerde kopie in `config/blueprints/…/button_scene.yaml` draaien blijven werken tot je die file verwijdert. Voor nieuwe knop→scene-mappings: gebruik `button_standard` en kies bij korte/lang druk de actie **Scène: Activeren**.

## [1.4.1] - 2026-06-22

### Fixed
- **Race tussen `single_press` en de trailing `release` in `button_dim` (v6 → v7) en `button_cover` (v6 → v7).** De gateway stuurt bij een korte tik `single_press` én `release` vlak na elkaar. De top-level `release`-trigger reageerde óók op die korte-druk-release: in `button_dim` (`mode: restart`) kon dat de net gestarte `single_press`-toggle cancellen (korte druk deed dan niets); in `button_cover` (`mode: single`) kon de trailing release een geconfigureerde korte-druk-actie ongedaan maken via `cover.stop_cover`. De `release`-trigger is nu gescopet met `from: "long_press"`, zodat hij alléén vuurt op een release die een hold afsluit (loop stoppen + richting flippen / cover stoppen). `button_scene` had dit probleem niet (geen release-trigger).

### Added
- **`button_scene` v4 / `button_dim` v7 / `button_cover` v7** triggeren nu direct op `single_press` en `long_press` — geen `wait_for_trigger` of raw `press`-abonnement meer. Evenknie van de `button_standard` v7 wijziging uit v1.3.0. De gateway classificeert de druk zelf, dus de race tussen raw `press` en `long_press` is weg.
- **`single_press` als entity-state vertaling** in `entity.event.button.state` voor zowel EN als NL. Na v1.3.0 vuurde de EventEntity al het `single_press`-event, maar de UI toonde "Unknown" als state omdat de vertaling ontbrak. Korte drukken tonen nu correct "Single pressed" / "Kort ingedrukt".

### Changed
- **`button_dim` v5 → v7**: `wait_for_trigger` met 600 ms timeout op de press-branch is weg; de toggle hangt nu direct aan het `single_press`-event. De `release`-trigger is gescopet met `from: "long_press"` (zie Fixed). De release-flip-guard (`trigger.from_state.attributes.event_type == 'long_press'`) blijft — een korte-druk-release mag de dim-richting niet flippen.
- **`button_scene` v3 → v4**: top-level `single_press` trigger vervangt de raw `press` trigger. `long_press` ongewijzigd.
- **`button_cover` v5 → v7**: top-level `single_press` trigger vervangt de raw `press` trigger voor de optionele korte-druk actie; de `release`-trigger is gescopet met `from: "long_press"` (zie Fixed).

### Tests
- `test_dim_blueprint_waits_on_press_before_toggling`, `test_dim_blueprint_short_press_continues_on_timeout` en `test_scene_blueprint_activates_scenes_on_press_and_long_press` zijn bijgewerkt om het v6-contract af te dwingen: geen `wait_for_trigger`, directe `single_press`-trigger, geen raw `press` in de scene-blueprint.

### Migratie
- Bestaande automation-instanties van `button_scene`, `button_dim` en `button_cover` blijven werken: de input-namen zijn ongewijzigd (`press_scene`, `long_press_scene`, `target_light`, `direction_helper`, `cover_entity`, `hold_direction`, `release_action`, `press_action`). `blueprints.py` synchroniseert de blueprint-bestanden zelf, de input-mapping blijft 1-op-1.

### Vereisten
- Gateway ≥ **1.1.0** voor de `single_press`-events. Oudere gateways sturen geen `single_press`; in dat geval vuurt de nieuwe `button_dim` v6 toggle nooit en moet de operator terugvallen op een oudere blueprint of de gateway updaten.

## [1.3.0] - 2026-06-21

### Added
- **`single_press` button event + `single_pressed` device trigger.** De gateway classificeert een korte druk nu zelf: `single_press` bij loslaten onder de drempel, `long_press` bij overschrijding van de drempel. De companion voegt `single_press` toe aan de EventEntity event-types, vuurt `ha_ipbuilding_gateway.button_single_pressed` op de HA bus, en tagt de gesture-events met hun HA/Matter-standaard naam in `event_data` (`press` → `press_start`, `single_press` → `press_end`, `long_press` → `long_press_start`). De raw `release` blijft bewust ongetagd (volgt zowel korte als lange druk, dus geen eenduidig standaard-equivalent). De automation-editor toont een nieuwe "Single pressed" device trigger. Vereist gateway ≥ 1.1.0 om de nieuwe `single_press`-events te ontvangen.

### Changed
- **`button_standard`-blueprint (v7)** triggeren nu direct op `single_press` en `long_press` — geen `wait_for_trigger` met 600 ms timeout meer. De gateway doet de press-vs-long-press-disambiguatie, dus de race tussen 600 ms timeout en de 1,5 s standaard hold-drempel is weg. Vereist gateway ≥ 1.1.0.

### Breaking
- **`button_standard` v7 verwijdert oude inputs** (`automation_name`, `automation_area`, `press_target`, `long_press_target` en de select-acties) ten gunste van volledige action-selectors. Bestaande automation-**instanties** op een eerdere `button_standard`-versie blijven verwijzen naar niet-bestaande inputs en moeten **opnieuw aangemaakt** worden na de update.

### Fixed
- **Blueprint triggers vuurden niet op event entities.** Alle
  state-triggers in de meegeleverde blueprints (`button_toggle`,
  `button_standard`, `button_dim`, `button_cover`, `button_scene`,
  `dim_button`) filterden op `to: "press"` / `"long_press"` /
  `"release"` tegen de `state`, terwijl die voor event entities een
  timestamp bevat. Het event-type leeft op `attributes.event_type`.
  Hierdoor vuurde bv. "Hal R → bureau toggle" nooit, terwijl de native
  HA-automations (device-trigger) wel werkten. Triggers zijn voorzien
  van `attribute: event_type` + `not_from: [unavailable, unknown]`.
  In `button_dim` zijn ook de templates aangepast die `trigger.state`
  vergeleken met event-namen.
- **Versie-bumps** van alle blueprints (4 → 5 voor `button_toggle`,
  2 → 3 voor `button_standard`, 3 → 4 voor `button_cover` en
  `button_dim`, 1 → 2 voor `button_scene` en `dim_button` stub) zodat
  [`blueprints.py`](custom_components/ha_ipbuilding_gateway/blueprints.py)
  de upgrade-sync triggert op bestaande HA-installaties.
- **`button_standard.yaml` press/long_press onderscheid.** Bij een
  lange druk vuurde zowel de press- als de long_press-actie: de
  gateway broadcastt direct `press` en (na de hold-drempel) opnieuw
  `long_press`, dus twee top-level triggers vuurden achter elkaar.
  Het action-blok gebruikt nu het `wait_for_trigger`-patroon uit
  [`button_dim.yaml`](custom_components/ha_ipbuilding_gateway/blueprints/automation/ha_ipbuilding_gateway/button_dim.yaml):
  één trigger op `press`, 600 ms wachten op `release` of `long_press`,
  en pas daarna de juiste actie kiezen. Korte drukken gedragen zich
  identiek; lange drukken voeren alleen nog de long_press-actie uit.
  Versie-bump 3 → 4.
- **`button_standard.yaml` timeout `UndefinedError`** (v4 had een
  tikfout in de guard). Home Assistant zet `wait.trigger` op `none`
  bij timeout — **niet** de hele `wait`-variabele. De v4-guard
  `wait is none` sloeg daardoor nooit aan op het timeout-pad, en de
  daaropvolgende `wait.trigger.to_state.attributes.event_type`-access
  op `none` gooide `UndefinedError: 'None' has no attribute 'to_state'`
  in de log bij elke korte druk. v5 volgt de community-conventie
  (HA-forum + Awesome HA Blueprints): `wait.trigger is none` voor
  het timeout-pad (→ press-actie als zachte fallback) en
  `wait.trigger is not none` voor het event-pad. Pattern is
  identiek aan wat `button_dim.yaml` al deed. Versie-bump 4 → 5.
- **`button_dim.yaml` korte-druk deed niets bij ontbrekende follow-up.**
  De short-press `wait_for_trigger` had geen `continue_on_timeout: true`,
  en de guard was `wait.trigger is not none and ... == 'release'`. Wanneer
  de gateway om welke reden dan ook geen `release` of `long_press`
  binnen 600 ms stuurde (trage bus, race, firmware-bug), stopte HA de
  automation op timeout en draaide de toggle nooit — de operator
  drukte op de knop en er gebeurde niets. v5 voegt
  `continue_on_timeout: true` toe plus een `wait.trigger is none`
  fallback-tak die alsnog de toggle uitvoert (Hue-style: de operator
  verwacht feedback). Versie-bump 4 → 5 (`button_dim.yaml`).
- **`button_standard.yaml` v6 — action-selector voor volledige vrijheid.**
  De v5-fixed `select:` (Geen / Aan / Uit / Toggle / Scene activeren)
  + `target:`-selector per fase zijn vervangen door één `selector:
  action:`-input per fase. De operator krijgt nu de volledige HA
  action-editor (zoals bij een gewone automation) en kan elke service,
  elk doel en alle data (brightness, transition, helpers, scripts,
  notificaties, …) zelf kiezen. De blueprint disambigueert alleen nog
  press vs long press; de scene-guard (`press_has_scene` /
  `long_press_has_scene`) en de vaste service-keuzes verdwijnen.
  Pattern volgt de HA-community-conventie: `sequence: !input
  press_action` in een `choose:`-tak. Versie-bump 5 → 6. Bestaande
  "Hal R → Bureau"-instanties verliezen hun `press_target`-referentie;
  heraanmaken van de automation vanaf deze blueprint is nodig
  (`blueprints.py` synchroniseert het bestand zelf, maar de input-
  namen zijn gewijzigd).

### Changed
- **`button_toggle` v5**: terug naar de **`target:`-selector** (HA
  Motion-activated Light UX). De `entity:`-selector uit v2/v4 was
  te nauw voor de dominante operator-flow ("toggle de lamp(en) in
  deze ruimte"). `light_target` accepteert nu één of meerdere
  entiteiten, een apparaat of een hele ruimte via de tabs Entiteit /
  Apparaat / Ruimte. De actie geeft het input rechtstreeks door
  (`target: !input light_target`) zodat meerdere doelen of een
  area-toggle ondersteund worden.

### Tests
- `test_toggle_blueprint_uses_target_selector` vervangt de
  omgekeerde entity-only test.
- `test_button_blueprints_use_event_type_attribute_on_triggers` is
  een nieuwe regression-test die voor elke blueprint afdwingt dat
  `attribute: event_type` op de trigger staat.
- Dim-template-assertions verwijzen nu naar
  `attributes.event_type` in plaats van `state`.

### Migratie
- Bestaande automations die vanuit de oude `button_toggle`-blueprint
  zijn aangemaakt behouden hun opgeslagen YAML (inclusief het foute
  `to: "press"` zonder `attribute`); die moeten **opnieuw
  aangemaakt** worden of handmatig de trigger + target fixen. De
  blueprint-sync upgrade't alleen het blueprint-bestand zelf.
- Legacy `ipbuilding_gateway_ha/button_toggle.yaml` op HA kan
  handmatig verwijderd worden; de v5-versie staat onder
  `ha_ipbuilding_gateway/`.

### Removed
- **`button_toggle.yaml`** — verwijderd. De combinatie van
  `button_standard` met de action-selector (kies
  `homeassistant.toggle` als service op een `target:` van lampen /
  schakelaars / ruimte) dekt dezelfde flow met meer vrijheid. Geen
  nieuwe instanties meer vanuit deze blueprint; bestaande
  automations blijven werken op hun opgeslagen YAML tot de
  operator ze verwijdert of heraanmaakt vanuit
  `button_standard.yaml`.

## [1.2.2] - 2026-06-19

### Changed
- **Integration heet nu "IPBuilding Gateway"** in plaats van "IPBuilding Gateway Companion". De `manifest.json` `name` is bijgewerkt; de device-tree in de Companion blijft gateway → module → kanaal.

### Added
- **Discovery TXT schema v2**: nieuwe TXT-velden `sw` (alias van `version`), `host`, `port` en `mac` worden nu gelezen. `DISCOVERY_SCHEMA_VERSION` is gebumped naar 2.
- **`mac` en `sw_version` in `GatewayDiscoveryInfo`**. Lege `mac` wordt als `None` doorgegeven (Supervisor add-on heeft geen unieke interface-MAC).

### Changed
- **mDNS-first discovery** (zoals Shelly). `async_step_zeroconf` werkt nu ook voor Supervisor add-ons — de duplicate-guard `already_discovered_addon` is verwijderd. Beide discovery-paden (zeroconf en HassIO) gebruiken dezelfde `async_step_confirm` step.
- **Naamgeving bij toevoegen (D3)**: één nieuwe `confirm` step vervangt `hassio_confirm` en `discovery_confirm`. Default naam = eerste 8 tekens van `instance_id` (of `gateway` als fallback), operator kan deze aanpassen. De gekozen naam komt in de config-entry title (`IPBuilding Gateway (<naam>)`) en in de `flow_title` van de Discovered-card.
- **`async_step_hassio` leest nu `instance_id`** uit de Supervisor `config` payload, zodat de unique_id tussen zeroconf en HassIO discovery aligned is. De fallback is het Supervisor discovery UUID.
- **Translaties**: nieuwe `flow_title` en `confirm` step in `strings.json`, `translations/nl.json` en `translations/en.json`. De placeholders `{addon}`, `{version}`, `{url}` en `{name}` worden nu in één beschrijvingsblok gebruikt.

### Tests
- Nieuwe tests: `tests/test_discovery_parser.py` (schema v2 + mac + sw-fallback) en `tests/test_config_flow_confirm.py` (default naam truncatie, `flow_title` template, refactor smoke-tests).

### Vereisten
- Gateway ≥ **1.0.4** om de nieuwe TXT-velden te gebruiken. Oudere gateways blijven werken dankzij fallback naar `version`/`base_url`.

## [1.2.1] - 2026-06-19

### Fixed
- **Supervisor discovery accepteert nu custom-repo slugs.** `async_step_hassio` in `config_flow.py` gebruikt een suffix-match (`*ipbuilding_gateway`) in plaats van een strikte gelijkheid. Hierdoor verschijnt de IPBuilding Gateway Companion in **Instellingen → Apparaten & diensten → Ontdekt** ook wanneer de add-on via een custom repository is geïnstalleerd (slug zoals `3059e002_ipbuilding_gateway`). De vaste store-slug `ipbuilding_gateway` blijft uiteraard ook werken.

## [1.2.0] - 2026-06-19

### Breaking
- **Onboarding-wizard verwijderd** uit de koppel-flow. Een verse installatie laat het tandwiel-menu (`Configure`) de plek zijn waar de operator expliciet gateway-ruimtes aan HA-areas koppelt. De `_suggest_channel_areas` stille koppeling (op bestaande areas met dezelfde naam) en de `suggested_area` hint op devices blijven werken.
- **Button-import verwijderd.** De wizard importeerde IP1100PoE-knop → actie mappings uit `getButtons` naar `automations.yaml`; dit moet nu via de meegeleverde blueprints (`button_standard`, `button_toggle`, `button_dim`, `button_cover`, `dim_button`) of eigen HA-automations.
- **Pre-change snapshot:** de laatste versie met de volledige wizard is getagged als `v1.1.0-with-onboarding-wizard` op `b80346f` — gebruik `git checkout v1.1.0-with-onboarding-wizard -- <paths>` om de wizard-code terug te halen.

### Added
- **Room → area mapping als tandwiel-optie.** De options-flow heeft één menu-item *Ruimtes koppelen* (`map_rooms`) dat een `AreaSelector` per gateway-ruimte toont. Een leeg veld valt terug op een HA-area met dezelfde naam (of maakt die aan); de keuze wordt in `entry.options[CONF_ROOM_MAPPINGS]` opgeslagen en door `__init__._apply_stored_room_mappings` opnieuw toegepast bij elke reload.
- **Ruimtes koppelen wordt automatisch geopend** meteen na het toevoegen van een gateway. `_maybe_offer_room_mapping` start de options-flow zelf (`hass.config_entries.options.async_init`) zodra er gateway-ruimtes gekend zijn en er nog geen mapping is opgeslagen; `async_step_init` slaat dan het menu over en toont meteen *Ruimtes koppelen*. Een nieuwe `entry.options[CONF_ROOM_MAPPING_OFFERED]`-vlag zorgt dat dit maar één keer per gateway gebeurt, ook als de operator het scherm sluit zonder op te slaan.

### Changed
- `config_flow.py`: alle discovery-paden (`async_step_user`, `async_step_hassio_confirm`, `async_step_discovery_confirm`) maken nu direct `async_create_entry` aan. Geen `_ob_*` state, geen wizard-spinner meer in de koppel-flow.
- `async_step_hassio_confirm` haalt `host`/`port` nu uit `self._discovery_info` (latente `NameError` in de oude code als de form werd geopend zonder `user_input`).
- `options_flow.py` herschreven tot één `IPBuildingOptionsFlowHandler(OptionsFlow)` met menu `["map_rooms"]` — geen `OnboardingFlowMixin` meer.
- `_apply_onboarding_results` hernoemd naar `_apply_stored_room_mappings` en doet alleen nog de room-mapping; button-import is weg.
- Debug agent-log blocks in `config_flow.async_step_hassio` en `_import_button_automations` verwijderd.

### Removed
- Wizard-modules: `onboarding_flow.py`, `gateway_rest.py`, `button_automation_builder.py`, `automation_store.py`, `target_resolver.py`, `button_mapping.py`.
- Constanten: `CONF_ONBOARDING_COMPLETED`, `CONF_ONBOARDING_SKIPPED`, `CONF_IMPORT_BUTTONS`, `CONF_BUTTON_AUTOMATIONS`.
- i18n: alle `ob_*` / `onboarding_*` steps, `preparing` / `discovery` / `modules_refresh` progress keys, `onboarding_complete` abort.
- Tests: `test_onboarding_wiring.py`, `test_button_automation_builder.py`, `test_button_mapping.py`, `test_automation_store.py`.

## [1.1.0] - 2026-06-19

### Added
- **Onboarding-wizard in de koppel-flow.** Na het toevoegen van de gateway loopt de wizard meteen — *ruimtes → areas* → *overzicht van nieuwe entiteiten* → *knoppen importeren* — vóór de integratie wordt aangemaakt. Dit vervangt het kale entiteiten-overzicht als eerste scherm.
- **Ruimte → HA-area mapping.** Gateway-ruimtenamen worden als veldlabel getoond en gekoppeld aan Home Assistant areas; een gelijknamige bestaande area wordt voorgeselecteerd en ontbrekende areas worden aangemaakt. Geldt voor relais/dimmers én IP1100PoE-knoppen.
- **Knop-automatiseringen worden daadwerkelijk aangemaakt** in `automations.yaml`: per geconfigureerde knopactie een HA device-trigger-automation met alias `"<knop> → <doel>"`, actie `on`/`off`/`toggle` conform de inputmodule, en een stabiel `ipb_map_*` id (idempotent — handgemaakte automatiseringen blijven behouden). De integratie roept automatisch `automation.reload` aan.
- **Knop-doelen worden voorgevuld** in de "wizard opnieuw"-flow op basis van de bestaande mapping van de inputmodule.
- IP1100PoE-knoppen zijn standaard **ingeschakeld** in de entity registry; inactieve relay/dimmer-kanalen (`active: false` in `devices.json`) blijven disabled+hidden.

### Changed
- De onboarding-wizard draait nu **in de config flow** i.p.v. een automatisch gestarte OptionsFlow. De OptionsFlow blijft beschikbaar voor *Configure → wizard opnieuw*.
- **Discovery-scan verwijderd** uit de wizard. Een sweep draait alleen nog stil wanneer de gateway nog geen devices kent (verse installatie).
- Knop-automatiseringen zijn nu **standaard ingeschakeld** en gebruiken het moderne `triggers`/`conditions`/`actions`-schema. `allOn`/`allOff` worden voorlopig overgeslagen in plaats van een ongeldige module-scope groep weg te schrijven.

### Fixed
- **Coordinator-crash bij elke refresh** en mislukte onboarding-discovery: de per-entity listener-dict botste met `DataUpdateCoordinator._listeners` (hernoemd naar `_entity_listeners`).
- **Lege wizard-menu's/labels:** onboarding-vertalingen stonden onder de verkeerde flow-sectie; ze staan nu op de juiste plek. Dynamische velden (ruimtes, knoppen) worden op naam gekeyd zodat het label klopt.
- **Wizard liep vast na de ruimte-stap:** ongeldige `show_progress`-overgang plus een reload midden in de wizard die de coordinator onderuithaalde (`KeyError`).
- **Unload-fout** `'_asyncio.Task' object is not callable`: de bootstrap-sweep registreerde een Task in plaats van een callable op `async_on_unload`.
- Geen scanscherm meer bij het koppelen van een reeds gevulde gateway.

## [1.0.0] - 2026-06-18

### Breaking
- **HA-domain hernoemd** van `ipbuilding_gateway_ha` naar `ha_ipbuilding_gateway`. Dit is een **breaking change** voor bestaande HA-installaties. Verwijder de oude integratie uit Instellingen → Apparaten & Diensten, herinstalleer via HACS, en pas je Lovelace-cards, scripts en automations aan om de nieuwe entity-IDs te gebruiken (`light.ha_ipbuilding_gateway_*`, `switch.ha_ipbuilding_gateway_*`, `event.ha_ipbuilding_gateway_*`, `sensor.ha_ipbuilding_gateway_*`). De folder `config/blueprints/automation/ipbuilding_gateway_ha/` moet je zelf hernoemen naar `config/blueprints/automation/ha_ipbuilding_gateway/` (of de blueprints opnieuw aanmaken vanuit de UI). Geen data-verlies in `devices.json` (gateway-kant). Zie de [README migratie-sectie](README.md#upgrading-from-a-pre-10-install) voor de volledige stappen.
- **Bus event-types** hernoemd: `ipbuilding_gateway_ha.button_pressed`, `.button_long_pressed`, `.button_released` → `ha_ipbuilding_gateway.button_pressed`, `.button_long_pressed`, `.button_released`. HA Core events volgen automatisch omdat ze via `f"{DOMAIN}.{suffix}"` worden opgebouwd; eventuele hardcoded referenties in eigen automations moeten worden bijgewerkt.

### Changed
- **Repository hernoemd** van `markminnoye/ipbuilding-gateway-ha` naar `markminnoye/ha-ipbuilding-gateway`. GitHub zet een 301-redirect in zodat bestaande clones, issues en HACS custom-repository URL's blijven werken. (Vorig release.)
- **Eerste major release (1.0.0)** — markeert de eerste stabiele versie van de volledige field-bus hub + companion stack.

## [0.4.3] - 2026-06-18

### Fixed
- **Correcte lichtstatus direct na een herstart.** Vóór deze versie zette de companion elk kanaal waarvan de gateway (nog) geen echte aan/uit-stand had doorgegeven op "uit" — inclusief relay-kanalen die alleen nog op hun eerste UDP-commando wachtten, en dimmer-kanalen die nog geen level-reply teruggestuurd hadden. Een verse herstart van de gateway of de companion zag er daardoor uit als "alles uit", ook al brandden er lampen. De companion mapt nu "unknown" en "inactive" netjes op een onbekende staat in Home Assistant, zodat HA "Onbekend" toont in plaats van "uit" tot de gateway de eerste echte status levert. Werkt samen met [IPBuilding Gateway v0.4.3](https://github.com/markminnoye/IPBuilding-Gateway/releases/tag/v0.4.3), die de live kanaalstatus bij het opstarten ophaalt zodat de eerste snapshot direct klopt.

## [0.4.0-rc.11] - 2026-06-18

### Changed
- **Packaged blueprints niet meer in de HA Blueprint-picker** — `async_install_packaged_blueprints` is vanaf nu een no-op. De blueprint-files blijven in de repo (referentie + source-only tests), maar worden niet meer naar `config/blueprints/automation/ipbuilding_gateway_ha/` gekopieerd. De publieke API (`async_install_packaged_blueprints`, `invalidate_packaged_blueprints_cache`) blijft bestaan voor backward compatibiliteit. De README-sectie is herschreven: "Button automations" wijst de operator op community-blueprints (Z2M Hue Dimmer Ultimate Controller, IKEA STYRBAR) en de standaard HA-flow.
- **`manifest.json` dependencies** — `blueprint` is verwijderd (de companion shipt niets meer naar HA-blueprint).

### Notes
- **Bestaande installs** — `config/blueprints/automation/ipbuilding_gateway_ha/*.yaml` files blijven staan op HA. De operator kan ze zelf verwijderen via de HA Blueprint-picker of de filesystem. Bestaande automations die `use_blueprint` refereren blijven werken totdat de operator de blueprint-files verwijdert.
- **Nieuwe installs** — De Blueprint-picker toont geen IPBuilding-blueprints meer. Operators bouwen acties via community-blueprints of de standaard HA-flow.

## [0.4.0-rc.10] - 2026-06-18

### Changed
- **`button_toggle.yaml` (v4)** — `automation_name` input en `alias: !input automation_name` zijn verwijderd. De automation-naam wordt nu direct in de Home Assistant save-popup ingevuld (die opent altijd bij het aanmaken van een nieuwe automation). De popup prefilt de blueprint-name "IPBuilding wandknop — toggle"; de operator typt de gewenste friendly naam en bevestigt. Dit voorkomt de mismatch tussen de blueprint-input en de popup-default.

## [0.4.0-rc.9] - 2026-06-18

### Notes
- **`button_cover.yaml` is een voorbeeld** — de blueprint-naam begint nu met `[Voorbeeld]` en de description legt uit dat de companion-ontwikkelaars geen `cover`-hardware hebben om dit te valideren. Bugs graag melden via GitHub Issues met label `cover-blueprint`.
- **`button_toggle.yaml`** — de zin "The automation area is asked by Home Assistant in the popup that appears after you press 'Opslaan' — it is not a blueprint input" is verwijderd uit de description om dubbele uitleg te vermijden.
- **HA-frontend rename-popup** — Home Assistant opent altijd een "hernoem"-popup bij het aanmaken van een nieuwe automation, ook vanuit een blueprint. De popup vult de **blueprint-name** als default in (bv. "IPBuilding wandknop — toggle"), niet de `automation_name` uit de blueprint. De `alias: !input automation_name` wordt wel correct in de opgeslagen YAML gezet; pas in de popup de naam aan vóór je bevestigt als je de blueprint-naam niet wilt.

## [0.4.0-rc.8] - 2026-06-18

### Changed
- **`button_toggle.yaml` (v2) — minimale UX** — vervangt de `target:`-selector (die tabbladen voor entity / apparaat / ruimte toonde plus een "Doel toevoegen"-knop) door een `entity:`-selector met `multiple: false`. Het veld `target_kind` en `target_area` zijn verwijderd; de toggle-blauprint is nu één entity op één knop. De `automation_area` input is verwijderd: HA vraagt de ruimte in de popup die verschijnt na "Opslaan", en een tweede "Ruimte"-veld in de blueprint was verwarrend.
- **`button_standard.yaml` (v2) — target-selector + scene-guard** — vervangt 8 separate velden (`*_target_kind`, `*_entity_target`, `*_area` per fase) door één `target:`-veld per fase. De `target:`-selector biedt automatisch entity, meerdere entities, of een ruimte in één widget. Een afgeleide `*_has_scene` variable checkt of het target een scene bevat; `on`/`off`/`toggle` worden defensief overgeslagen wanneer dat zo is, en `activate_scene` wordt overgeslagen wanneer er geen scene in het target zit.

## [0.4.0-rc.7] - 2026-06-18

### Fixed
- **YAML 1.1 boolean coercion in blueprint `select` opties** — `value: on` en `value: off` werden door YAML als booleans (`True`/`False`) ingelezen, waardoor HA's `select`-validator ze afkeurde met `expected str for dictionary value @ data['...']['value']. Got None`. Alle optie-velden in `button_standard.yaml` zijn nu expliciet gequote (`"on"`, `"off"`, `"none"`, `"toggle"`, `"activate_scene"`). Regression-guard in `tests/test_blueprints_source.py::test_select_option_values_are_strings`.

## [0.4.0-rc.6] - 2026-06-18

### Added
- **Blueprint-set voor IP1100PoE-knoppen** — vier doelgerichte blueprints in `custom_components/ipbuilding_gateway_ha/blueprints/automation/ipbuilding_gateway_ha/`: `button_toggle` (korte druk → toggle), `button_standard` (kort + optioneel lang, met on / off / toggle / scene voor entity of alle lampen in een ruimte), `button_dim` (toggle + dim tijdens hold, vervangt `dim_button.yaml`) en `button_cover` (hold = open of close, release = stop).
- **Versioned blueprint-sync** — elke packaged blueprint heeft een `# ipbuilding_blueprint_version: N` header. De companion overschrijft bestaande blueprints op HA wanneer de package-versie hoger is. Bestanden met een `# user_modified: true` marker blijven onaangeraakt.

### Fixed
- **Dim-blueprint `max: 1` foutmelding** — `button_dim.yaml` gebruikt uitsluitend `mode: restart`; de ongeldige `max: 1` is verwijderd zodat `Message malformed: value must be at least 2 @ data['max']` niet meer optreedt bij het opslaan.
- **Helper UX-tekst** — `button_dim.yaml` legt nu het verschil uit tussen de **Naam** (mag spaties) en de **Entity ID** (alleen `a-z`, `0-9`, underscores) van de `input_boolean` direction helper.
- **Device-trigger lekt niet meer over andere knoppen** — `async_attach_trigger` in `device_trigger.py` viel terug op een lege `event_data` filter wanneer de hardware-id niet gevonden kon worden. Een lege filter matcht *iedere* `ipbuilding_gateway_ha.button_*`-event, waardoor een automatisering op één knop kon afgaan op een fysieke druk op een andere. De handler faalt nu hard met een `ValueError` wanneer de hardware-id ontbreekt; regressie-guard in `tests/test_device_trigger.py`.

### Deprecated
- **`dim_button.yaml`** is vervangen door `button_dim.yaml` en blijft alleen als stub bestaan. De stub vuurt een `persistent_notification` af zodra een bestaande automatisering hem nog gebruikt. Migreer door een nieuwe automatisering vanuit `button_dim.yaml` te maken en de oude uit te zetten.

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

[Unreleased]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.7.1...HEAD
[1.7.1]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.3.0...v1.4.1
[1.3.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/markminnoye/ha-ipbuilding-gateway/releases/tag/v1.0.0
[0.4.3]: https://github.com/markminnoye/ha-ipbuilding-gateway/releases/tag/v0.4.3
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
