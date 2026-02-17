
#ifndef NETWORKSETUP_H
#define NETWORKSETUP_H

#include <Arduino.h>

class NetworkSetup {
	public:
		static void init_wifi_with_setup(const char *const *credentials,
								 size_t count,
								 const char *hostname,
								 const char *sensorName);

		template <size_t N>
		static void init_wifi_with_setup(const char *const (&credentials)[N],
								 const char *hostname,
								 const char *sensorName) {
			init_wifi_with_setup(credentials, N, hostname, sensorName);
		}
};

#endif
