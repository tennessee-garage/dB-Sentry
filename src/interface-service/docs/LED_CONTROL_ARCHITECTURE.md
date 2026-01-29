# LED Control Architecture

This document describes how the LED control system works between `interface-service` and `limit-service`.

## Overview

```
┌─────────────────────┐
│  Neopixel Strip     │
│    (GPIO 18)        │
└──────────┬──────────┘
           │
      ┌────▼──────────────────────────┐
      │  interface-service (runs root)│
      │  - LEDController              │
      │  - LEDIPCServer               │
      │  - OLED Display               │
      │  - Menu System                │
      └────▲──────────────────────────┘
           │
      IPC: Unix Socket
      /tmp/db-sentry-led-control.sock
      ┌────┴─────────────────────────┐
      │  limit-service               │
      │  - RemoteLEDClient           │
      │  - Reads dB levels           │
      │  - Sends alerts              │
      └──────────────────────────────┘
```

## How It Works

### 1. interface-service (LED Owner)

When `interface-service` starts:

1. Initializes `LEDController` connected to GPIO 18
2. Creates `LEDIPCServer` that listens on `/tmp/db-sentry-led-control.sock`
3. Menu system can control LEDs directly
4. Other services connect via the socket to request LED changes

### 2. limit-service (LED Consumer)

When `limit-service` needs to show an alert:

1. Creates `RemoteLEDClient` instance
2. Calls methods like `show_alert('critical')` or `set_color(255, 0, 0)`
3. Client sends JSON command over the socket
4. `interface-service` executes the command and sends back response
5. LED changes immediately

## Usage in limit-service

### Basic Usage

```python
from ipc.led_ipc_client import RemoteLEDClient

# Create client
led = RemoteLEDClient()

# Show alerts
led.show_alert('info')      # Green
led.show_alert('warning')   # Yellow
led.show_alert('critical')  # Red

# Set custom colors
led.set_color(255, 100, 0)  # Orange

# Control brightness
led.set_brightness(200)

# Clear (turn off)
led.clear()
```

### Example: Alert Based on dB Level

```python
from ipc.led_ipc_client import RemoteLEDClient

def display_dB_alert(dB_level):
    led = RemoteLEDClient()
    
    if dB_level < 70:
        return led.show_alert('info')      # Normal level
    elif dB_level < 80:
        return led.show_alert('warning')   # Warning level
    else:
        return led.show_alert('critical')  # Dangerous level

# In your main loop:
for dB in measure_dB_levels():
    success = display_dB_alert(dB)
    if not success:
        logger.error("Failed to update LED status")
```

## API Reference

### RemoteLEDClient

#### Methods

- **`set_color(r, g, b)`** - Set solid RGB color
  - `r, g, b`: 0-255
  - Returns: `bool` (success/failure)

- **`show_alert(level)`** - Show alert with automatic coloring
  - `level`: 'info' (green), 'warning' (yellow), 'critical' (red)
  - Returns: `bool`

- **`clear()`** - Turn off all LEDs
  - Returns: `bool`

### Error Handling

All methods return `False` on error. The client logs errors to the logger, so you can capture them:

```python
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

led = RemoteLEDClient()

if not led.show_alert('warning'):
    logger.warning("LED update failed - interface-service may be down")
    # Continue anyway, LED status not critical
```

## Socket Details

- **Socket Path**: `/tmp/db-sentry-led-control.sock`
- **Permissions**: 0o666 (all users can connect)
- **Protocol**: JSON messages over Unix socket
- **Timeout**: Each request/response is quick (<100ms)

### Check socket is listening

```bash
# Should show the socket file
ls -l /tmp/db-sentry-led-control.sock

# Should show socket connections
netstat -an | grep db-sentry
```

## Troubleshooting

### "LED IPC socket not found"

- `interface-service` is not running
- Socket path is wrong (check `/tmp/db-sentry-led-control.sock` exists)
- Fix: Start `interface-service` first

### Connection refused

- `interface-service` crashed or is shutting down
- Fix: Restart `interface-service`

### Commands timeout

- Too many simultaneous connections (unlikely)
- LED operations taking too long (hardware issue)
- Fix: Check `interface-service` logs

### LEDs not responding

- `interface-service` running in simulate mode (check logs)
- GPIO permission issue (must run as root)
- LED strip not connected
- Fix: Check `interface-service` initialization logs

## Integration Checklist

- [ ] `interface-service` runs as root
- [ ] `LEDIPCServer` starts without errors
- [ ] Socket file created at `/tmp/db-sentry-led-control.sock`
- [ ] `limit-service` can import `RemoteLEDClient`
- [ ] Test `show_alert()` with each level
- [ ] Test `set_color()` with custom values
- [ ] Test error handling when socket unavailable
- [ ] Both services in systemd
- [ ] interface-service starts before limit-service
