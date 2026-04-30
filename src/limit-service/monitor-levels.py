#!/usr/bin/env python3
import argparse
import json
import signal
import sys
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt

from config import cfg
from mqtt.dba_message import DBAMessage
from mqtt.factory import create_message


BAND_ORDER = ("treble", "mid", "bass")
BAND_COLORS = {
    "treble": "\033[33m",
    "mid": "\033[36m",
    "bass": "\033[35m",
}
ANSI_RESET = "\033[0m"


def parse_level(payload: bytes) -> Optional[float]:
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        for key in ("value", "level", "dba"):
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    return None

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug MQTT level stream by printing sensor values as they are received."
    )
    parser.add_argument("--broker", default=cfg.mqtt_broker, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=cfg.mqtt_port, help="MQTT broker port")
    parser.add_argument("--topic", default=cfg.mqtt_topic, help="MQTT topic filter to subscribe to")
    parser.add_argument("--qos", type=int, default=0, choices=(0, 1, 2), help="MQTT QoS")
    parser.add_argument(
        "--show-unparsed",
        action="store_true",
        help="Print payloads that could not be parsed as a numeric level",
    )
    parser.add_argument(
        "--equalizer",
        action="store_true",
        help="Show a per-sensor treble/mid/bass equalizer using colored # bars",
    )
    parser.add_argument(
        "--bar-width",
        type=int,
        default=30,
        help="Character width for each equalizer bar",
    )
    return parser.parse_args()


def clamp_dba(value: float) -> float:
    return max(0.0, min(100.0, value))


def render_equalizer_line(band: str, level: Optional[float], bar_width: int) -> str:
    if level is None:
        return f"{band:>6}: {'-' * bar_width} --"

    clamped = clamp_dba(level)
    filled = int(round((clamped / 100.0) * bar_width))
    color = BAND_COLORS.get(band, "")
    filled_bar = f"{color}{'#' * filled}{ANSI_RESET}" if filled > 0 else ""
    empty_bar = "-" * (bar_width - filled)
    return f"{band:>6}: {filled_bar}{empty_bar} {clamped:6.2f}"


def render_equalizer_dashboard(
    sensor_bands: dict[str, dict[str, float]],
    bar_width: int,
    topic: str,
    notice: str = "",
) -> None:
    lines: list[str] = [
        f"Equalizer view | topic='{topic}' | dBA range: 0-100",
        "Press Ctrl+C to stop.",
    ]
    if notice:
        lines.append(f"Notice: {notice}")

    if not sensor_bands:
        lines.append("Waiting for sensor data...")
    else:
        for sensor in sorted(sensor_bands.keys()):
            lines.append("")
            lines.append(f"sensor={sensor}")
            sensor_data = sensor_bands[sensor]
            for band in BAND_ORDER:
                lines.append("  " + render_equalizer_line(band, sensor_data.get(band), bar_width))

    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def main() -> int:
    args = parse_args()
    if args.bar_width < 1:
        print("--bar-width must be at least 1")
        return 2

    client = mqtt.Client()
    sensor_bands: dict[str, dict[str, float]] = {}
    last_notice = ""

    def shutdown(*_):
        print("\nStopping MQTT debug listener...")
        try:
            client.disconnect()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    def on_connect(mqtt_client, _userdata, _flags, rc):
        if rc != 0:
            print(f"Failed to connect to MQTT broker (rc={rc})")
            return

        mqtt_client.subscribe(args.topic, qos=args.qos)
        if args.equalizer:
            render_equalizer_dashboard(sensor_bands, args.bar_width, args.topic)
            return

        print(f"Connected to {args.broker}:{args.port} | topic='{args.topic}' | qos={args.qos}")
        print("Waiting for messages... Press Ctrl+C to stop.")

    def on_message(_mqtt_client, _userdata, msg):
        nonlocal last_notice
        level = parse_level(msg.payload)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if level is None:
            if args.show_unparsed:
                raw = msg.payload.decode("utf-8", errors="replace")
                if args.equalizer:
                    last_notice = f"Unparsed payload on {msg.topic}: {raw}"
                    render_equalizer_dashboard(sensor_bands, args.bar_width, args.topic, last_notice)
                    return
                print(f"[{ts}] unparsed topic={msg.topic} payload={raw}")
            return

        parsed = create_message(msg.topic, level)
        if isinstance(parsed, DBAMessage) and parsed.sensor is not None:
            sensor = parsed.sensor
            band = parsed.band or "-"
        else:
            parts = msg.topic.split("/")
            sensor = parts[1] if len(parts) > 1 else parts[0]
            band = parts[2] if len(parts) > 2 else "-"

        if not args.equalizer:
            print(f"[{ts}] sensor={sensor} band={band} level={level:.2f}")
            return

        band_key = (band or "").lower()
        if band_key in BAND_ORDER:
            sensor_bands.setdefault(sensor, {})[band_key] = level
        last_notice = ""
        render_equalizer_dashboard(sensor_bands, args.bar_width, args.topic, last_notice)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, args.port, keepalive=60)
    except Exception as exc:
        print(f"Could not connect to MQTT broker {args.broker}:{args.port}: {exc}")
        return 1

    client.loop_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
