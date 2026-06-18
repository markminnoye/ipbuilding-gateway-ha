# IPBuilding Gateway HA

HA custom component (integration) voor de **[ipbuilding-gateway](https://github.com/markminnoye/IPBuilding-Gateway)** hub.

De gateway praat rechtstreeks via **UDP/1001** met IPBuilding-modules (IP0200PoE relays, IP0300PoE dimmers, IP1100PoE inputs) en biedt een **WebSocket `/ws`** + **REST `/api/v1/`** northbound API op poort `8080`. Deze component is de client-kant die HA entities aanmaakt op basis van die API.

## Features

- **Auto-detectie via Supervisor** — wanneer de `ipbuilding_gateway` HA add-on actief is, verschijnt de integratie automatisch onder **Instellingen → Apparaten & Diensten → Ontdekt**.
- **Zeroconf / mDNS detectie** — een standalone gateway (Docker / Pi) op het LAN verschijnt op dezelfde manier. Beide kanalen worden automatisch gededupliceerd.
- **Handmatige config** — voor remote of onbereikbare setups vul je host + poort zelf in.
- **Entities** — light (relay/dimmer), switch (relay/dimmer met semantic_type), button (IP1100PoE fysieke knop → HA events), sensor (per-kanaal current_watt).
- **Real-time** — WebSocket-streaming van device-state en input-events; geen polling.
- **Local-only** — `iot_class: local_push`, geen cloud, geen internet nodig.

## Vereisten

- Home Assistant **≥ 2023.8** (voor `EventEntity`)
- Een draaiende [ipbuilding-gateway](https://github.com/markminnoye/IPBuilding-Gateway) (HA add-on óf standalone Docker) bereikbaar op `host:8080`
- Bereikbare IPBuilding-modules op het `10.10.1.0/24` veldbus-segment (relay, dimmer, input)

## Installatie (HACS)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=markminnoye&repository=ha-ipbuilding-gateway&category=integration)

Custom repository (niet in de standaard HACS-winkel). De link hierboven voegt
`markminnoye/ha-ipbuilding-gateway` toe; daarna **IPBuilding Gateway HA**
downloaden en Home Assistant herstarten.

Handmatig als de link faalt: **HACS → Integraties → ⋮ → Aangepaste
repositories** → `https://github.com/markminnoye/ha-ipbuilding-gateway`
(type **Integratie**).
4. De integratie verschijnt nu vanzelf onder **Instellingen → Apparaten & Diensten → Ontdekt** zodra de gateway (add-on of standalone) draait. Klik **Toevoegen** om te koppelen.
   - Bij actieve add-on: Supervisor stuurt het discovery signaal — geen multicast nodig.
   - Bij standalone gateway: mDNS broadcast; werkt alleen op een plat LAN met host networking.
   - Werkt geen van beide? Kies dan handmatig **Integratie toevoegen → IPBuilding Gateway HA** en vul host + poort zelf in.

## Architectuur

```
IPBuilding veldbus (UDP/1001)
  └── ipbuilding-gateway (Python, deze repo: companion van)
        ├── WebSocket /ws  (product northbound)
        └── REST /api/v1/  (product northbound)
              │
              ▼
        ha-ipbuilding-gateway (deze component)
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

- Event type: `ha_ipbuilding_gateway.button_pressed`
- Data: `{"hardware_id": "2DE341851900001F", "action": "press"}`

Gebruik in automations:

```yaml
trigger:
  - platform: event
    event_type: ha_ipbuilding_gateway.button_pressed
    event_data:
      hardware_id: "2DE341851900001F"
```

## Documentatie

- Companion README: zie [README.md](README.md)
- Gateway docs (northbound API): https://github.com/markminnoye/IPBuilding-Gateway/tree/main/docs/api
- Volledige RE-kennis: https://github.com/markminnoye/IPBuilding-Gateway/blob/main/resources_and_docs/IPBUILDING_KNOWLEDGE.md

## Licentie

MIT
