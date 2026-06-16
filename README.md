# IPBuilding Gateway HA — Home Assistant Custom Component

HA custom component voor de **ipbuilding-gateway** (Fase 3 product-API op `8080`).

## Installatie (HACS)

1. Voeg toe als **custom repository** in HACS:
   `https://github.com/markminnoye/IPBuilding-Gateway`
2. Zoek naar **IPBuilding Gateway HA** en installeer
3. Herstart Home Assistant
4. De integratie verschijnt nu vanzelf onder **Instellingen → Apparaten & diensten → Ontdekt** zodra de gateway (add-on of standalone) draait. Klik **Toevoegen** om te koppelen.
   - Werkt dat niet (mDNS geblokkeerd, andere VLAN, …)? Kies dan handmatig **Integratie toevoegen → IPBuilding Gateway HA** en vul host + poort (`8080`) zelf in.

## Architectuur

```
IPBuilding veldbus (UDP/1001)
  └── ipbuilding-gateway (Python)
        ├── REST :30200  (IPBox shim — transitie, Fase 1-2; disabled by default)
        ├── WebSocket /ws  (product northbound, Fase 3)  ←── ipbuilding-gateway-ha
        └── REST /api/v1/  (product northbound, Fase 3)
  └── ipbuilding-gateway-ha (HA custom component)
        ├── WebSocket-client (coordinator)
        └── HA entities:
              ├── light      (relay ONOFF + dimmer BRIGHTNESS)
              ├── switch     (relay/dimmer met semantic_type switch/plug/fan)
              ├── button     (IP1100PoE fysieke knop → HA events)
              └── sensor     (current_watt per kanaal)
```

## Auto-detectie

De companion maakt de gateway op twee manieren vindbaar in **Instellingen → Apparaten & diensten → Ontdekt** (zelfde patroon als Shelly, ESPHome en Music Assistant):

| Deployment | Kanaal | Wat er gebeurt |
|------------|--------|----------------|
| HA add-on op HA OS / Supervised | **Supervisor discovery** | De add-on `POST /supervisor/discovery` bij opstart → Supervisor geeft het door aan Home Assistant. Geen multicast nodig. |
| Standalone Docker / Pi op het LAN | **Zeroconf / mDNS** | Gateway broadcast `_ipbgw._tcp.local.`. Werkt alleen op een plat LAN (geen VLAN-reflector) en met host networking. |
| Beide | Dedup | Een add-on stuurt *beide* kanalen; de Zeroconf-route bevat `homeassistant_addon=true` zodat de companion dubbele entries voorkomt. |

```
HA add-on draait                    Companion geïnstalleerd
        │                                       │
        ├─ POST /supervisor/discovery           │
        │      service=ipbuilding_gateway_ha     │
        ▼                                       ▼
Supervisor ──push──►  Home Assistant  ◄──mDNS──── gateway
                          │
                          ▼
                 Ontdekt-lijst: "IPBuilding Gateway HA"
                          │
                          ▼  klik "Toevoegen"
                Bevestiging → config entry
```

Wanneer geen ontdekking mogelijk is (mDNS geblokkeerd, remote, …) blijft de handmatige setup beschikbaar via **Integratie toevoegen → IPBuilding Gateway HA**.

## Entity ID formaat

De companion gebruikt het gateway entity-ID:
```
{module_ip}:{device_type}:{channel}
Bijv. "10.10.1.30:relay:0"
```

## Knoppen (button events)

Knop events van de IP1100PoE verschijnen als HA events:
- Event type: `ipbuilding_gateway_ha.button_pressed`
- Data: `{"hardware_id": "2DE341851900001F", "action": "press"}`

Gebruik in automations:
```yaml
trigger:
  platform: event
  event_type: ipbuilding_gateway_ha.button_pressed
  event_data:
    hardware_id: "2DE341851900001F"
```

## Commandos sturen

Vanuit een HA automation of service call:
*(Command interface via WebSocket `command` berichten — automations/scenes spreken direct via de coordinator.)*

## Ontwikkeling

Bestanden in `custom_components/ipbuilding_gateway_ha/`:
- `coordinator.py` — WebSocket-client + state management
- `light.py` — relay/dimmer light entities
- `switch.py` — switch entities
- `button.py` — button/event entities
- `sensor.py` — power sensor entities
- `config_flow.py` — gebruiker invoer + validatie
- `manifest.json` — HA integratie manifest

## Dashboard

Voor de Tier-1 hub-entities (`sensor.ipbuilding_gateway_gateway_status` +
`button.ipbuilding_gateway_run_discovery_sweep`) is een apart Lovelace-fragment
beschikbaar — inclusief Issues-card, button-card snippet en troubleshooting:

- [custom_components/ipbuilding_gateway_ha/dashboard.md](custom_components/ipbuilding_gateway_ha/dashboard.md)

## Vereisten

- Home Assistant >= 2023.8 (voor EventEntity)
- `aiohttp` Python package
- Gateway moet WebSocket `/ws` en REST `/api/v1/devices` exposed hebben (poort 8080)
- Voor dashboard-card `button-card` is de HACS Frontend custom card vereist (overige cards zijn core Lovelace)