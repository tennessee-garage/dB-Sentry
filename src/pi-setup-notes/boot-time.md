# Boot Time Tuning

Changes made to shorten the time from power-on until the display menu is usable on
`db-sentry-hub` (Pi 3 Model B). The menu appears once `limit-service`'s API answers, so
the critical path is InfluxDB → limit-service.

| Milestone (seconds after kernel start) | Before | After |
|---|---|---|
| "Booting up..." on display | ~15 | ~17.5 |
| Menu loaded | ~48 | ~22.5 |

Add ~6-7s of GPU firmware time before kernel start for time from power-on.

---

## 1. InfluxDB start script and unit

The packaged start script (`/usr/lib/influxdb/scripts/influxd-systemd-start.sh`) runs
`influx_inspect buildtsi` on every start. We use `index-version = "inmem"`, so the TSI
index it builds is never used (~8s wasted). The packaged unit also waits for
`network-online.target` (~6-8s), which InfluxDB doesn't need.

```bash
sudo install -D -m 755 influxdb/influxd-fast-start.sh /usr/local/lib/influxdb/influxd-fast-start.sh
sudo install -m 644 influxdb/influxdb.service /etc/systemd/system/influxdb.service
sudo systemctl daemon-reload
```

`/etc/systemd/system/influxdb.service` fully overrides the packaged unit, so check it
against `/usr/lib/systemd/system/influxdb.service` after a major InfluxDB upgrade.

## 2. InfluxDB config (`/etc/influxdb/influxdb.conf`)

```toml
[data]
  cache-snapshot-memory-size = "4m"
  cache-snapshot-write-cold-duration = "1m"

[monitor]
  store-enabled = false
```

- `store-enabled = false`: InfluxDB was writing its own stats to `_internal` every 10s.
  Nothing reads them, and because writes never stopped, the WAL was never snapshotted
  and grew to ~23MB, which took ~10s to replay every boot.
- Smaller snapshot thresholds keep the WAL small, so boot after an unclean power-off
  (common on battery) doesn't replay a large WAL.

Original config backed up to `/etc/influxdb/influxdb.conf.bak-pre-bootspeed`.

## 3. limit-service starts in parallel

`db-sentry-limit.service` is no longer ordered `After=` influxdb/mosquitto, so its slow
Python imports (~5s of FastAPI/pydantic) overlap their startup. `main.py` waits for
InfluxDB to answer a ping, and the MQTT client connects asynchronously and retries until
mosquitto is up (mosquitto still waits for `network-online.target`).

## 4. Boot-time priority for heavy services

`boot-priority/boot-priority.conf` is installed as a drop-in for `grafana-server` and
`telegraf` so they yield CPU/IO during boot only:

```bash
for u in grafana-server telegraf; do
  sudo install -D -m 644 boot-priority/boot-priority.conf /etc/systemd/system/$u.service.d/boot-priority.conf
done
sudo systemctl daemon-reload
```

## 5. Faster NTP sync after boot

The Pi has no RTC, so until `systemd-timesyncd` syncs it runs on the clock saved at
last shutdown. Its first attempt at boot happens before WiFi/DNS are up and fails, and
the default 30s retry meant the clock didn't sync until ~41-52s after boot (now ~33s).

```bash
sudo install -D -m 644 timesyncd/fast-retry.conf /etc/systemd/timesyncd.conf.d/fast-retry.conf
sudo systemctl restart systemd-timesyncd
```
