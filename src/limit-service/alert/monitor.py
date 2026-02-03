from typing import Dict
import logging
import time

from mqtt.dba_message import DBAMessage
from alert.window import Window

logger = logging.getLogger('limit-service.alert.monitor')


class Monitor:
	def __init__(self, window_seconds: int):
		# sensor -> (band -> Window)
		self.sensors: Dict[str, Dict[str, Window]] = {}
		# Track last update time for each sensor
		self.sensor_timestamps: Dict[str, float] = {}
		self.window_seconds = window_seconds

	def add_reading(self, message: DBAMessage):
		"""Add a numeric reading for the given message's sensor/band.
		"""
		# Narrow optionals for the type-checker and runtime safety
		if message.sensor is None or message.band is None:
			return
		
		# Set defaults for nested dicts
		self.sensors.setdefault(message.sensor, {}).setdefault(message.band, Window(self.window_seconds))

		# Add the value to the appropriate Window
		self.sensors[message.sensor][message.band].append(message.value)
		
		# Update timestamp for this sensor
		self.sensor_timestamps[message.sensor] = time.time()

	def sensor_averages(self) -> Dict[str, int]:
		"""Get average values for sensors that have recent data.
		Sensors that haven't sent data in 1/2 * window_seconds are removed.
		
		Returns:
			Dictionary mapping sensor name to its maximum band average
		"""
		now = time.time()
		stale_threshold = self.window_seconds / 2
		
		# Remove sensors that haven't sent data recently
		stale_sensors = []
		for sensor, timestamp in self.sensor_timestamps.items():
			if now - timestamp > stale_threshold:
				stale_sensors.append(sensor)
		
		for sensor in stale_sensors:
			logger.info(f"Removing stale sensor: {sensor} (no data for {stale_threshold:.0f}s)")
			del self.sensors[sensor]
			del self.sensor_timestamps[sensor]
		
		max_values: Dict[str, int] = {}
		for sensor, bands in self.sensors.items():
			# Skip sensors with no recent data (all windows empty)
			if not any(len(window.dq) > 0 for window in bands.values()):
				continue
			
			# `bands` is typed as `Dict[str, Window]` so `band` below is a Window
			max_avg = max(band.average() for band in bands.values())
			max_values[sensor] = max_avg

		return max_values
	
	def update_window_seconds(self, window_seconds: int):
		"""Update the window size for all band windows."""
		self.window_seconds = window_seconds
		for bands in self.sensors.values():
			for window in bands.values():
				window.update_window(window_seconds)
