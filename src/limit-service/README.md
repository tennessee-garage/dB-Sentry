# dB-Sentry Limit Service

A Python service for Raspberry Pi that:
- Subscribes to MQTT topics on the local broker and evaluates incoming numeric messages.
- Reads and writes limit values to InfluxDB on the Pi.
- Controls an LED strip (hardware mode) or simulates LED output (dev mode).
- Provides a simple HTTP UI to view and update 3-5 numeric limits.

Quick start

1. Install dependencies (on the Pi):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create a `.env` file next to `main.py` with Influx/MQTT settings, e.g.:

```ini
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_TOPIC=sensors/#
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=my-token
INFLUX_ORG=my-org
INFLUX_BUCKET=limits
LED_SIMULATE=true
LED_COUNT=30
``` 

3. Run locally:

```bash
python main.py
```

## Running as a systemd service

To run the service automatically on boot:

1. Install the service:

```bash
# Copy the service file to systemd
sudo cp db-sentry-limit-service.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable db-sentry-limit-service

# Start the service now
sudo systemctl start db-sentry-limit-service
```

2. Managing the service:

```bash
# Check status
sudo systemctl status db-sentry-limit-service

# View logs
sudo journalctl -u db-sentry-limit-service -f

# Stop the service
sudo systemctl stop db-sentry-limit-service

# Restart the service
sudo systemctl restart db-sentry-limit-service

# Disable auto-start on boot
sudo systemctl disable db-sentry-limit-service
```

**Note:** Make sure to update the `User`, `Group`, `WorkingDirectory`, and `ExecStart` paths in `db-sentry-limit-service.service` to match your system configuration before installing.

Files of interest
- `main.py` - entrypoint that starts MQTT, Influx and the web server.
- `mqtt_client.py` - MQTT subscription and message handling.
- `influx_client.py` - read/write limit values.
- `led_controller.py` - hardware/simulated LED control.
- `webserver.py` - FastAPI app exposing UI and update endpoints.

Notes
Notes
- InfluxDB: The project now prefers InfluxDB v1. Configure `INFLUX_HOST`, `INFLUX_PORT`, `INFLUX_USER`, `INFLUX_PASSWORD`, and `INFLUX_DB` in your `.env` to persist limits. If `INFLUX_DB` is not set or the v1 client is unavailable, the service will use an in-memory Noop client with default limits.
	The v2 `influxdb-client` settings (`INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET`) remain in `.env.example` for legacy reference but are not used by default.
- For real LED control on a Pi, set `LED_SIMULATE=false`; this will attempt to import `rpi_ws281x`.
