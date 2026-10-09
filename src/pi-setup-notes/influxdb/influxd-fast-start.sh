#!/bin/bash -e
# Faster replacement for /usr/lib/influxdb/scripts/influxd-systemd-start.sh.
#
# The packaged script runs `influx_inspect buildtsi` on every start, which rebuilds
# a TSI index from scratch. Our config uses index-version = "inmem", so that index is
# never used and the rebuild just costs ~8s of boot time on the Pi 3. The packaged
# script also runs `influxd config` several times to find the bind address, which
# is slow on the Pi; we use the default HTTP port directly.

CONFIG=/etc/influxdb/influxdb.conf

/usr/bin/influxd -config "${CONFIG}" ${INFLUXD_OPTS} &
PID=$!
echo $PID > /var/lib/influxdb/influxd.pid

# Wait for the HTTP API so units ordered after influxdb see a working server
until curl -s -o /dev/null http://127.0.0.1:8086/health; do
  kill -0 $PID 2>/dev/null || { echo "influxd exited during startup"; exit 1; }
  sleep 0.2
done
echo "InfluxDB started"
