from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
	mqtt_broker: str = os.getenv("MQTT_BROKER", "localhost")
	mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
	mqtt_topic: str = os.getenv("MQTT_TOPIC", "db_sentry/#")

	# InfluxDB v1 settings (preferred if INFLUX_DB is set)
	influx_host: str = os.getenv("INFLUX_HOST", "localhost")
	influx_port: int = int(os.getenv("INFLUX_PORT", "8086"))
	influx_user: str = os.getenv("INFLUX_USER", "")
	influx_password: str = os.getenv("INFLUX_PASSWORD", "")
	influx_db: str = os.getenv("INFLUX_DB", "db_sentry")

	# InfluxDB v2 settings (optional)
	influx_url: str = os.getenv("INFLUX_URL", "http://localhost:8086")
	influx_token: str = os.getenv("INFLUX_TOKEN", "")
	influx_org: str = os.getenv("INFLUX_ORG", "")
	influx_bucket: str = os.getenv("INFLUX_BUCKET", "db_sentry")

	led_simulate: bool = os.getenv("LED_SIMULATE", "true").lower() in ("1", "true", "yes")
	led_count: int = int(os.getenv("LED_COUNT", "30"))
	
	dba_limit: int = int(os.getenv("DBA_LIMIT", "50"))
	min_triggering_sensors: int = int(os.getenv("MIN_TRIGGERING_SENSORS", 1))
	warn_percent: float = float(os.getenv("WARN_PERCENT", "0.8"))

	# Note that these use BCM GPIO pin numbers e.g. GPIO19 will be 19 here.
	encoder_data_pin: int = int(os.getenv("ENCODER_DATA_PIN", "19"))
	encoder_clock_pin: int = int(os.getenv("ENCODER_CLOCK_PIN", "13"))
	encoder_button_pin: int = int(os.getenv("ENCODER_BUTTON_PIN", "26"))

cfg = Config()
