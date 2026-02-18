"""DB-Sentry Setup Service - Raspberry Pi Access Point Configuration."""
from flask import Flask, request, jsonify, render_template, send_from_directory, redirect
from flask_cors import CORS
from config_manager import ConfigManager
from network_manager import NetworkManager
import threading
import time
import os
from datetime import datetime
import logging
import traceback
from werkzeug.exceptions import HTTPException
from zeroconf import Zeroconf, ServiceInfo
import socket

# Get absolute paths for templates and static folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'setup-service.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATE_DIR)
CORS(app)

# Initialize managers
config_manager = ConfigManager()
network_manager = NetworkManager(config_manager)

# mDNS (Zeroconf) setup
MDNS_SERVICE_TYPE = "_http._tcp.local."
MDNS_SERVICE_NAME = "db-sentry-setup"
mdns = Zeroconf()
mdns_info = None


def _get_mdns_ip() -> str:
    ip = network_manager.get_ip_address()
    if ip:
        return ip
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def register_mdns() -> None:
    global mdns_info
    ip = _get_mdns_ip()
    info = ServiceInfo(
        MDNS_SERVICE_TYPE,
        f"{MDNS_SERVICE_NAME}.{MDNS_SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=5000,
        properties={"path": "/"},
        server=f"{MDNS_SERVICE_NAME}.local."
    )
    if mdns_info:
        try:
            mdns.unregister_service(mdns_info)
        except Exception:
            pass
    mdns.register_service(info)
    mdns_info = info


def _finalize_stop_ap(selected_ssid: str, selected_password: str) -> None:
    """Perform AP stop and network transition in background after response is sent."""
    try:
        network_manager.stop_ap_mode()
        state['ap_mode'] = False
        state['network_cache'] = []
        state['network_cache_at'] = None
        register_mdns()

        if not selected_ssid:
            restored = network_manager.restore_previous_connection()
            state['setup_complete'] = restored
            if not restored:
                logging.error("AP stopped but no configured WiFi and previous connection restore failed")
            return

        success = network_manager.connect_to_wifi(selected_ssid, selected_password)
        if success:
            state['setup_complete'] = True
            return

        restored = network_manager.restore_previous_connection()
        state['setup_complete'] = restored
        if not restored:
            logging.error("AP stopped but failed to connect to selected WiFi and restore previous connection")
    except Exception as error:
        logging.error("Error during background AP stop workflow: %s", error)
        logging.error(traceback.format_exc())
    finally:
        state['finish_in_progress'] = False

# State management
state = {
    'ap_mode': False,
    'selected_wifi': {'ssid': None, 'password': None},
    'connected_sensors': [],
    'setup_complete': False,
    'finish_in_progress': False,
    'network_cache': [],
    'network_cache_at': None
}


@app.route('/')
def home():
    """Serve the setup page."""
    return send_from_directory(TEMPLATE_DIR, 'setup.html')


# Captive portal routes - redirect all unhandled requests to setup page
@app.route('/generate_204')  # Android
@app.route('/gen_204')  # Android
@app.route('/hotspot-detect.html')  # iOS
@app.route('/library/test/success.html')  # iOS
@app.route('/connecttest.txt')  # Windows
@app.route('/redirect')  # Windows
@app.route('/success.txt')  # Firefox
def captive_portal():
    """Handle captive portal detection."""
    return redirect('/', code=302)


@app.route('/<path:path>', methods=['GET'])
def captive_portal_fallback(path: str):
    """Redirect unknown non-API/non-static GET routes to setup page for captive clients."""
    if path.startswith('api/') or path.startswith('static/'):
        return "Not found", 404
    return redirect('/', code=302)


@app.route('/api/start-ap', methods=['POST'])
def start_ap():
    """Start access point mode."""
    if state['ap_mode']:
        return jsonify({'message': 'AP mode already active', 'success': True}), 200

    # Scan networks before switching to AP mode (scan usually fails while AP is active)
    state['network_cache'] = network_manager.scan_wifi_networks()
    state['network_cache_at'] = datetime.now().isoformat()
    
    success = network_manager.start_ap_mode()
    if success:
        state['ap_mode'] = True
        state['connected_sensors'] = []
        state['setup_complete'] = False
        register_mdns()
        return jsonify({
            'message': 'AP mode started', 
            'success': True,
            'ssid': config_manager.get('ap_ssid')
        }), 200
    else:
        return jsonify({'message': 'Failed to start AP mode', 'success': False}), 500


