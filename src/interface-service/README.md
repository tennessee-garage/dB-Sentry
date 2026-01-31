# db-Sentry Interface Service

The interface-service is the main user-facing component of db-Sentry, providing a real-time monitoring dashboard on a small OLED display with rotary encoder controls. It manages:

- **OLED Display (128x32)**: Real-time visualization of system metrics and menu interface
- **Rotary Encoder**: User input for menu navigation and value adjustment
- **Neopixel LED Strip**: Visual indicators for system status and alerts
- **IPC Server**: Remote LED control for other services (e.g., limit-service)

## Prerequisites

### Hardware
- Raspberry Pi (tested on Pi 3b+)
- 128x32 SSD1306 OLED display (SPI connection)
- Rotary encoder with button
- WS2812B addressable LED strip (neopixel)
- Custom PCB (see pinout below)

### GPIO Pinout
```
Encoder:
  - Data (DT):    GPIO19
  - Clock (CLK):  GPIO13
  - Button (SW):  GPIO26

OLED Display (SPI):
  - DC:  GPIO24
  - RST: GPIO25
  - SPI0 (MOSI: GPIO10, MISO: GPIO9, SCLK: GPIO11, CE0: GPIO8)

LED Strip:
  - Data: GPIO18 (PWM)
```

## Setup

### 1. System Dependencies
Run the setup script to install all required system packages and configure GPIO:

```bash
./setup.sh
```

This script:
- Installs Python development tools and GPIO libraries
- Enables and starts the pigpiod daemon
- Creates a Python virtual environment with system packages
- Installs Python dependencies from requirements.txt

### 2. Environment Configuration
Create a `.env` file in this directory (or use defaults):

```bash
# LED Configuration
LED_SIMULATE=false           # Set to true for testing without hardware
LED_COUNT=20                 # Number of LEDs in strip
LED_PIN=18                   # GPIO pin for LED data

# Encoder Configuration (BCM GPIO numbers)
ENCODER_DATA_PIN=19          # GPIO19 (data/DT)
ENCODER_CLOCK_PIN=13         # GPIO13 (clock/CLK)
ENCODER_BUTTON_PIN=26        # GPIO26 (button/SW)
```

## Running

### One-off (Interactive Development)
Activate the virtual environment and run directly:

```bash
source venv/bin/activate
sudo venv/bin/python3 main.py
```

**Note:** Must use `sudo` for GPIO/LED hardware access.

### Via Systemd Service
The setup.sh process will create and install `/etc/systemd/system/db-sentry-interface-service.service`:

View logs:
```bash
sudo journalctl -u interface-service -f
```

Service management:
```bash
# Check service status
sudo systemctl status interface-service

# Start the service
sudo systemctl start interface-service

# Stop the service
sudo systemctl stop interface-service

# Restart the service
sudo systemctl restart interface-service
```

## Architecture

### Directory Structure
```
interface-service/
├── main.py                          # Entry point
├── config/
│   ├── __init__.py
│   ├── app_config.py               # Configuration management
│   └── menu_config.yaml            # Menu structure
├── interface/
│   ├── __init__.py
│   ├── sentry_hub_interface.py     # Main application class
│   ├── dynamic_menu.py             # Menu system
│   ├── menu.py                     # Menu rendering
│   ├── encoder.py                  # Rotary encoder control
│   ├── oled_display.py             # OLED display management
│   └── led_controller.py           # LED hardware control
├── ipc/
│   ├── __init__.py
│   ├── led_ipc_server.py           # IPC socket server
│   └── led_ipc_client.py           # IPC client library
├── utils/
│   ├── __init__.py
│   ├── system_info.py              # System monitoring
│   └── user_settings.py            # Settings persistence
├── scripts/
│   ├── test_*.py                   # Testing scripts
│   ├── example_*.py                # Usage examples
│   └── neopixel_pattern_demo.py    # LED pattern demonstrations
├── docs/
│   └── LED_CONTROL_ARCHITECTURE.md # LED IPC system documentation
├── requirements.txt
├── setup.sh                        # One-time setup script
├── db-sentry-interface.service     # Systemd service file
└── README.md                       # This file
```

### LED Control Architecture

The interface-service exclusively owns the LED hardware. Other services (like limit-service) control LEDs via a Unix domain socket IPC interface.

### Remote LED Control from limit-service

```python
from ipc.led_ipc_client import RemoteLEDClient

led = RemoteLEDClient()

# Show status alerts
led.show_alert('info')       # Green: Normal operation
led.show_alert('warning')    # Yellow: Warning state
led.show_alert('critical')   # Red: Critical alert

# Custom colors
led.set_color(255, 100, 0)   # Orange

# Control brightness
led.set_brightness(200)

# Turn off
led.clear()
```

The client handles connection errors gracefully - if interface-service isn't running, operations fail silently with logging.

## Troubleshooting

### GPIO Busy Errors
If you see `GPIO busy` or `lgpio.error` messages:

1. Ensure no other Python processes are using GPIO (e.g., limit-service)
2. Stop interface-service: `sudo systemctl stop interface-service`
3. Check running Python processes: `ps aux | grep python`
4. Kill lingering processes if needed: `sudo killall python3`

### OLED Not Displaying
- Check SPI is enabled: `raspi-config` → Interface Options → SPI
- Verify wiring: GPIO24 (DC), GPIO25 (RST), SPI pins
- Test with: `sudo python3 scripts/test_oled_scroll.py`

### LEDs Not Responding
- Check `LED_PIN` in `.env` (should be 18)
- Set `LED_SIMULATE=false` to use hardware
- Test with: `sudo python3 scripts/neopixel_pattern_demo.py rainbow 5`
- Ensure power supply is adequate for LED strip

### IPC Socket Permission Issues
If limit-service can't connect to LED control socket:
- Socket is created at: `/tmp/db-sentry-led-control.sock`
- Permissions should allow access from limit-service user
- Socket is only created after interface-service starts
- Add `After=interface-service.service` to limit-service systemd unit

## Development

### Adding Menu Items
Edit `config/menu_config.yaml` to add menu entries. See [interface/dynamic_menu.py](interface/dynamic_menu.py) for handler implementation.

### Customizing LED Alerts
Modify alert colors in [ipc/led_ipc_server.py](ipc/led_ipc_server.py) `handle_alert()` method.

### Extending Encoder Functionality
Add callbacks in [interface/encoder.py](interface/encoder.py) or handle in [interface/sentry_hub_interface.py](interface/sentry_hub_interface.py).

## License

Part of the db-Sentry project.

## Support

For issues or questions, refer to:
- [docs/LED_CONTROL_ARCHITECTURE.md](docs/LED_CONTROL_ARCHITECTURE.md) - LED IPC system details
- Individual module docstrings
- Test scripts for usage examples
