"""IPC server for LED control.

Allows other services (like limit-service) to control LEDs via Unix socket.
"""

import json
import logging
import os
import socket
import threading
from collections import deque
from pathlib import Path
from typing import Optional, Callable
from interface.led_controller import LEDController
from utils.user_settings import user_settings
from utils.color_utils import hsv_to_rgb

logger = logging.getLogger(__name__)


class LEDIPCServer:
    """Unix socket server for remote LED control."""
    
    DEFAULT_SOCKET_PATH = "/tmp/db-sentry-led-control.sock"
    
    def __init__(self, led_controller: LEDController, socket_path: Optional[str] = None):
        """Initialize the IPC server.
        
        Args:
            led_controller: LEDController instance to control
            socket_path: Path to Unix socket (default: /tmp/db-sentry-led-control.sock)
        """
        self.led = led_controller
        self.socket_path = socket_path or self.DEFAULT_SOCKET_PATH
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Status history FIFO (max 10 entries)
        # Stores tuples of (status, timestamp)
        self.status_history = deque(maxlen=10)
        
        # Pause updates flag (for when user is adjusting LED colors)
        self.pause_updates = False
        
        # Sensor data: dict of sensor_name -> measurements_per_second
        self.sensor_data = {}
    
    def start(self):
        """Start the IPC server in a background thread."""
        if self.running:
            logger.warning("LED IPC server already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()
        logger.info(f"LED IPC server started on {self.socket_path}")
    
    def stop(self):
        """Stop the IPC server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("LED IPC server stopped")
    
    def _run_server(self):
        """Main server loop (runs in background thread)."""
        # Clean up any existing socket file
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception as e:
                logger.error(f"Failed to remove old socket: {e}")
        
        # Create socket directory if needed
        socket_dir = os.path.dirname(self.socket_path)
        if socket_dir:
            Path(socket_dir).mkdir(parents=True, exist_ok=True)
        
        try:
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(1)
            os.chmod(self.socket_path, 0o666)  # Allow all users to connect
            
            logger.info(f"LED IPC server listening on {self.socket_path}")
            
            while self.running:
                try:
                    # Set timeout so we can check running flag
                    self.server_socket.settimeout(1.0)
                    conn, _ = self.server_socket.accept()
                    
                    # Handle request in this thread (requests are quick)
                    self._handle_request(conn)
                    conn.close()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            logger.error(f"LED IPC server error: {e}")
        finally:
            if self.server_socket:
                try:
                    self.server_socket.close()
                except Exception:
                    pass
    
    def _handle_request(self, conn: socket.socket):
        """Handle a single client request.
        
        Args:
            conn: Socket connection to client
        """
        try:
            # Receive and parse request
            data = conn.recv(1024).decode('utf-8')
            if not data:
                return
            
            request = json.loads(data)
            command = request.get('command')
            
            # Route to appropriate handler
            if command == 'set_color':
                r = request.get('r', 0)
                g = request.get('g', 0)
                b = request.get('b', 0)
                self.led.set_color(r, g, b)
                response = {'status': 'ok', 'command': command}
            
            elif command == 'alert':
                level = request.get('level', 'warning')  # 'info', 'warning', 'critical'
                color_map = {
                    'info': (0, 255, 0),      # Green
                    'warning': (255, 255, 0), # Yellow
                    'critical': (255, 0, 0),  # Red
                }
                color = color_map.get(level, (255, 255, 255))
                self.led.set_color(*color)
                response = {'status': 'ok', 'command': command, 'level': level}
            
            elif command == 'clear':
                self.led.set_color(0, 0, 0)
                response = {'status': 'ok', 'command': command}
            
            elif command == 'push_status':
                alert_status = request.get('status', 'normal')  # 'normal', 'warn', 'alert', 'none'
                if alert_status in ['normal', 'warn', 'alert', 'none']:
                    self._push_status(alert_status)
                    response = {'status': 'ok', 'command': command, 'alert_status': alert_status}
                else:
                    response = {'status': 'error', 'message': f'Invalid status: {alert_status}'}
            
            elif command == 'update_sensors':
                sensors = request.get('sensors', {})  # dict of sensor_name -> mps
                self.sensor_data = sensors
                response = {'status': 'ok', 'command': command, 'sensor_count': len(sensors)}
            
            else:
                response = {'status': 'error', 'message': f'Unknown command: {command}'}
            
            # Send response
            conn.send(json.dumps(response).encode('utf-8'))
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON request: {e}")
            try:
                conn.send(json.dumps({'status': 'error', 'message': 'Invalid JSON'}).encode('utf-8'))
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            try:
                conn.send(json.dumps({'status': 'error', 'message': str(e)}).encode('utf-8'))
            except Exception:
                pass
    
    def _push_status(self, status: str):
        """Push a status update to the FIFO and render to LEDs.
        
        Args:
            status: Status string ('normal', 'warn', 'alert', 'none')
        """
        self.status_history.append(status)
        if not self.pause_updates:
            self._render_status_history()
    
    def _render_status_history(self):
        """Render the status history to the LED strip.
        
        LED layout:
        - LEDs 0-9 (top row): Status history as FIFO (right-justified)
          - LED 9 = Most recent
          - LED 0 = Oldest (or first LED if fewer than 10)
          - Empty slots are unlit
        - LEDs 10-19 (bottom row): All lit with color of most recent status
        
        Colors are determined by user-configured hue values from settings.
        """
        pixels = []
        
        # Top LEDs (0-9): Status history FIFO (right-justified)
        # Convert deque to list for indexing
        history_list = list(self.status_history)
        history_len = len(history_list)
        
        for i in range(10):
            if history_len > 0:
                # Right-justify: empty slots on left, data on right
                data_start_led = 10 - history_len
                if i < data_start_led:
                    # Empty slot - unlit
                    r, g, b = 0, 0, 0
                else:
                    # Data slot: index into history_list
                    history_index = i - data_start_led
                    status = history_list[history_index]
                    # Handle 'none' status as unlit
                    if status == 'none':
                        r, g, b = 0, 0, 0
                    else:
                        # Get hue from user settings and convert to RGB
                        hue = user_settings.get_alert_hue(status)
                        r, g, b = hsv_to_rgb(hue * 360.0, 100, 100)
            else:
                # No history - all unlit
                r, g, b = 0, 0, 0
            
            pixels.append((i, r, g, b))
        
        # Bottom LEDs (10-19): Color of most recent status
        if history_list:
            most_recent = history_list[-1]
            # Handle 'none' status as unlit
            if most_recent == 'none':
                r, g, b = 0, 0, 0
            else:
                hue = user_settings.get_alert_hue(most_recent)
                r, g, b = hsv_to_rgb(hue * 360.0, 100, 100)
        else:
            # No status yet - all off
            r, g, b = 0, 0, 0
        
        for i in range(10, 20):
            pixels.append((i, r, g, b))
        
        # Send to LED controller
        self.led.set_pixels(pixels)
