#include "MQTT.h"
#include <Preferences.h>

#ifndef CLIENT_ID_NAME
#define CLIENT_ID_NAME ""
#endif

#ifndef CLIENT_ID_REWRITE
#define CLIENT_ID_REWRITE 0
#endif


MQTT::MQTT(const char *server, uint16_t port) {
	_client.setClient(_wifi);
	_client.setServer(server, port);
	_clientIdValue = _clientId();
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
	snprintf(topic, sizeof(topic), "db_sentry/%s/%s", _clientIdValue.c_str(), band);

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
		connected = _client.connect(_clientIdValue.c_str());

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

String MQTT::_generateClientId() {
	String clientId = "sensor-";
	clientId += String((uint32_t)ESP.getEfuseMac(), HEX);
	return clientId;
}

String MQTT::_getStoredClientId() {
	Preferences prefs;
	prefs.begin("db-sentry", false);
	String stored = prefs.getString("client_id", "");
	prefs.end();
	return stored;
}

String MQTT::_storeAndReturnClientId() {
	Preferences prefs;
	String clientId = "";

	if (String(CLIENT_ID_NAME).length() > 0) {
		prefs.begin("db-sentry", false);
		prefs.putString("client_id", CLIENT_ID_NAME);
		prefs.end();

		clientId = CLIENT_ID_NAME;
		Serial.print("MQTT client ID set from define: ");
		Serial.println(clientId);
	}

	return clientId;
}

String MQTT::_clientId() {
	String clientId = "";

	// See if we're configured to write a new client ID, otherwise pull the stored ID
	if (CLIENT_ID_REWRITE) {
		clientId = _storeAndReturnClientId();
	} else {
		clientId = _getStoredClientId();
	}

	// Make sure we have a client ID
	if (clientId.length() > 0) {
		Serial.print("MQTT client ID: ");
		Serial.println(clientId);
		return clientId;
	}

	// If no clientId at this point, generate one from the MAC address (default behavior) but don't store it
	return _generateClientId();
}