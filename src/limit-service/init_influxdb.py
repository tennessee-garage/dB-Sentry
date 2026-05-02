#!/usr/bin/env python3
"""Initialize InfluxDB database and retention policies for db-sentry.

Idempotent: safe to run multiple times. Creates the database and retention
policies if they don't exist, and leaves existing data untouched.

Usage:
    python init_influxdb.py [--default-window-seconds N]
"""
import argparse
import logging
import sys

from influxdb import InfluxDBClient
from influxdb.resultset import ResultSet

from config import cfg

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Retention policy name used for persistent settings (limits, window_seconds)
SETTINGS_RP = "settings_rp"
# Default retention policy name (InfluxDB built-in)
DEFAULT_RP = "autogen"
# Sound data retention duration (90 days)
SOUND_DATA_DURATION = "90d"
# Default window_seconds to seed if none exists
DEFAULT_WINDOW_SECONDS = 30


def get_existing_rp_names(client: InfluxDBClient, db: str) -> set:
    result = client.get_list_retention_policies(database=db)
    return {rp["name"] for rp in result}


def get_existing_db_names(client: InfluxDBClient) -> set:
    return {db["name"] for db in client.get_list_database()}


def ensure_database(client: InfluxDBClient, db: str):
    if db in get_existing_db_names(client):
        logger.info(f"Database '{db}' already exists, skipping creation.")
    else:
        client.create_database(db)
        logger.info(f"Created database '{db}'.")


def ensure_retention_policy(
    client: InfluxDBClient,
    db: str,
    name: str,
    duration: str,
    default: bool = False,
):
    existing = get_existing_rp_names(client, db)
    if name in existing:
        logger.info(f"Retention policy '{name}' already exists on '{db}', skipping creation.")
    else:
        client.create_retention_policy(
            name=name,
            duration=duration,
            replication=1,
            database=db,
            default=default,
        )
        logger.info(f"Created retention policy '{name}' (duration={duration}) on '{db}'.")


def ensure_default_window_seconds(client: InfluxDBClient, db: str, window_seconds: int):
    """Write a seed value for window_seconds only if none exists."""
    result = client.query(
        f'SELECT LAST(value) FROM "{SETTINGS_RP}"."window_seconds"',
        database=db,
    )
    if isinstance(result, ResultSet) and list(result.get_points()):
        current = next(result.get_points())["last"]
        logger.info(f"window_seconds already set to {current}, skipping seed.")
        return

    client.write_points(
        [{
            "measurement": "window_seconds",
            "fields": {"value": window_seconds},
        }],
        database=db,
        retention_policy=SETTINGS_RP,
    )
    logger.info(f"Seeded window_seconds = {window_seconds}.")


def main():
    parser = argparse.ArgumentParser(description="Initialize InfluxDB for db-sentry.")
    parser.add_argument(
        "--default-window-seconds",
        type=int,
        default=DEFAULT_WINDOW_SECONDS,
        metavar="N",
        help=f"Window seconds to seed if no value exists (default: {DEFAULT_WINDOW_SECONDS})",
    )
    args = parser.parse_args()

    logger.info(f"Connecting to InfluxDB at {cfg.influx_host}:{cfg.influx_port} ...")
    client = InfluxDBClient(
        host=cfg.influx_host,
        port=cfg.influx_port,
        username=cfg.influx_user,
        password=cfg.influx_password,
    )

    db = cfg.influx_db

    # 1. Ensure database exists
    ensure_database(client, db)
    client.switch_database(db)

    # 2. Ensure default (sound data) retention policy — 90 days, set as default
    ensure_retention_policy(client, db, DEFAULT_RP, duration=SOUND_DATA_DURATION, default=True)

    # 3. Ensure settings retention policy — infinite duration
    ensure_retention_policy(client, db, SETTINGS_RP, duration="INF", default=False)

    # 4. Seed window_seconds if not present
    ensure_default_window_seconds(client, db, args.default_window_seconds)

    logger.info("InfluxDB initialization complete.")


if __name__ == "__main__":
    main()
