import logging
from mqtt.client import start_mqtt_service
from webserver import run_in_thread
from influx_client import create_influx_client
from config import cfg
import time
import os
from collections import deque
import threading
from mqtt.dba_message import DBAMessage
from mqtt.factory import create_message
import alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('limit-service')

influx = create_influx_client()

# Keep track of sensor band values
sensor_limits = influx.read_sensor_limits()
window_seconds = influx.read_window_seconds()
monitor = alert.Monitor(window_seconds)

# lock to protect sensor_band_values (callback runs in MQTT thread)
sensor_lock = threading.Lock()

def on_message(topic, value):
	"""Handle incoming MQTT messages. Topic format: db_sentry/$sensor/$band
	Maintain per-sensor band values and compute the max across bands for LED evaluation.
	"""
	logger.info("Received %s = %s; limits=%s", topic, value)
	message = create_message(topic, value)
	
	if type(message) is not DBAMessage:
		logger.debug("Topic does not match expected pattern 'db_sentry/$sensor/$band': %s", topic)
		return

	with sensor_lock:
		monitor.add_reading(message)

def check_alerts():
	sensors = monitor.sensor_averages()
	alerting = 0

	for sensor in sensors.keys():
		if sensor not in sensor_limits:
			influx.set_sensor_limit(sensor, cfg.dba_limit)
			sensor_limits[sensor] = cfg.dba_limit

		# Increment our alerting value for every sensor that is currently over
		if sensors[sensor] >= sensor_limits[sensor]:
			alerting += 1

	if alerting >= cfg.min_triggering_sensors:
		logger.info(f"ALERT TRIGGERED: {alerting} sensors over the threshold")


if __name__ == '__main__':
	logger.info("Starting limit-service")
	# start webserver
	run_in_thread(port=8000)
	# start MQTT service
	mqtt = start_mqtt_service(message_callback=on_message)
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		logger.info("Shutting down")
		mqtt.stop()
