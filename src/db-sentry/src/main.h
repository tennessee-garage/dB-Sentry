
#ifndef HOSTNAME
#define HOSTNAME "db-sentry"
#endif

// Syslog server connection info
#define SYSLOG_SERVER "tigerbackup"
#define SYSLOG_PORT 514
#define APP_NAME "db_sentry"

// Whether to log to a central syslog server
#ifndef LOG_TO_SYSLOG
#define LOG_TO_SYSLOG false
#endif

#ifndef MQTT_SERVER
#define MQTT_SERVER "db-sentry-hub"
#endif

#ifndef SETUP_WIFI
#define SETUP_WIFI "DB-Sentry-Setup"
#endif

// Interval for LEQ computation in milliseconds
#define LEQ_INTERVAL_MS 1000