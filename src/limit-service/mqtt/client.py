import paho.mqtt.client as mqtt
import json
import logging
from threading import Thread
from influx_client import create_influx_client
from config import cfg

logger = logging.getLogger(__name__)

class MQTTService:
    def __init__(self, message_callback=None):
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.message_callback = message_callback
        self.influx = create_influx_client()
        self._running = False

    def _on_connect(self, client, userdata, flags, rc):
        logger.info("Connected to MQTT broker %s:%d with rc=%s", cfg.mqtt_broker, cfg.mqtt_port, rc)
        client.subscribe(cfg.mqtt_topic)

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode('utf-8')
        topic = msg.topic
        logger.debug("MQTT message on %s: %s", topic, payload)
        # Try to extract number
        try:
            value = float(payload)
        except Exception:
            # try JSON
            try:
                data = json.loads(payload)
                if isinstance(data, dict) and 'value' in data:
                    value = float(data['value'])
                else:
                    logger.warning("MQTT payload not numeric or JSON with 'value': %s", payload)
                    return
            except Exception:
                logger.warning("Unable to parse MQTT payload: %s", payload)
                return

        if self.message_callback:
            try:
                self.message_callback(topic, value)
            except Exception:
                logger.exception("message_callback raised")

    def start(self):
        self.client.connect(cfg.mqtt_broker, cfg.mqtt_port, 60)
        self._running = True
        # Use a background thread for the loop
        t = Thread(target=self.client.loop_forever, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        try:
            self.client.disconnect()
        except Exception:
            pass

# simple usage helper
_service_instance = None

def start_mqtt_service(message_callback=None):
    global _service_instance
    if _service_instance is None:
        _service_instance = MQTTService(message_callback=message_callback)
        _service_instance.start()
    return _service_instance
