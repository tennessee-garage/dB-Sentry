#include <InfluxDBHandler.h>
#include "WirelessControl.h"

extern Logger *LOGGER;

InfluxDBHandler::InfluxDBHandler(const String &url, const String &db, const char *device) : _device(device) {
    LOGGER->log("Initializing InfluxDBHandler");
    Serial.println("Initialziing InfluxDB: ");

    _client = new InfluxDBClient(url, db);

	// Configure write buffering
	_client->setWriteOptions(
		WriteOptions()
		.batchSize(10)     // how many points before a flush
		.bufferSize(50)    // max points to keep in RAM
		.flushInterval(5)  // seconds between forced flushes
	);

    if (_client->validateConnection()) {
        Serial.println("\tConnected to InfluxDB: " + _client->getServerUrl());
        LOGGER->log("Connected to InfluxDB at " + _client->getServerUrl());
    } else {
        Serial.println("\tInfluxDB connection failed: " + _client->getLastErrorMessage());
        LOGGER->log_error("InfluxDB connection failed: " + _client->getLastErrorMessage());
    }

    if (WirelessControl::is_connected) {
        LOGGER->log("Logging events to InfluxDB is enabled");
    }
}

bool InfluxDBHandler::write_level_metric(const char *band, float leq_db, float max_db) {
	Point level("band_level");
	level.addTag("device", _device);
	level.addTag("band", band);

	level.addField("dBA_leq", leq_db);
	level.addField("dBA_max", max_db);

	return _write_metric(&level);
}

bool InfluxDBHandler::_write_metric(Point *point) {
    if (!WirelessControl::is_connected) {
        return true;
    }

    if (!_client->writePoint(*point)) {
        String error_msg = last_error();
        if (error_msg.length() > 0) {
            LOGGER->log_error("Failed to write metric {" + point->toLineProtocol() + "}: " + error_msg);
            Serial.println("Failed to write point " + point->toLineProtocol() + ": " + error_msg);
        } else {
            LOGGER->log_error("Failed to write metric {" + point->toLineProtocol() + "}: Unknown InfluxDB error");
            Serial.println("Failed to write point " + point->toLineProtocol() + ": Unknown InfluxDB error");
        }
        return false;
    }

    return true;
}

String InfluxDBHandler::last_error() {
    return _client->getLastErrorMessage();
}
