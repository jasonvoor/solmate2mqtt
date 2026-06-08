# solmate2mqtt

A tiny, self-contained bridge that brings your **EET SolMate** (the *sun2plug*
plug-in battery) into **Home Assistant** over MQTT — with **automatic device &
sensor discovery**, so you don't write a single line of YAML.

It logs in to the EET SolMate **cloud** API with your serial number and portal
password, polls the live values every 30 seconds, and republishes them as MQTT
sensors. Home Assistant picks them up via MQTT auto-discovery and creates an
`EET SolMate` device with PV power, injection power, battery flow, battery
state-of-charge, and temperature.

> Not affiliated with or endorsed by EET. "SolMate" and "sun2plug" are
> trademarks of their respective owner. This project just talks to the same
> public API the official app uses.

---

## What you get in Home Assistant

A single device, **EET SolMate**, with these entities (created automatically):

| Entity | Unit | Device class |
|---|---|---|
| `sensor.solmate_pv_power` | W | power |
| `sensor.solmate_inject_power` | W | power |
| `sensor.solmate_battery_flow` | W | power |
| `sensor.solmate_battery_state` | % | battery |
| `sensor.solmate_temperature` | °C | temperature |

All are `state_class: measurement`, so they work in the Energy dashboard,
history, and statistics out of the box. An availability topic marks them
*unavailable* when the bridge can't reach your SolMate.

---

## How it works

```
            wss://sol.eet.energy:9124                    MQTT
 EET SolMate ───────────────────────▶ solmate2mqtt ───────────▶  MQTT broker ───▶ Home Assistant
   (cloud)        serial + password      (this bridge)     publish      (Mosquitto)   (MQTT discovery)
```

