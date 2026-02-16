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

# State management
state = {
    'ap_mode': False,
    'selected_wifi': {'ssid': None, 'password': None},
    'connected_sensors': [],
    'setup_complete': False
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


@app.route('/api/start-ap', methods=['POST'])
def start_ap():
    """Start access point mode."""
    if state['ap_mode']:
        return jsonify({'message': 'AP mode already active', 'success': True}), 200
    
    success = network_manager.start_ap_mode()
    if success:
        state['ap_mode'] = True
        state['connected_sensors'] = []
        state['setup_complete'] = False
        return jsonify({
            'message': 'AP mode started', 
            'success': True,
            'ssid': config_manager.get('ap_ssid')
        }), 200
    else:
        return jsonify({'message': 'Failed to start AP mode', 'success': False}), 500


@app.route('/api/stop-ap', methods=['POST'])
def stop_ap():
    """Stop access point mode and connect to configured WiFi."""
    # Stop AP mode
    network_manager.stop_ap_mode()
    state['ap_mode'] = False

    if not state['selected_wifi']['ssid']:
        restored = network_manager.restore_previous_connection()
        if restored:
            return jsonify({
                'message': 'AP stopped and previous WiFi restored',
                'success': True
            }), 200
        return jsonify({
            'message': 'AP stopped but no WiFi network configured',
            'success': False
        }), 400

    # Connect to the selected WiFi
    success = network_manager.connect_to_wifi(
        state['selected_wifi']['ssid'],
        state['selected_wifi']['password']
    )

    if success:
        state['setup_complete'] = True
        return jsonify({
            'message': 'Connected to WiFi and AP stopped', 
            'success': True
        }), 200
    else:
        restored = network_manager.restore_previous_connection()
        if restored:
            return jsonify({
                'message': 'AP stopped and previous WiFi restored',
                'success': True
            }), 200
        return jsonify({
            'message': 'AP stopped but failed to connect to WiFi', 
            'success': False
        }), 500


@app.route('/api/scan-networks', methods=['GET'])
def scan_networks():
    """Scan for available WiFi networks."""
    networks = network_manager.scan_wifi_networks()
    return jsonify({'networks': networks, 'success': True}), 200


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
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)