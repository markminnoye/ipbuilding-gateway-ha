# Dashboard — Gateway diagnostics

De companion levert een Tier-1 **IPBuilding Gateway**-device met twee entities
voor operator-diagnostiek en -acties:

| Entity | Categorie | Doel |
|---|---|---|
| `sensor.ipbuilding_gateway_gateway_status` | `diagnostic` | Aggregate gateway-status: `ok` / `degraded` / `unhealthy` + attributen (`issues`, `subsystems`, `version`, `uptime_seconds`, `updated_at`) |
| `button.ipbuilding_gateway_run_discovery_sweep` | `config` | Forceert een ARP-sweep + HTTP-identify op de gateway (`POST /api/v1/discover`) |

Beide staan op de Tier-1 hub in **Instellingen → Apparaten → IPBuilding Gateway**.
Ze zijn bewust als `diagnostic` / `config` gecategoriseerd zodat ze niet tussen
de lichten/dimmers op een Overview-dashboard verschijnen.

## Entities ontdekken

Filter in **Developer Tools → States** op `ipbuilding`. Je ziet dan naast de
kanaal-entities (relays, dimmers, fysieke knoppen) ook de gateway-entities.

## Aanbevolen Lovelace-view

Maak een aparte view "Gateway" in een dashboard, met onderstaande cards.

### 1. Status-glance (native)

Toont aggregate status in één tegel.

```yaml
type: glance
title: Gateway
entities:
  - entity: sensor.ipbuilding_gateway_gateway_status
    name: Status
    icon: mdi:server-network
columns: 1
```

### 2. Discover-knop (button-card)

Vereist [button-card](https://github.com/custom-cards/button-card) (HACS → Frontend).

```yaml
type: custom:button-card
entity: button.ipbuilding_gateway_run_discovery_sweep
name: Run discovery sweep
icon: mdi:radar
show_state: false
tap_action:
  action: call-service
  service: button.press
  target:
    entity_id: button.ipbuilding_gateway_run_discovery_sweep
styles:
  card:
    - height: 60px
```

### 3. Issues + subsystems (markdown)

Toont leesbare issues uit de sensor-attributen. Markdown-templates worden
door core Lovelace geëvalueerd.

```yaml
type: markdown
content: |
  ## Issues
  {% set issues = state_attr('sensor.ipbuilding_gateway_gateway_status', 'issues') %}
  {% set subs = state_attr('sensor.ipbuilding_gateway_gateway_status', 'subsystems') %}
  {% set version = state_attr('sensor.ipbuilding_gateway_gateway_status', 'version') %}
  **Subsystems:** {{ subs }}
  **Version:** {{ version }}
  {% if issues and issues | length > 0 %}
  {% for issue in issues %}
  - **[{{ issue.level }}]** {{ issue.message }} (`{{ issue.code }}`)
  {% endfor %}
  {% else %}
  No open issues.
  {% endif %}
card_mod:
  style: |
    ha-card { font-size: 0.95em; }
```

### 4. Volledige view (alles in één)

Combineer bovenstaande cards in een `vertical-stack`:

```yaml
type: vertical-stack
title: IPBuilding Gateway
cards:
  - type: glance
    title: Status
    entities:
      - entity: sensor.ipbuilding_gateway_gateway_status
        name: Status
        icon: mdi:server-network
    columns: 1
  - type: custom:button-card
    entity: button.ipbuilding_gateway_run_discovery_sweep
    name: Run discovery sweep
    icon: mdi:radar
    show_state: false
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.ipbuilding_gateway_run_discovery_sweep
    styles:
      card:
        - height: 60px
  - type: markdown
    content: |
      ## Issues
      {% set issues = state_attr('sensor.ipbuilding_gateway_gateway_status', 'issues') %}
      {% set subs = state_attr('sensor.ipbuilding_gateway_gateway_status', 'subsystems') %}
      {% set version = state_attr('sensor.ipbuilding_gateway_gateway_status', 'version') %}
      **Subsystems:** {{ subs }}
      **Version:** {{ version }}
      {% if issues and issues | length > 0 %}
      {% for issue in issues %}
      - **[{{ issue.level }}]** {{ issue.message }} (`{{ issue.code }}`)
      {% endfor %}
      {% else %}
      No open issues.
      {% endif %}
    card_mod:
      style: |
        ha-card { font-size: 0.95em; }
```

## Hoe onderscheid je gateway-entities van kanaal-entities?

| Filter | Wat je ziet |
|---|---|
| Categorie `diagnostic` | Gateway status-sensor (en toekomstige diagnose-sensors) |
| Categorie `config` | Discover-knop (en toekomstige config-acties) |
| Categorie `geen` | Licht/dimmer/switch/knop per kanaal + power-sensor |

In een entities-card kun je rechtsboven filteren op categorie.

## HACS-afhankelijkheid

Alleen `button-card` (HACS → Frontend → search "Button card" → install). De
glance- en markdown-cards zijn core Lovelace.

Na HACS-install: **hard refresh** de browser (Cmd-Shift-R / Ctrl-F5) zodat de
custom-card-types geladen worden.

## Troubleshooting

### Status = `unknown`

- Companion heeft (nog) geen REST-response ontvangen van `/api/v1/status`
- Check of de gateway bereikbaar is: `curl http://<host>:8080/api/v1/status`
- In de gateway-log moet `IPBuilding Gateway v...` zichtbaar zijn

### Discover-knop doet niets

- Check of `button.ipbuilding_gateway_run_discovery_sweep` bestaat in States
- Klik op de knop en kijk in de gateway-log — verwacht: `Discover sweep completed: {...}`
- HTTP-timeout is 120 s; een echte sweep kan even duren
- Controleer `services.yaml` niet aangepast is — companion gebruikt `button.press` met de entity als target

### Issues-card toont leeg ondanks `degraded`

- `state_attr('sensor.ipbuilding_gateway_gateway_status', 'issues')` is dan `[]`
- Mogelijk zijn issues tussentijds opgelost; herhaal de actie (bv. forceer een
  metadata refresh via `POST /api/v1/modules/refresh`) om ze opnieuw te triggeren
- Issues in de gateway-log zijn leidend als de attributen leeg lijken

### Knop verschijnt niet in HACS-installatie

- Bevestig dat `manifest.json` `version: 0.1.6` of hoger toont
- Herstart HA, en herlaad de integratie (Instellingen → Apparaten & diensten → IPBuilding Gateway → ⋯ → Herladen)
- Wis eventueel `custom_components/ipbuilding_gateway_ha/__pycache__/`
