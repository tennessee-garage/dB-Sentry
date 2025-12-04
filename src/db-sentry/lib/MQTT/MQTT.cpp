#include "MQTT.h"


MQTT::MQTT(const char *server, uint16_t port) {
	_client.setClient(_wifi);
	_client.setServer(server, port);
}

void MQTT::loop() {
	if (!_client.connected()) {
		_reconnect();
	}
	_client.loop();
}

void MQTT::publishBandLevel(const char *band, float value) {
	// topic: db_sentry/<sensor>/<band>
  	char topic[64];
	snprintf(topic, sizeof(topic), "db_sentry/%s/%s", _clientId().c_str(), band);

	// payload: float as plain text, no JSON
	char payload[32];
	// No extra spaces; Telegraf data_format="value", data_type="float"
	snprintf(payload, sizeof(payload), "%.2f", value);

	Serial.print("Publishing to ");
	Serial.print(topic);
	Serial.print(" = ");
	Serial.println(payload);

	bool ok = _client.publish(topic, payload);
	if (!ok) {
		Serial.println("Publish failed!");
	}
}

void MQTT::_reconnect() {
	  // Loop until we're reconnected
	while (!_client.connected()) {
		Serial.print("Attempting MQTT connection... ");

		// Attempt to connect
		bool connected;
		connected = _client.connect(_clientId().c_str());

		if (connected) {
			Serial.println("connected!");
			// If you need to subscribe, do it here:
			// client.subscribe("some/topic");
		} else {
			Serial.print("failed, rc=");
			Serial.print(_client.state());
			Serial.println(" — retrying in 5 seconds");
			delay(5000);
		}
	}
}

String MQTT::_clientId() {
	// Generate and return a client ID
	String clientId = "sensor-";
    clientId += String((uint32_t)ESP.getEfuseMac(), HEX);
	Serial.print("MQTT client ID: ");
	Serial.println(clientId);
	return clientId;
}