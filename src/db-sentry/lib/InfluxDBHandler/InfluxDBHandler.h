#ifndef INFLUXDBHANDLER_H
#define INFLUXDBHANDLER_H

#include <Arduino.h>
#include <InfluxDbClient.h>
#include <InfluxDbCloud.h>

#include "Logger.h"

class InfluxDBHandler {
    private:
    InfluxDBClient *_client;

    const char *_device;

    bool _write_metric(Point *point);

    public:
    InfluxDBHandler(const String &serverUrl, const String &db, const char *device);

	bool write_level_metric(const char *band, float leq_db, float max_db);

    String last_error();
};

#endif