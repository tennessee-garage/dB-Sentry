import logging
from typing import Dict
from mqtt.client import start_mqtt_service
from webserver import run_in_thread, set_limits_changed_event, set_window_seconds_changed_event
from influx_client import create_influx_client
from config import cfg
import time
import os
from collections import deque
import threading
from mqtt.dba_message import DBAMessage
from mqtt.factory import create_message
import alert
from ipc.led_ipc_client import RemoteLEDClient


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('limit-service')

influx = create_influx_client()

# Events to signal when configuration has changed
limits_changed_event = threading.Event()
window_seconds_changed_event = threading.Event()

# Keep track of sensor band values
sensor_limits = influx.read_sensor_limits()
window_seconds = influx.read_window_seconds()
monitor = alert.Monitor(window_seconds)

# lock to protect sensor_band_values (callback runs in MQTT thread)
sensor_lock = threading.Lock()

led = RemoteLEDClient()

def on_message(topic, value):
	"""Handle incoming MQTT messages. Topic format: db_sentry/$sensor/$band
	Maintain per-sensor band values and compute the max across bands for LED evaluation.
	"""
	logger.debug(f"Received message {topic} = {value}")
	message = create_message(topic, value)
	
	if type(message) is not DBAMessage:
		logger.debug(f"Topic does not match expected pattern 'db_sentry/$sensor/$band': {topic}")
		return

	with sensor_lock:
		monitor.add_reading(message)

sensors_normal = dict[str, bool]()
def check_alerts():
	sensors = monitor.sensor_averages()
	alerting = 0

	for sensor in sensors.keys():
		sensors_normal.setdefault(sensor, False)

		if sensor not in sensor_limits:
			logger.info(f"No limit set for sensor {sensor}, using default {cfg.dba_limit}")
			influx.set_sensor_limit(sensor, cfg.dba_limit)
			sensor_limits[sensor] = cfg.dba_limit

		logger.debug(f"Sensor {sensor} average is currently {sensors[sensor]:.2f}")

		if sensors[sensor] >= sensor_limits[sensor]:
			# Increment our alerting value for every sensor that is currently over
			logger.debug(f"Warning: Sensor {sensor} average {sensors[sensor]:.2f} exceeds ALERT threshold")
			alerting += 1
			influx.set_sensor_alarm_state(sensor, "ALERT")
			sensors_normal[sensor] = False
			led.push_alert_status('alert')
		elif sensors[sensor] > sensor_limits[sensor] * cfg.warn_percent:
			# Warn if we're over the warn threshold
			logger.debug(f"Warning: Sensor {sensor} average {sensors[sensor]:.2f} exceeds WARN threshold")
			influx.set_sensor_alarm_state(sensor, "WARN")
			sensors_normal[sensor] = False
			led.push_alert_status('warn')
		else:
			# Note normal state
			logger.debug(f"Sensor {sensor} average {sensors[sensor]:.2f} is within normal limits")
			# To save writes, only set NORMAL if we were previously not normal
			if not sensors_normal[sensor]:
				influx.set_sensor_alarm_state(sensor, "NORMAL")
			led.push_alert_status('normal')

			sensors_normal[sensor] = True
	
	if alerting >= cfg.min_triggering_sensors:
		logger.info(f"ALERT TRIGGERED: {alerting} sensors over the threshold")


if __name__ == '__main__':
	logger.info("Starting limit-service")
	
	# Register change events with the webserver
	set_limits_changed_event(limits_changed_event)
	set_window_seconds_changed_event(window_seconds_changed_event)
	
	# start webserver
	run_in_thread(port=8000)

	# start MQTT service
	mqtt = start_mqtt_service(message_callback=on_message)

	# main loop: check alerts once per second
	try:
		while True:
			# Check if limits have changed and refresh if needed
			if limits_changed_event.is_set():
				logger.info("Refreshing sensor limits from InfluxDB")
				sensor_limits.clear()
				sensor_limits.update(influx.read_sensor_limits())
				limits_changed_event.clear()
			
			# Check if window_seconds have changed and refresh if needed
			if window_seconds_changed_event.is_set():
				window_seconds = influx.read_window_seconds()
				logger.info(f"Updating monitor window to {window_seconds} seconds")
				monitor.update_window_seconds(window_seconds)
				window_seconds_changed_event.clear()
			
			check_alerts()
			time.sleep(1)

	except KeyboardInterrupt:
		logger.info("Shutting down")
		mqtt.stop()
