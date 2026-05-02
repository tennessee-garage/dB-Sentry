# Reboot Diagnostics & System Health Monitoring

Notes on changes made to improve reboot forensics on the `db-sentry-hub` Raspberry Pi.
The Pi runs InfluxDB, Grafana, Mosquitto (MQTT broker), and several custom services
for a sound volume monitoring system.

---

## Problem

The Pi was experiencing unexpected reboots with no clear cause. The suspected trigger
was a physical jolt causing a momentary power dropout via the Adafruit PowerBoost 1000C
battery interface, but this needed to be confirmed.

---

## 1. Persistent systemd Journal

By default, Raspberry Pi OS ships with a drop-in config that forces the journal to
volatile (RAM-only) storage, meaning all logs are lost on reboot. This overrides it.

**Root cause:** `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf` sets
`Storage=volatile`, which wins over the main `journald.conf`.

**Fix:** Create a higher-priority override in `/etc/` (files here beat `/usr/lib/`,
and prefix `50` beats `40`):

```bash
sudo mkdir -p /etc/systemd/journald.conf.d/
sudo tee /etc/systemd/journald.conf.d/50-persistent.conf << 'EOF'
[Journal]
Storage=persistent
EOF
```

Ensure the journal directory and machine-ID subdirectory exist with correct ownership:

```bash
sudo mkdir -p /var/log/journal
sudo systemd-tmpfiles --create --prefix /var/log/journal
sudo mkdir -p /var/log/journal/$(cat /etc/machine-id)
sudo chown root:systemd-journal /var/log/journal/$(cat /etc/machine-id)
sudo chmod 2755 /var/log/journal/$(cat /etc/machine-id)
sudo systemctl restart systemd-journald
sudo systemctl kill --kill-who=main --signal=USR1 systemd-journald
```

**Verify it worked** (after next reboot):

```bash
journalctl --list-boots        # should show multiple boots
journalctl -b -1 -k            # kernel messages from previous boot
```

---

## 2. Voltage / Throttle Monitor

Logs undervoltage and CPU throttling events continuously. If the Pi is browning out,
this will show it.

**Script:** `/usr/local/bin/throttle-monitor.sh`

```bash
sudo tee /usr/local/bin/throttle-monitor.sh << 'EOF'
#!/bin/bash
while true; do
    STATUS=$(vcgencmd get_throttled)
    if [ "$STATUS" != "throttled=0x0" ]; then
        echo "$(date -Iseconds) THROTTLE: $STATUS" >> /var/log/throttle.log
    fi
    sleep 5
done
EOF
sudo chmod +x /usr/local/bin/throttle-monitor.sh
```

**Service:** `/etc/systemd/system/throttle-monitor.service`

```bash
sudo tee /etc/systemd/system/throttle-monitor.service << 'EOF'
[Unit]
Description=Voltage/Throttle Monitor
After=multi-user.target

[Service]
ExecStart=/usr/local/bin/throttle-monitor.sh
Restart=always
StandardOutput=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now throttle-monitor
```

**Check the log:**

```bash
cat /var/log/throttle.log
```

**Throttle value reference** (from `vcgencmd get_throttled`):

| Bit | Hex | Meaning |
|-----|-----|---------|
| 0 | 0x1 | Currently under-voltage |
| 1 | 0x2 | Currently throttled |
| 16 | 0x10000 | Under-voltage has occurred this boot |
| 17 | 0x20000 | Throttling has occurred this boot |

A clean system returns `throttled=0x0`.

---

## 3. Heartbeat & Boot Reason Logger

Two paired services: a heartbeat that writes a timestamp every 30 seconds, and a
boot-time check that records whether the previous shutdown was clean or dirty.

If the Pi reboots unexpectedly, the boot-reason log will say `UNCLEAN REBOOT` and
show the timestamp of the last heartbeat — telling you roughly when it went down.

**Heartbeat script:** `/usr/local/bin/heartbeat.sh`

```bash
sudo tee /usr/local/bin/heartbeat.sh << 'EOF'
#!/bin/bash
HBFILE=/var/log/last-heartbeat
while true; do
    echo "$(date -Iseconds) PID:$$" > $HBFILE
    sleep 30
done
EOF
sudo chmod +x /usr/local/bin/heartbeat.sh
```

**Boot check script:** `/usr/local/bin/check-last-boot.sh`

```bash
sudo tee /usr/local/bin/check-last-boot.sh << 'EOF'
#!/bin/bash
HBFILE=/var/log/last-heartbeat
LOGFILE=/var/log/boot-reason.log
if [ -f "$HBFILE" ]; then
    echo "$(date -Iseconds) UNCLEAN REBOOT. Last heartbeat: $(cat $HBFILE)" >> $LOGFILE
else
    echo "$(date -Iseconds) FIRST BOOT or clean shutdown" >> $LOGFILE
fi
EOF
sudo chmod +x /usr/local/bin/check-last-boot.sh
```

**Boot check service:** `/etc/systemd/system/boot-check.service`

```bash
sudo tee /etc/systemd/system/boot-check.service << 'EOF'
[Unit]
Description=Check Last Boot Reason
DefaultDependencies=no
Before=heartbeat.service
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/check-last-boot.sh

[Install]
WantedBy=multi-user.target
EOF
```

**Heartbeat service:** `/etc/systemd/system/heartbeat.service`

```bash
sudo tee /etc/systemd/system/heartbeat.service << 'EOF'
[Unit]
Description=Heartbeat Logger
After=boot-check.service multi-user.target

[Service]
ExecStart=/usr/local/bin/heartbeat.sh
Restart=always
StandardOutput=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now boot-check
sudo systemctl enable --now heartbeat
```

**Check the log:**

```bash
cat /var/log/boot-reason.log
```

---

## 4. InfluxDB Retention Policy

The default `autogen` retention policy had `duration=0s` (keep forever). Updated to
90 days, which is more than sufficient for this use case (a few monitoring nights per
year, data only needed during and shortly after events).

```bash
influx
```

```sql
ALTER RETENTION POLICY "autogen" ON "db_sentry" DURATION 90d DEFAULT
SHOW RETENTION POLICIES ON "db_sentry"
```

Expected output after change: `duration` should show `2160h0m0s`.

---

## Diagnostic Commands Reference

```bash
# Check current throttle/voltage state
vcgencmd get_throttled

# View previous boot kernel messages (requires persistent journal)
journalctl -b -1 -k

# List all recorded boots
journalctl --list-boots

# Check for OOM kills or panics
journalctl -b -1 | grep -E -i "killed|oom|panic|reset"

# View throttle log
cat /var/log/throttle.log

# View boot reason history
cat /var/log/boot-reason.log

# Check service status
sudo systemctl status throttle-monitor
sudo systemctl status heartbeat
sudo systemctl status boot-check
```
