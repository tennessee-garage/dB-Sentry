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
                alert_status = request.get('status', 'normal')  # 'normal', 'warn', 'alert'
                if alert_status in ['normal', 'warn', 'alert']:
                    self._push_status(alert_status)
                    response = {'status': 'ok', 'command': command, 'alert_status': alert_status}
                else:
                    response = {'status': 'error', 'message': f'Invalid status: {alert_status}'}
            
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
            status: Status string ('normal', 'warn', 'alert')
        """
        self.status_history.append(status)
        self._render_status_history()
    
    def _render_status_history(self):
        """Render the status history to the LED strip.
        
        LED layout:
        - LEDs 0-9 (top row): Status history as FIFO
          - LED 9 = Most recent (First In)
          - LED 0 = Oldest (First Out)
          - Empty slots are unlit
        - LEDs 10-19 (bottom row): All lit with color of most recent status
        
        Colors:
        - Normal = Green (0, 255, 0)
        - Warn = Yellow (255, 255, 0)
        - Alert = Red (255, 0, 0)
        """
        color_map = {
            'normal': (0, 255, 0),    # Green
            'warn': (255, 255, 0),    # Yellow
            'alert': (255, 0, 0)      # Red
        }
        
        pixels = []
        
        # Top LEDs (0-9): Status history FIFO
        # Convert deque to list for indexing
        history_list = list(self.status_history)
        history_len = len(history_list)
        
        for i in range(10):
            if i < history_len:
                # LED 9 is the most recent, LED 0 is oldest
                # So we index from the end of the history
                status = history_list[history_len - 10 + i]
                r, g, b = color_map.get(status, (0, 0, 0))
            else:
                # Empty slot - unlit
                r, g, b = 0, 0, 0
            
            pixels.append((i, r, g, b))
        
        # Bottom LEDs (10-19): Color of most recent status
        if history_list:
            most_recent = history_list[-1]
            r, g, b = color_map.get(most_recent, (0, 0, 0))
        else:
            # No status yet - all off
            r, g, b = 0, 0, 0
        
        for i in range(10, 20):
            pixels.append((i, r, g, b))
        
        # Send to LED controller
        self.led.set_pixels(pixels)
