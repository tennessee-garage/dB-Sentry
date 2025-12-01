from typing import Dict
from config import cfg
import logging

from influxdb import InfluxDBClient as V1Client
from influxdb.resultset import ResultSet

logger = logging.getLogger('limit-service.influx-client')

class InfluxV1Client:
	def __init__(self):
		if V1Client is None:
			raise RuntimeError("influxdb package is not available")
		
		logger.info(f"Connecting to InfluxV1 client on {cfg.influx_host} with db {cfg.influx_db}")

		self.client = V1Client(host=cfg.influx_host, port=cfg.influx_port,
								username=cfg.influx_user,
								password=cfg.influx_password,
								database=cfg.influx_db)
		
		if self.client is None:
			raise RuntimeError("Could not connect to influxdb")

	def read_sensor_limits(self) -> Dict[str, int]:
		"""Find the dBA limits currently set (if any) for any sensorss."""
		try:
			limits = {}
			result = self.client.query("SELECT LAST(value) FROM sensor_limits group by sensor")
			if not isinstance(result, ResultSet):
				return {}

			for measurement, points in result.items():
				for point in points:
					sensor = measurement[1]['sensor']
					limits[sensor] = point['last']
			return limits
		except Exception:
			return {}

	def read_window_seconds(self) -> int:
		"""Read the configured moving average window in seconds."""
		result = self.client.query(f"SELECT LAST(value) FROM window_seconds")
		if not isinstance(result, ResultSet):
			return 1
		
		for measurement, points in result.items():
			for point in points:
				return int(point['last'])
		return 1
	
	def set_sensor_limit(self, sensor: str, limit: int):
		"""Set the dBA limit for a specific sensor."""
		point = [{
			"measurement": "sensor_limits",
			"tags": {"sensor": sensor},
			"fields": {"value": int(limit)}
		}]
		self.client.write_points(point)

	def set_window_seconds(self, seconds: int):
		"""Set the moving average window in seconds."""
		point = [{
			"measurement": "window_seconds",
			"fields": {"value": int(seconds)}
		}]
		self.client.write_points(point)

# Lightweight helper for when Influx is not configured
class NoopInfluxClient:
	def __init__(self):
		logger.warning("InfluxDB is not configured; using NoopInfluxClient")

		# store per-sensor limits (sensor -> limit)
		self._sensor_limits: Dict[str, int] = {}
		# default window seconds
		self._window_seconds: int = 30

	def read_sensor_limits(self) -> Dict[str, int]:
		"""Return currently configured sensor limits."""
		return dict(self._sensor_limits)

	def read_window_seconds(self) -> int:
		"""Return configured moving-average window seconds."""
		return int(self._window_seconds)

	def set_sensor_limit(self, sensor: str, limit: int):
		"""Set per-sensor limit."""
		try:
			self._sensor_limits[sensor] = int(limit)
		except Exception:
			pass

	def set_window_seconds(self, seconds: int):
		"""Set the moving-average window seconds."""
		try:
			self._window_seconds = int(seconds)
		except Exception:
			pass

# factory
def create_influx_client():
	# If INFLUX_DB is set, try to use v1 client
	if cfg.influx_db:
		try:
			return InfluxV1Client()
		except Exception:
			return NoopInfluxClient()
	# fallback to Noop (or later, support v2)
	return NoopInfluxClient()
