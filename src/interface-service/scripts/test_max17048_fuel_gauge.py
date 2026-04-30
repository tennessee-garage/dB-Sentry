#!/usr/bin/env python3
"""Simple demo script for reading MAX17048 fuel gauge metrics."""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interface.max17048_fuel_gauge import MAX17048FuelGauge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read metrics from MAX17048 over I2C")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number (default: 1)")
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        default=0x36,
        help="I2C address (default: 0x36)",
    )
    parser.add_argument(
        "--alert-pin",
        type=int,
        default=4,
        help="GPIO pin for ~ALERT (default: 4)",
    )
    parser.add_argument(
        "--no-alert-gpio",
        action="store_true",
        help="Disable reading ALERT state from GPIO",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="Number of samples to read (0 = run until Ctrl+C)",
    )
    return parser.parse_args()


def format_alert(alert_value: float | None) -> str:
    if alert_value is None:
        return "n/a"
    return "asserted" if bool(alert_value) else "clear"


def main() -> int:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    gauge = MAX17048FuelGauge(
        bus_number=args.bus,
        address=args.address,
        alert_pin=args.alert_pin,
        use_alert_gpio=not args.no_alert_gpio,
    )

    if not gauge.is_ready:
        logging.error("Fuel gauge is not ready. Check I2C wiring, permissions, and installed packages.")
        return 1

    print("MAX17048 fuel gauge demo")
    print(f"  I2C bus: {args.bus}")
    print(f"  I2C address: 0x{args.address:02X}")
    print(f"  ALERT GPIO: {'disabled' if args.no_alert_gpio else args.alert_pin}")
    print()

    sample_count = 0

    try:
        while True:
            metrics = gauge.read_metrics()
            voltage_v = metrics["voltage_v"]
            soc_percent = metrics["soc_percent"]
            crate = metrics["crate_percent_per_hour"]
            status_raw = int(metrics["status_raw"] or 0)
            version_raw = int(metrics["version_raw"] or 0)
            alert_text = format_alert(metrics["alert_pin_asserted"])
            time_left_text = gauge.read_estimated_time_remaining_text()

            direction = "charging" if (crate or 0.0) >= 0 else "discharging"
            print(
                f"V={voltage_v:.4f}V | "
                f"SOC={soc_percent:6.2f}% | "
                f"CRate={crate:8.3f}%/hr ({direction}) | "
                f"Time left={time_left_text} | "
                f"STATUS=0x{status_raw:04X} | "
                f"VERSION=0x{version_raw:04X} | "
                f"ALERT={alert_text}"
            )

            sample_count += 1
            if args.samples > 0 and sample_count >= args.samples:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        gauge.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
