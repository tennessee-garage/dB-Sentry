#!/usr/bin/env python3
"""Poll the limit service once per second and print sensor details to stdout."""

import sys
import time
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.limit_service_api import LimitServiceAPI


def main():
    api = LimitServiceAPI()

    print(f"Connecting to limit service at {api.base_url} ...")
    if not api.is_available():
        print("ERROR: limit service is not available. Is it running?", file=sys.stderr)
        sys.exit(1)

    print("Connected. Polling every 1s. Press Ctrl+C to stop.\n")

    try:
        while True:
            ts = time.strftime("%H:%M:%S")
            sensors = api.get_sensors()
            limits = api.get_limits()

            print(f"[{ts}] sensors: {sensors or '(none)'}")

            for sensor in sorted(sensors):
                details = api.get_sensor_details(sensor)
                limit = limits.get(sensor, "n/a")
                if details:
                    reading = details.get("current_reading", "n/a")
                    average = details.get("average", "n/a")
                    mps = details.get("measurements_per_second", "n/a")
                    print(
                        f"  {sensor:<20}"
                        f"  reading={reading}"
                        f"  avg={average}"
                        f"  mps={mps}"
                        f"  limit={limit}"
                    )
                else:
                    print(f"  {sensor:<20}  (no details)  limit={limit}")

            print()
            time.sleep(1)

    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
