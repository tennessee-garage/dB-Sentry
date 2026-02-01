"""Client for remote LED control via IPC.

Used by limit-service to control LEDs managed by interface-service.
"""

import json
import logging
import socket
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class RemoteLEDClient:
    """Client for controlling LEDs on a remote interface-service via Unix socket."""
    
    DEFAULT_SOCKET_PATH = "/tmp/db-sentry-led-control.sock"
    
    def __init__(self, socket_path: Optional[str] = None):
        """Initialize the remote LED client.
        
        Args:
            socket_path: Path to the LED IPC socket (default: /tmp/db-sentry-led-control.sock)
        """
        self.socket_path = socket_path or self.DEFAULT_SOCKET_PATH
    
    def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command to the LED server.
        
        Args:
            command: Command dictionary to send
            
        Returns:
            Response dictionary from server
            
        Raises:
            ConnectionError: If unable to connect to server
            json.JSONDecodeError: If response is invalid JSON
        """
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            sock.send(json.dumps(command).encode('utf-8'))
            
            response_data = sock.recv(1024).decode('utf-8')
            response = json.loads(response_data)
            
            sock.close()
            return response
        
        except FileNotFoundError:
            raise ConnectionError(f"LED IPC socket not found at {self.socket_path}. Is interface-service running?")
        except ConnectionRefusedError:
            raise ConnectionError(f"Failed to connect to LED server at {self.socket_path}")
        except Exception as e:
            raise ConnectionError(f"Error communicating with LED server: {e}")
    
    def set_color(self, r: int, g: int, b: int) -> bool:
        """Set the LED strip to a solid color.
        
        Args:
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self._send_command({
                'command': 'set_color',
                'r': max(0, min(255, r)),
                'g': max(0, min(255, g)),
                'b': max(0, min(255, b))
            })
            return response.get('status') == 'ok'
        except ConnectionError as e:
            logger.error(f"LED set_color failed: {e}")
            return False
    
    def show_alert(self, level: str = 'warning') -> bool:
        """Show an alert on the LED strip.
        
        Args:
            level: Alert level - 'info' (green), 'warning' (yellow), 'critical' (red)
            
        Returns:
            True if successful, False otherwise
        """
        if level not in ['info', 'warning', 'critical']:
            logger.warning(f"Invalid alert level: {level}, using 'warning'")
            level = 'warning'
        
        try:
            response = self._send_command({
                'command': 'alert',
                'level': level
            })
            return response.get('status') == 'ok'
        except ConnectionError as e:
            logger.error(f"LED show_alert failed: {e}")
            return False
    
    def clear(self) -> bool:
        """Turn off all LEDs.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self._send_command({'command': 'clear'})
            return response.get('status') == 'ok'
        except ConnectionError as e:
            logger.error(f"LED clear failed: {e}")
            return False
    
    def push_alert_status(self, status: str) -> bool:
        """Push an alert status to the status history FIFO.
        
        The status is added to a 10-entry FIFO queue and visualized on the LEDs:
        - Top 10 LEDs show the status history (oldest on left, newest on right)
        - Bottom 10 LEDs all show the color of the most recent status
        
        Args:
            status: Alert status - 'normal' (green), 'warn' (yellow), 'alert' (red), 'none' (unlit)
            
        Returns:
            True if successful, False otherwise
        """
        if status not in ['normal', 'warn', 'alert', 'none']:
            logger.warning(f"Invalid alert status: {status}, using 'none'")
            status = 'none'
        
        try:
            response = self._send_command({
                'command': 'push_status',
                'status': status
            })
            return response.get('status') == 'ok'
        except ConnectionError as e:
            logger.error(f"LED push_alert_status failed: {e}")
            return False
    
    def update_sensors(self, sensors: dict) -> bool:
        """Update the active sensor list with measurements per second.
        
        Args:
            sensors: Dictionary mapping sensor_name (str) to measurements_per_second (float)
                    Example: {'temperature': 10.5, 'pressure': 5.2}
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = self._send_command({
                'command': 'update_sensors',
                'sensors': sensors
            })
            return response.get('status') == 'ok'
        except ConnectionError as e:
            logger.error(f"LED update_sensors failed: {e}")
            return False
