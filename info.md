# IPBuilding Gateway HA

HA custom component (integration) voor de **[ipbuilding-gateway](https://github.com/markminnoye/IPBuilding-Gateway)** hub.

De gateway praat rechtstreeks via **UDP/1001** met IPBuilding-modules (IP0200PoE relays, IP0300PoE dimmers, IP1100PoE inputs) en biedt een **WebSocket `/ws`** + **REST `/api/v1/`** northbound API op poort `8080`. Deze component is de client-kant die HA entities aanmaakt op basis van die API.

## Features

- **Auto-discovery via Supervisor** — wanneer de `ipbuilding_gateway` HA add-on actief is, wordt host/poort (`127.0.0.1:8080`) automatisch ingevuld. Geen handmatige config nodig.
- **Handmatige config** — voor standalone Docker of remote setups vul je host + poort zelf in.
- **Entities** — light (relay/dimmer), switch (relay/dimmer met semantic_type), button (IP1100PoE fysieke knop → HA events), sensor (per-kanaal current_watt).
- **Real-time** — WebSocket-streaming van device-state en input-events; geen polling.
- **Local-only** — `iot_class: local_polling`, geen cloud, geen internet nodig.

## Vereisten

- Home Assistant **≥ 2023.8** (voor `EventEntity`)
- Een draaiende [ipbuilding-gateway](https://github.com/markminnoye/IPBuilding-Gateway) (HA add-on óf standalone Docker) bereikbaar op `host:8080`
- Bereikbare IPBuilding-modules op het `10.10.1.0/24` veldbus-segment (relay, dimmer, input)

## Installatie (HACS)

1. Voeg deze repo toe in HACS als **Custom Repository**:
   - URL: `https://github.com/markminnoye/ipbuilding-gateway-ha`
   - Type: **Integration**
2. Installeer **IPBuilding Gateway HA**
3. Herstart Home Assistant
4. **Instellingen → Apparaten & Diensten → Integratie toevoegen** → "IPBuilding Gateway HA"
   - Bij actieve add-on: velden worden automatisch ingevuld
   - Anders: `host:poort` van de gateway handmatig invullen

## Architectuur

```
IPBuilding veldbus (UDP/1001)
  └── ipbuilding-gateway (Python, deze repo: companion van)
        ├── WebSocket /ws  (product northbound)
        └── REST /api/v1/  (product northbound)
              │
              ▼
        ipbuilding-gateway-ha (deze component)
              ├── WebSocket-client (coordinator)
              └── HA entities:
                    ├── light      (relay ONOFF + dimmer BRIGHTNESS)
                    ├── switch     (relay/dimmer met semantic_type switch/plug/fan)
                    ├── button     (IP1100PoE fysieke knop → HA events)
                    └── sensor     (current_watt per kanaal)
```

## Entity ID formaat

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
  - platform: event
    event_type: ipbuilding_gateway_ha.button_pressed
    event_data:
      hardware_id: "2DE341851900001F"
```

## Documentatie

- Companion README: zie [README.md](README.md)
- Gateway docs (northbound API): https://github.com/markminnoye/IPBuilding-Gateway/tree/main/docs/api
- Volledige RE-kennis: https://github.com/markminnoye/IPBuilding-Gateway/blob/main/resources_and_docs/IPBUILDING_KNOWLEDGE.md

## Licentie

MIT
