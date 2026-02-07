#ifndef MQTT_H
#define MQTT_H

#include <Arduino.h>
#include <PubSubClient.h>
#include <WiFiClient.h>

#define DEFAULT_MQTT_PORT 1883

class MQTT {
public:

	MQTT(const char *server, uint16_t port = DEFAULT_MQTT_PORT);
	void loop();

	void publishBandLevel(const char *band, float value);

private:
	PubSubClient _client;
	WiFiClient _wifi;
	String _clientIdValue;

	String _clientId();
	String _generateClientId();
	String _getStoredClientId();
	String _storeAndReturnClientId();
	void _reconnect();
};

#endif // MQTT_H
