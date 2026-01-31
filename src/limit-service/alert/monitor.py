from typing import Dict
import logging

from mqtt.dba_message import DBAMessage
from alert.window import Window

logger = logging.getLogger('limit-service.alert.monitor')


class Monitor:
	def __init__(self, window_seconds: int):
		# sensor -> (band -> Window)
		self.sensors: Dict[str, Dict[str, Window]] = {}
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

	def sensor_averages(self) -> Dict[str, int]:
		max_values: Dict[str, int] = {}
		for sensor, bands in self.sensors.items():
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
