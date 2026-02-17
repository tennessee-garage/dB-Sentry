
#include "NetworkSetup.h"

#include <WiFi.h>
#include <WiFiClient.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <cstring>

#include "WirelessControl.h"
#include "wifi-info.h"

namespace {
	const char *kSetupRegisterUrl = "http://192.168.4.1:5000/api/sensor-register";

	const char *kPrefsNamespace = "db-sentry";
	const char *kPrefsSsidKey = "setup_ssid";
	const char *kPrefsPassKey = "setup_pass";

	String get_setup_ssid() {
		String setup = String(WIFI_SETUP_CREDENTIALS);
		int colonIndex = setup.indexOf(':');
		if (colonIndex > 0) {
			return setup.substring(0, colonIndex);
		}
		return setup;
	}

	bool call_sensor_register(const char *sensor_name, String &out_body) {
		HTTPClient http;
		WiFiClient client;
		http.begin(client, kSetupRegisterUrl);
		http.addHeader("Content-Type", "application/json");

		String payload = String("{\"name\":\"") + sensor_name + "\"}";
		int http_code = http.POST(payload);

		if (http_code <= 0) {
			Serial.print("Setup register POST failed: ");
			Serial.println(http.errorToString(http_code));
			http.end();
			return false;
		}

		out_body = http.getString();
		Serial.println("Setup register raw response body:");
		Serial.println(out_body);
		http.end();
		return true;
	}

	bool fetch_setup_credentials(const char *sensor_name,
								 String &out_ssid,
								 String &out_pass,
								 String &out_hostname) {
		String body;
		if (!call_sensor_register(sensor_name, body)) {
			return false;
		}

		JsonDocument doc;
		DeserializationError err = deserializeJson(doc, body);
		if (err) {
			Serial.print("Setup register JSON parse failed: ");
			Serial.println(err.c_str());
			return false;
		}

		bool success = doc["success"] | false;
		out_ssid = String(doc["ssid"] | "");
		out_pass = String(doc["password"] | "");
		out_hostname = String(doc["hostname"] | "");
		// We are not going to pass this back out to the caller, just print here on error
		String out_message = String(doc["message"] | "");

		if (!success) {
			Serial.print("Setup register failed: ");
			Serial.println(out_message);
			return false;
		}

		if (out_ssid.length() == 0 || out_pass.length() == 0) {
			Serial.println("Setup register returned empty SSID or password");
			return false;
		}

		return true;
	}

	void store_setup_credentials(const String &ssid, const String &pass) {
		Preferences prefs;
		prefs.begin(kPrefsNamespace, false);
		prefs.putString(kPrefsSsidKey, ssid);
		prefs.putString(kPrefsPassKey, pass);
		prefs.end();
	}

	String get_saved_credential() {
		Preferences prefs;
		prefs.begin(kPrefsNamespace, true);
		String savedSsid = prefs.isKey(kPrefsSsidKey) ? prefs.getString(kPrefsSsidKey, "") : "";
		String savedPass = prefs.isKey(kPrefsPassKey) ? prefs.getString(kPrefsPassKey, "") : "";
		prefs.end();

		if (savedSsid.length() == 0 || savedPass.length() == 0) {
			return "";
		}

		return savedSsid + ":" + savedPass;
	}

	void run_setup_mode(const char *sensorName, const char *hostname) {
		Serial.println("Connected to setup WiFi; entering setup mode...");

		String setup_ssid;
		String setup_pass;
		String setup_hostname;
		String setup_message;

		if (fetch_setup_credentials(sensorName, setup_ssid, setup_pass, setup_hostname)) {
			store_setup_credentials(setup_ssid, setup_pass);

			if (setup_hostname.length() == 0) {
				setup_hostname = hostname;
			}

			Serial.print("Setup provided SSID: ");
			Serial.println(setup_ssid);

			WiFi.disconnect();
			delay(200);
			WirelessControl::init_wifi(setup_ssid.c_str(), setup_pass.c_str(), setup_hostname.c_str());
		}
	}
}

void NetworkSetup::init_wifi_with_setup(const char *const *credentials,
										size_t count,
										const char *hostname,
										const char *sensorName) {
	if (count == 0) {
		Serial.println("Error: credentials list is empty");
		return;
	}

	String savedCredential = get_saved_credential();

	// Always start with setup credentials, then any saved credentials, then the normal list.
	size_t extra = savedCredential.length() > 0 ? 2 : 1;
	const char **credsCombined = new const char *[count + extra];

	size_t idx = 0;
	credsCombined[idx++] = WIFI_SETUP_CREDENTIALS;
	if (savedCredential.length() > 0) {
		credsCombined[idx++] = savedCredential.c_str();
	}
	for (size_t i = 0; i < count; ++i) {
		credsCombined[idx++] = credentials[i];
	}

	WirelessControl::init_wifi_from_list(credsCombined, idx, hostname);
	delete[] credsCombined;

	String setupSsid = get_setup_ssid();
	if (WirelessControl::is_connected && WiFi.SSID() == setupSsid) {
		run_setup_mode(sensorName, hostname);
	}
}
