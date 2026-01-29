"""IPC server for LED control.

Allows other services (like limit-service) to control LEDs via Unix socket.
"""

import json
import logging
import os
import socket
import threading
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