The bridge uses the community [`solmate-sdk`](https://github.com/eet-energy/solmate-sdk)
to authenticate against EET's cloud endpoint (`wss://sol.eet.energy:9124`). That
endpoint **auto-redirects** to whatever server your SolMate is assigned to, so
it works from anywhere — you do **not** need to be on the same LAN as the
battery, and you don't need to know its local IP.

It's deliberately small: one Python file (`bridge/bridge.py`), ~200 lines, two
dependencies.

---

## Prerequisites

- An **EET SolMate** with cloud access, and the **serial number** + **web-portal
  password** you use for the SolMate app / [my.eet.energy](https://my.eet.energy).
- **Docker** + **Docker Compose**.
- An **MQTT broker**. Most Home Assistant users already have one (the
  *Mosquitto broker* add-on). If you don't, this repo can start one for you —
  see [Option B](#option-b-no-broker-yet-bundled-mosquitto).
- **Home Assistant** with the **MQTT integration** configured and pointed at the
  same broker. MQTT discovery is enabled by default (prefix `homeassistant`).

---

## Setup

```bash
git clone https://github.com/jasonvoor/solmate2mqtt.git
cd solmate2mqtt
cp .env.example .env
$EDITOR .env          # fill in SOLMATE_SERIAL, SOLMATE_PASSWORD, MQTT_HOST, ...
docker compose up -d --build
docker compose logs -f
```

A healthy startup looks like:

```
[solmate] INFO EET SolMate -> MQTT bridge starting (serial=...)
[solmate] INFO MQTT connected to your-broker-host:1883
[solmate] INFO HA auto-discovery published for 5 sensors.
[solmate] INFO SolMate authenticated.
[solmate] INFO Published 5 sensor values: {'pv_power': 142.0, 'battery_state': 63.0, ...}
```

Within a few seconds the **EET SolMate** device appears under
**Settings → Devices & Services → MQTT** in Home Assistant.

### Option A: you already have a broker (recommended)

Point `MQTT_HOST` (and `MQTT_USERNAME` / `MQTT_PASSWORD` if your broker needs
auth) at your existing broker in `.env`. If that's the Home Assistant Mosquitto
add-on, `MQTT_HOST` is the IP of your Home Assistant host. Done.

### Option B: no broker yet (bundled Mosquitto)

This repo ships an **optional** Mosquitto service, commented out by default.

1. Create its config:
   ```bash
   cp mosquitto/mosquitto.conf.example mosquitto/mosquitto.conf
   ```
2. In `docker-compose.yml`, uncomment the `mosquitto:` service, the `volumes:`
   block at the bottom, and the `depends_on:` lines on the bridge.
3. In `.env`, set `MQTT_HOST=mosquitto`.
4. Point Home Assistant's MQTT integration at this broker (host = the Docker
   host's IP, port `1883`).

The example Mosquitto config allows **anonymous** connections for a fast start —
add a `password_file` and/or TLS before exposing it to anything but your LAN.

---

## Configuration reference

All configuration is via environment variables (`.env`). Defaults in **bold**.

| Variable | Required | Default | Description |
|---|---|---|---|
| `SOLMATE_SERIAL` | ✅ | — | SolMate serial number. |
| `SOLMATE_PASSWORD` | ✅ | — | SolMate web-portal / app password. |
| `MQTT_HOST` | ✅ | — | MQTT broker host/IP (`mosquitto` if bundled). |
| `MQTT_PORT` | | **1883** | MQTT broker port. |
| `MQTT_USERNAME` | | *(empty)* | MQTT username; blank = anonymous. |
| `MQTT_PASSWORD` | | *(empty)* | MQTT password. |
| `MQTT_PREFIX` | | **eet** | Root of the state topics. |
| `MQTT_DISCOVERY_PREFIX` | | **homeassistant** | Must match HA's discovery prefix. |
| `DEVICE_ID` | | **solmate** | Device slug; HA entity prefix `sensor.<DEVICE_ID>_…`. |
| `TIMER_LIVE` | | **30** | Seconds between live-value polls. |
| `TIMER_OFFLINE` | | **60** | Seconds before retry after a drop. |
| `LOG_LEVEL` | | **INFO** | `DEBUG` to log raw SDK payloads. |
| `TZ` | | **UTC** | Timezone for log timestamps. |

---

## MQTT topic map

With defaults (`MQTT_PREFIX=eet`, `DEVICE_ID=solmate`):

| Topic | Retained | Payload |
|---|---|---|
| `eet/sensor/solmate/availability` | ✅ | `online` / `offline` |
| `eet/sensor/solmate/pv_power/state` | | e.g. `142.0` |
| `eet/sensor/solmate/inject_power/state` | | e.g. `0.0` |
| `eet/sensor/solmate/battery_flow/state` | | e.g. `-85.0` |
| `eet/sensor/solmate/battery_state/state` | | e.g. `63.0` |
| `eet/sensor/solmate/temperature/state` | | e.g. `24.5` |
| `homeassistant/sensor/solmate_<field>/config` | ✅ | HA discovery JSON (one per sensor) |

The discovery configs are **retained**, so Home Assistant re-discovers the
device after a restart without the bridge republishing.

### Don't use MQTT discovery?

If you prefer manual YAML (discovery disabled), add sensors like this — one per
field in the topic map:

```yaml
# configuration.yaml
mqtt:
  sensor:
    - name: "SolMate PV Power"
      state_topic: "eet/sensor/solmate/pv_power/state"
      availability_topic: "eet/sensor/solmate/availability"
      unit_of_measurement: "W"
      device_class: power
      state_class: measurement
    # ...repeat for inject_power, battery_flow, battery_state, temperature
```

---

## Troubleshooting

**Nothing shows up in Home Assistant.**
Confirm the bridge and Home Assistant talk to the *same* broker, and that
`MQTT_DISCOVERY_PREFIX` matches HA's discovery prefix (default `homeassistant`).
Subscribe and watch:
`mosquitto_sub -h <broker> -t 'homeassistant/#' -t 'eet/#' -v`.

**`SolMate connection failed` in the logs.**
Check `SOLMATE_SERIAL` and `SOLMATE_PASSWORD` — the same credentials must log in
at [my.eet.energy](https://my.eet.energy). Make sure your SolMate is online in
the app.

**`Cannot connect to MQTT broker`.**
Wrong `MQTT_HOST`/`MQTT_PORT`, broker not running, or it requires auth
(`MQTT_USERNAME`/`MQTT_PASSWORD`) and you left them blank — or the reverse.

**`get_live_values returned no recognised sensor keys`.**
The SDK returned a payload without the expected keys (firmware/SDK change).
Run with `LOG_LEVEL=DEBUG` to see the raw payload, then open an issue with it.

**Entities show *unavailable*.**
The bridge published `offline` on the availability topic — it can't reach your
SolMate. Check the logs; it retries every `TIMER_OFFLINE` seconds.

---

## Credits

- Built on the community [`solmate-sdk`](https://github.com/eet-energy/solmate-sdk).
- Talks to [Home Assistant](https://www.home-assistant.io/) via
  [MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).

## License

[MIT](LICENSE).