@app.route('/api/stop-ap', methods=['POST'])
def stop_ap():
    """Acknowledge finish request, then stop AP and connect WiFi in background."""
    if state['finish_in_progress']:
        return jsonify({
            'message': 'Finish setup already in progress.',
            'success': True
        }), 200

    state['finish_in_progress'] = True
    selected_ssid = state['selected_wifi']['ssid']
    selected_password = state['selected_wifi']['password']

    response = jsonify({
        'message': 'Finishing setup. AP will shut down and network will transition shortly.',
        'success': True
    })

    @response.call_on_close
    def _start_stop_ap_worker() -> None:
        worker = threading.Thread(
            target=_finalize_stop_ap,
            args=(selected_ssid, selected_password),
            daemon=True
        )
        worker.start()

    return response, 200


@app.route('/api/scan-networks', methods=['GET'])
def scan_networks():
    """Scan for available WiFi networks."""
    if state['ap_mode'] and state['network_cache']:
        return jsonify({
            'networks': state['network_cache'],
            'success': True,
            'cached': True,
            'cached_at': state['network_cache_at']
        }), 200

    networks = network_manager.scan_wifi_networks()
    return jsonify({'networks': networks, 'success': True, 'cached': False}), 200


@app.route('/api/configure-wifi', methods=['POST'])
def configure_wifi():
    """Configure WiFi credentials for the Pi to connect to."""
    data = request.get_json(silent=True) or {}
    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid:
        return jsonify({'message': 'SSID is required', 'success': False}), 400
    
    state['selected_wifi']['ssid'] = ssid
    state['selected_wifi']['password'] = password
    
    return jsonify({
        'message': 'WiFi configured successfully',
        'success': True,
        'ssid': ssid
    }), 200


@app.route('/api/sensor-register', methods=['POST'])
def sensor_register():
    """Register a sensor and provide it with WiFi credentials."""
    data = request.get_json(silent=True) or {}
    sensor_name = data.get('name')
    
    if not sensor_name:
        return jsonify({'message': 'Sensor name is required', 'success': False}), 400
    
    # Add sensor to connected list if not already present
    if sensor_name not in [s['name'] for s in state['connected_sensors']]:
        state['connected_sensors'].append({
            'name': sensor_name,
            'connected_at': datetime.now().isoformat()
        })
    
    # Return WiFi credentials to the sensor
    return jsonify({
        'success': True,
        'ssid': state['selected_wifi']['ssid'],
        'password': state['selected_wifi']['password'],
        'hostname': f"{MDNS_SERVICE_NAME}.local",
        'message': f'Sensor {sensor_name} registered'
    }), 200


@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    """Get list of connected sensors."""
    return jsonify({
        'sensors': state['connected_sensors'],
        'count': len(state['connected_sensors'])
    }), 200


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current setup status."""
    return jsonify({
        'ap_mode': state['ap_mode'],
        'wifi_configured': state['selected_wifi']['ssid'] is not None,
        'connected_sensors': state['connected_sensors'],
        'setup_complete': state['setup_complete'],
        'ip_address': network_manager.get_ip_address()
    }), 200


@app.route('/api/reset', methods=['POST'])
def reset_setup():
    """Reset the setup process."""
    state['selected_wifi'] = {'ssid': None, 'password': None}
    state['connected_sensors'] = []
    state['setup_complete'] = False
    
    return jsonify({'message': 'Setup reset', 'success': True}), 200


@app.errorhandler(Exception)
def handle_exception(error):
    """Log unhandled exceptions and return a 500 response."""
    if isinstance(error, HTTPException):
        return error
    logging.error("Unhandled exception: %s", error)
    logging.error(traceback.format_exc())
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    return "Internal server error", 500


if __name__ == '__main__':
    print("=" * 50)
    print("DB-Sentry Setup Service Starting")
    print("=" * 50)
    print(f"AP SSID: {config_manager.get('ap_ssid')}")
    print(f"AP Password: {config_manager.get('ap_password')}")
    print("=" * 50)
    register_mdns()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)