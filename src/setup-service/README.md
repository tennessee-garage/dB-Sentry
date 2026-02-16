# DB-Sentry Setup Service

A Raspberry Pi service that creates an Access Point (AP) for easy WiFi configuration of your DB-Sentry sensor network.

## Features

- 🔌 **AP Mode**: Automatically creates a WiFi access point on demand
- 📡 **Network Scanning**: Scans and displays available WiFi networks
- 🌐 **Web Interface**: User-friendly setup page for configuration
- 🔧 **Sensor Registration**: Automatically configures sensors as they connect
- 🔒 **Secure**: Password-protected AP with configurable credentials
- ⚙️ **API-Driven**: RESTful API for all operations

## Architecture

### Components

1. **app.py** - Main Flask application with API endpoints
2. **config_manager.py** - Configuration file management
3. **network_manager.py** - WiFi and AP mode control
4. **templates/setup.html** - Web interface
5. **static/** - CSS and JavaScript for frontend

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve setup page (when in AP mode) |
| `/api/start-ap` | POST | Start access point mode |
| `/api/stop-ap` | POST | Stop AP and connect to configured WiFi |
| `/api/scan-networks` | GET | Scan for available WiFi networks |
| `/api/configure-wifi` | POST | Set WiFi credentials |
| `/api/sensor-register` | POST | Register sensor and provide WiFi info |
| `/api/sensors` | GET | Get list of connected sensors |
| `/api/status` | GET | Get current setup status |
| `/api/reset` | POST | Reset setup process |

## Installation

### Prerequisites

- Raspberry Pi (3/4/5 or Zero W)
- Raspberry Pi OS (Bullseye or later)
- WiFi adapter capable of AP mode

### Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y hostapd dnsmasq python3-pip network-manager
```

### Install Python Dependencies

```bash
cd /path/to/db-sentry-setup
pip3 install -r requirements.txt
```

### Configuration

Edit `config.json` (created automatically on first run):

```json
{
    "ap_ssid": "DB-Sentry-Setup",
    "ap_password": "not-too-loud",
    "ap_interface": "wlan0",
    "ap_channel": 6,
    "ap_ip": "192.168.4.1",
    "ap_netmask": "255.255.255.0",
    "dhcp_range_start": "192.168.4.2",
    "dhcp_range_end": "192.168.4.20"
}
```

**Note**: `config.json` is not tracked in git for security.

## Usage

### Start the Service

```bash
python3 app.py
```

### Enable AP Mode

**Via API:**
```bash
curl -X POST http://localhost:5000/api/start-ap
```

**Via Code:**
```python
import requests
requests.post('http://localhost:5000/api/start-ap')
```

### Connect to Setup Page

1. Enable AP mode on the Pi
2. Connect your mobile device to WiFi SSID: `DB-Sentry-Setup`
3. Enter password: `not-too-loud`
4. Open browser and navigate to: `http://192.168.4.1:5000`
5. Follow the setup wizard

### Setup Workflow

1. **Scan Networks**: The Pi scans and displays available WiFi networks
2. **Select Network**: Choose your home/office WiFi
3. **Enter Password**: Provide the WiFi password
4. **Turn On Sensors**: Power on your DB-Sensors
5. **Sensor Registration**: Sensors automatically register and receive WiFi credentials
6. **Complete**: Finish setup - Pi reconnects to your WiFi

### Sensor Integration

Sensors should make a POST request to register:

```python
import requests

response = requests.post('http://192.168.4.1:5000/api/sensor-register', 
    json={'name': 'sensor-01'}
)

if response.status_code == 200:
    data = response.json()
    wifi_ssid = data['ssid']
    wifi_password = data['password']
    # Configure sensor WiFi with these credentials
```

## Systemd Service (Optional)

A ready-to-use unit file is included: [db-sentry-setup.service](db-sentry-setup.service).

Install it and enable the service:
```bash
sudo cp /home/garth/dB-Sentry/src/setup-service/db-sentry-setup.service /etc/systemd/system/db-sentry-setup.service
sudo systemctl daemon-reload
sudo systemctl enable db-sentry-setup
sudo systemctl start db-sentry-setup
```

Check status and logs:
```bash
sudo systemctl status db-sentry-setup
journalctl -u db-sentry-setup -f
```

## Security Considerations

1. **Change Default Credentials**: Update `ap_ssid` and `ap_password` in `config.json`
2. **Network Isolation**: AP mode creates an isolated network
3. **Temporary Mode**: AP should only be active during setup
4. **Password Protection**: WiFi credentials are only transmitted over local network

## Troubleshooting

### Check Application Logs

The service writes logs to:

- [logs/setup-service.log](logs/setup-service.log)

If you see 500 errors or crashes, check this file and `journalctl -u db-sentry-setup -f` for stack traces.

### Enable Persistent Journal (Optional)

If `journalctl -b -1` reports no persistent journal, enable it so logs survive reboots:

```bash
sudo sed -i 's/^#\?Storage=.*/Storage=persistent/' /etc/systemd/journald.conf
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

Then you can view previous boot logs:

```bash
sudo journalctl -u db-sentry-setup -b -1
```

### AP Mode Won't Start

```bash
# Check interface status
ip link show wlan0

# Verify hostapd is installed
which hostapd

# Check for conflicting services
sudo systemctl status hostapd
sudo systemctl status dnsmasq
```

### Can't Scan Networks

```bash
# Test network manager
nmcli dev wifi list

# Test with iwlist
sudo iwlist wlan0 scan
```

### Sensors Not Connecting

1. Verify AP is active: `curl http://localhost:5000/api/status`
2. Check sensor is in range
3. Verify sensor is making correct API call
4. Check logs: `journalctl -u db-sentry-setup -f`

## Development

### Project Structure

```
db-sentry-setup/
├── app.py                 # Main application
├── config_manager.py      # Configuration management
├── network_manager.py     # Network utilities
├── config.json           # Settings (not in git)
├── requirements.txt      # Python dependencies
├── templates/
│   └── setup.html       # Web interface
├── static/
│   ├── style.css        # Styles
│   └── script.js        # Frontend logic
└── README.md            # This file
```

### Testing

```bash
# Start service
python3 app.py

# In another terminal, test API
curl http://localhost:5000/api/status
curl -X POST http://localhost:5000/api/start-ap
curl http://localhost:5000/api/scan-networks
```

## License

[Your License Here]

## Contributing

[Contribution Guidelines]
