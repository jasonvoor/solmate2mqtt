#!/usr/bin/env python3
"""
EET SolMate (sun2plug) -> MQTT bridge for Home Assistant.

Connects to the EET SolMate cloud WebSocket API with your SolMate serial
number + web-portal password, polls live values, and republishes them to
MQTT. It also publishes Home Assistant MQTT auto-discovery payloads, so the
battery's sensors appear in Home Assistant automatically -- no YAML required.

Uses eet-energy/solmate-sdk 0.1.x (synchronous API).

SDK facts (0.1.11):
  SolMateAPIClient(serialnum, uri='wss://sol.eet.energy:9124')
  client.quickstart(password, device_id, store_auth_token_in_file)
  client.get_live_values()  -> dict with pv_power, battery_state, inject_power, ...

The cloud URI auto-redirects to the device's assigned server, so no local
connection or LAN subdomain is needed -- the bridge works from anywhere your
SolMate web portal works.

All configuration comes from environment variables -- see .env.example.
"""

import json
import logging
import os
import sys
import time

import paho.mqtt.client as mqtt
from solmate_sdk import SolMateAPIClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [solmate] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment (see .env.example)
# ---------------------------------------------------------------------------
# SolMate cloud credentials (required)
SOLMATE_SERIAL   = os.environ["SOLMATE_SERIAL"]
SOLMATE_PASSWORD = os.environ["SOLMATE_PASSWORD"]

# MQTT broker (MQTT_HOST required)
MQTT_HOST     = os.environ["MQTT_HOST"]
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

# Topic layout
MQTT_PREFIX     = os.environ.get("MQTT_PREFIX", "eet")            # state topic root
MQTT_DISCOVERY  = os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant")
DEVICE_ID       = os.environ.get("DEVICE_ID", "solmate")

# Polling
TIMER_LIVE    = int(os.environ.get("TIMER_LIVE", "30"))      # seconds between live polls
TIMER_OFFLINE = int(os.environ.get("TIMER_OFFLINE", "60"))   # seconds before reconnect retry

AVAIL_TOPIC = f"{MQTT_PREFIX}/sensor/{DEVICE_ID}/availability"

# ---------------------------------------------------------------------------
# Sensor definitions: (sdk_key, friendly_name, unit, device_class, icon)
# ---------------------------------------------------------------------------
SENSORS = [
    ("pv_power",      "PV Power",      "W",   "power",       "mdi:solar-power"),
    ("inject_power",  "Inject Power",  "W",   "power",       "mdi:transmission-tower-export"),
    ("battery_flow",  "Battery Flow",  "W",   "power",       "mdi:battery-charging"),
    ("battery_state", "Battery State", "%",   "battery",     "mdi:battery"),
    ("temperature",   "Temperature",   "°C",  "temperature", "mdi:thermometer"),
]

DEVICE_INFO = {
    "identifiers": [f"eet_solmate_{SOLMATE_SERIAL}"],
    "name": "EET SolMate",
    "manufacturer": "EET",
    "model": "SolMate (sun2plug)",
    "serial_number": SOLMATE_SERIAL,
}


# ---------------------------------------------------------------------------
# MQTT helpers
# ---------------------------------------------------------------------------
def state_topic(field: str) -> str:
    return f"{MQTT_PREFIX}/sensor/{DEVICE_ID}/{field}/state"


def publish_discovery(mqttc: mqtt.Client) -> None:
    for field, name, unit, device_class, icon in SENSORS:
        payload = {
            "name": name,
            # object_id controls the HA entity_id: sensor.solmate_<field>
            "object_id": f"{DEVICE_ID}_{field}",
            "unique_id": f"eet_solmate_{SOLMATE_SERIAL}_{field}",
            "state_topic": state_topic(field),
            "unit_of_measurement": unit,
            "device_class": device_class,
            "icon": icon,
            "state_class": "measurement",
            "device": DEVICE_INFO,
            "availability_topic": AVAIL_TOPIC,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        disc_topic = f"{MQTT_DISCOVERY}/sensor/{DEVICE_ID}_{field}/config"
        mqttc.publish(disc_topic, json.dumps(payload), retain=True)
    log.info("HA auto-discovery published for %d sensors.", len(SENSORS))


def publish_values(mqttc: mqtt.Client, values: dict) -> None:
    published = 0
    for field, *_ in SENSORS:
        value = values.get(field)
        if value is not None:
            mqttc.publish(state_topic(field), str(round(float(value), 2)))
            published += 1
    if published:
        log.info("Published %d sensor values: %s",
                 published,
                 {f: round(float(values[f]), 2) for f, *_ in SENSORS if values.get(f) is not None})
    else:
        log.warning("get_live_values returned no recognised sensor keys: %s", list(values.keys()))


def set_availability(mqttc: mqtt.Client, online: bool) -> None:
    mqttc.publish(AVAIL_TOPIC, "online" if online else "offline", retain=True)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def connect_mqtt() -> mqtt.Client:
    mqttc = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"solmate_bridge_{SOLMATE_SERIAL}",
        protocol=mqtt.MQTTv5,
    )
    if MQTT_USERNAME:
        mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Last-will: broker marks us offline if the bridge dies unexpectedly.
    mqttc.will_set(AVAIL_TOPIC, "offline", retain=True)

    def on_connect(client, userdata, flags, reason_code, props=None):
        if reason_code == 0:
            log.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
            publish_discovery(client)
            set_availability(client, False)  # offline until SolMate connects
        else:
            log.error("MQTT connect failed reason_code=%s", reason_code)

    mqttc.on_connect = on_connect
    mqttc.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqttc.loop_start()

    deadline = time.time() + 30
    while not mqttc.is_connected() and time.time() < deadline:
        time.sleep(0.5)
    if not mqttc.is_connected():
        log.error("Cannot connect to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        sys.exit(1)
    return mqttc


def solmate_loop(mqttc: mqtt.Client) -> None:
    while True:
        log.info("Connecting to SolMate cloud API (serial=%s)...", SOLMATE_SERIAL)
        try:
            # SolMateAPIClient connects to wss://sol.eet.energy:9124 by default.
            # quickstart() handles login + auth-token caching + URI redirect.
            # store_auth_token_in_file=False avoids writing to a file inside the container.
            client = SolMateAPIClient(SOLMATE_SERIAL)
            client.quickstart(
                password=SOLMATE_PASSWORD,
                device_id=f"ha-bridge-{SOLMATE_SERIAL}",
                store_auth_token_in_file=False,
            )
            log.info("SolMate authenticated.")
            set_availability(mqttc, True)

            while True:
                try:
                    values = client.get_live_values()
                    log.debug("live_values raw: %s", values)
                    if values:
                        publish_values(mqttc, values)
                    else:
                        log.warning("Empty live_values response.")
                except Exception as e:
                    log.warning("get_live_values error: %s — reconnecting", e)
                    break
                time.sleep(TIMER_LIVE)

        except Exception as e:
            log.error("SolMate connection failed: %s", e)

        set_availability(mqttc, False)
        log.info("Retrying in %ds...", TIMER_OFFLINE)
        time.sleep(TIMER_OFFLINE)


def main() -> None:
    log.info("EET SolMate -> MQTT bridge starting (serial=%s)", SOLMATE_SERIAL)
    mqttc = connect_mqtt()
    try:
        solmate_loop(mqttc)
    except KeyboardInterrupt:
        log.info("Shutdown.")
    finally:
        set_availability(mqttc, False)
        mqttc.loop_stop()
        mqttc.disconnect()


if __name__ == "__main__":
    main()
