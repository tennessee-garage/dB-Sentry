"""Dynamic menu system with nested navigation, value editing, and timed refresh.

Extends the static menu system to support:
- Submenu navigation with back actions
- Dynamic content with configurable refresh rates
- Editable numeric values
- Checkbox groups
- System info display
- Display sleep after inactivity
"""

import yaml
import time
import logging
import threading
import subprocess
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Union, Tuple
from PIL import Image, ImageDraw, ImageFont

from .menu import Menu, MenuItem
from .oled_display import OledDisplay
from utils.system_info import (
    get_wifi_ssid,
    get_ip_address,
    get_uptime,
    get_service_status,
    get_load_average
)
from utils.user_settings import user_settings
from utils.color_utils import hsv_to_rgb
from utils.limit_service_api import LimitServiceAPI

logger = logging.getLogger(__name__)


class DynamicMenu:
    """Dynamic menu system with navigation, editing, and auto-refresh."""
    
    INACTIVITY_TIMEOUT = 60  # Seconds before display sleeps
    
    def __init__(self, display: OledDisplay, config_path: Optional[str] = None, led_controller=None, led_ipc_server=None):
        """Initialize dynamic menu system.
        
        Args:
            display: OledDisplay instance
            config_path: Path to menu_config.yaml
            led_controller: Optional LEDController instance for brightness control
            led_ipc_server: Optional LEDIPCServer instance for pausing updates during hue adjustment
        """
        self.display = display
        self.led_controller = led_controller
        self.led_ipc_server = led_ipc_server
        
        # Load menu configuration
        config_file: Path
        if config_path is None:
            config_file = Path(__file__).parent.parent / "config" / "menu_config.yaml"
        else:
            config_file = Path(config_path)
        
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Boot screen state
        self.boot_screen_active: bool = True
        self.boot_check_thread: Optional[threading.Thread] = None
        
        # Navigation state
        self.menu_stack: List[str] = ["main"]  # Stack of menu names
        self.current_menu_name: str = "main"
        
        # Edit mode state
        self.edit_mode: bool = False
        self.edit_value: int = 0
        self.edit_value_float: float = 0.0  # For hue values (0.0-1.0)
        self.edit_config: Dict = {}
        
        # LED state tracking for brightness adjustment
        self.saved_led_state: Dict[str, int] = {}  # Save color when adjusting brightness
        self.showing_rainbow: bool = False
        
        # Refresh thread state
        self.refresh_lock = threading.RLock()  # Use RLock for reentrant locking
        self.refresh_thread: Optional[threading.Thread] = None
        self.stop_refresh = threading.Event()
        self.last_activity = time.time()
        self.display_sleeping = False
        
        # Dynamic content cache
        self.dynamic_values: Dict[str, str] = {}
        self.refresh_timers: Dict[str, float] = {}  # Last refresh time per function
        
        # Limit service API client
        self.limit_api = LimitServiceAPI()
        self.sensor_limits: Dict[str, float] = {}  # Cache of sensor limits
        self.last_sensor_list: List[str] = []  # Track sensor list changes
        
        # Current sensor being edited (for threshold_bar)
        self.editing_sensor: Optional[str] = None
        self.editing_sensor_live_value: float = 0.0  # Live current_reading from API
        self.editing_sensor_last_update: float = 0.0  # Last time live value was fetched
        
        # Sensor details cache (for sensor menu display)
        self.sensor_details_cache: Dict[str, Dict] = {}  # Cache sensor details to avoid polling
        self.sensor_details_cache_time: Dict[str, float] = {}  # Last fetch time per sensor
        
        # AP scan state
        self.scanning_aps: bool = False
        self.scanned_aps: List[Tuple[str, int]] = []

        # Setup mode status cache
        self.setup_mode_status: Optional[bool] = None
        self.setup_mode_status_time: float = 0.0
        self.setup_mode_status_ttl: float = 5.0
        
        # Function registry for dynamic content
        self.function_registry: Dict[str, Callable] = {
            "get_wifi_ssid": get_wifi_ssid,
            "get_ip_address": get_ip_address,
            "get_uptime": get_uptime,
            "get_service_status": get_service_status,
            "get_load_average": get_load_average,
            "get_setup_mode_status": self._get_setup_mode_status,
            "start_setup_mode": self._start_setup_mode,
            "stop_setup_mode": self._stop_setup_mode,
            "get_sensor_count": self._get_sensor_count,
            "set_orientation_left": self._set_orientation_left,
            "set_orientation_right": self._set_orientation_right,
            "set_display_brightness": self._set_display_brightness,
            "set_led_brightness": self._set_led_brightness,
            "set_alert_hue_normal": self._set_alert_hue_normal,
            "set_alert_hue_warn": self._set_alert_hue_warn,
            "set_alert_hue_alert": self._set_alert_hue_alert,
            "restart_now": self._restart_now,
            "shutdown_now": self._shutdown_now,
            "reset_wifi": self._reset_wifi,
        }
        
        # Apply saved user settings on startup
        self._apply_startup_settings()
        
        # Check if limit-service is available, show boot screen if not
        if not self.limit_api.is_available():
            self._show_boot_screen()
            self._start_boot_check_thread()
        else:
            self.boot_screen_active = False
            # Initialize and display first menu
            self.display.scroll_index = 0
            self._refresh_current_menu()
        
        self._start_refresh_thread()
    
    def _apply_startup_settings(self):
        """Apply saved user settings on startup."""
        # Apply display brightness
        brightness = user_settings.get_display_brightness()
        self.display.set_contrast(brightness)
        
        # Apply LED brightness
        if self.led_controller:
            led_brightness = user_settings.get_led_brightness()
            self.led_controller.set_brightness(led_brightness)
        
        # Apply orientation
        orientation = user_settings.get("orientation", "left")
        rotation = 180 if orientation == "left" else 0
        self.display.set_rotation(rotation)
    
    def _show_boot_screen(self):
        """Display boot screen while waiting for services."""
        from PIL import Image, ImageDraw, ImageFont
        
        image = Image.new('1', (self.display.device.width, self.display.device.height), 0)
        draw = ImageDraw.Draw(image)
        
        # Center "Booting up..." text
        text = "Booting up..."
        draw.text((20, 12), text, fill=1)
        
        self.display.device.display(image)
    
    def _start_boot_check_thread(self):
        """Start background thread to poll for API availability."""
        self.boot_check_thread = threading.Thread(target=self._boot_check_loop, daemon=True)
        self.boot_check_thread.start()
    
    def _boot_check_loop(self):
        """Background loop to check when limit-service becomes available."""
        while self.boot_screen_active:
            try:
                if self.limit_api.is_available():
                    logger.info("Limit-service API is now available, loading menu...")
                    self.boot_screen_active = False
                    # Initialize and display first menu
                    with self.refresh_lock:
                        self.display.scroll_index = 0
                        self._refresh_current_menu()
                    break
                else:
                    # Wait before next check
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in boot check loop: {e}")
                time.sleep(1)
    
    def _wake_display(self):
        """Wake display from sleep and reset inactivity timer."""
        self.last_activity = time.time()
        if self.display_sleeping:
            self.display_sleeping = False
            self._refresh_current_menu()
    
    def _check_sleep(self):
        """Check if display should sleep due to inactivity."""
        if time.time() - self.last_activity > self.INACTIVITY_TIMEOUT:
            if not self.display_sleeping:
                self.display_sleeping = True
                self.display.clear()
    
    def _get_dynamic_value(self, function_name: str) -> str:
        """Get value from a dynamic function.
        
        Args:
            function_name: Name of function to call
            
        Returns:
            String value from function
        """
        func = self.function_registry.get(function_name)
        if func:
            try:
                return str(func())
            except Exception as e:
                logger.error(f"Error calling {function_name}: {e}")
                return "Error"
        return "Unknown"
    
    def _should_refresh_item(self, item: Dict) -> bool:
        """Check if item should be refreshed based on its refresh interval.
        
        Args:
            item: Menu item configuration
            
        Returns:
            True if item should be refreshed
        """
        refresh = item.get("refresh", "on_navigate")
        
        if refresh == "on_navigate":
            return False  # Only refresh when navigating to menu
        
        if isinstance(refresh, (int, float)):
            func_name = item.get("function", "")
            last_refresh = self.refresh_timers.get(func_name, 0)
            return (time.time() - last_refresh) >= refresh
        
        return False
    
    def _refresh_dynamic_items(self, menu_items: List[Dict]):
        """Refresh dynamic menu items based on their refresh intervals."""
        for item in menu_items:
            if item.get("type") == "dynamic" and self._should_refresh_item(item):
                func_name = item.get("function")
                if func_name:
                    self.dynamic_values[func_name] = self._get_dynamic_value(func_name)
                    self.refresh_timers[func_name] = time.time()
    
    def _format_menu_text(self, item: Dict) -> MenuItem:
        """Format menu item text with dynamic values.
        
        Args:
            item: Menu item configuration
            
        Returns:
            Formatted text string or dict with text and submenu flag
        """
        text = item.get("text", "")
        item_type = item.get("type", "static")
        
        if item_type in ("dynamic", "dynamic_submenu"):
            func_name = item.get("function")
            if func_name:
                value = self.dynamic_values.get(func_name, self._get_dynamic_value(func_name))
                # Replace any placeholder tokens in text/right_text
                text = re.sub(r"\{[^}]+\}", str(value), text)
        
        elif item_type == "checkbox":
            # Add checkbox indicator
            group = item.get("group")
            value = item.get("value")
            if group and value:
                current = user_settings.get(group, "")
                check = "[x]" if current == value else "[ ]"
                text = text.replace("{orientation_left_check}", check)
                text = text.replace("{orientation_right_check}", check)
        
        elif item_type == "editable":
            # Show current value
            func_name = item.get("function")
            if "display_brightness" in text:
                value = user_settings.get_display_brightness()
                if self.edit_mode and self.edit_config.get("function") == func_name:
                    text = text.replace("{display_brightness}", f"[{self.edit_value}]")
                else:
                    text = text.replace("{display_brightness}", str(value))
            elif "led_brightness" in text:
                value = user_settings.get_led_brightness()
                if self.edit_mode and self.edit_config.get("function") == func_name:
                    text = text.replace("{led_brightness}", f"[{self.edit_value}]")
                else:
                    text = text.replace("{led_brightness}", str(value))
        
        elif item_type == "brightness_bar":
            # Don't show value in menu, just the label
            pass
        
        elif item_type == "sensor_summary":
            # Show sensor count
            sensor_count = self._get_sensor_count()
            text = text.replace("{sensor_count}", str(sensor_count))
        
        # Preserve right-aligned text if present
        right_text = item.get("right_text")
        if item_type in ("dynamic", "dynamic_submenu") and right_text:
            func_name = item.get("function")
            if func_name:
                value = self.dynamic_values.get(func_name, self._get_dynamic_value(func_name))
                right_text = re.sub(r"\{[^}]+\}", str(value), right_text)

        # Return dict with submenu flag for items that lead to special screens
        if item_type in ("submenu", "dynamic_submenu", "threshold_bar", "brightness_bar", "hue_bar", "editable"):
            payload = {"text": text, "submenu": True}
            if right_text:
                payload["right_text"] = right_text
            return payload

        if right_text:
            return {"text": text, "right_text": right_text}
        
        return text
    
    def _create_sensor_menu_config(self, sensor_name: str) -> Dict:
        """Create a dynamic menu configuration for a sensor.
        
        Args:
            sensor_name: Name of the sensor
            
        Returns:
            Menu configuration dictionary
        """
        # Use cached sensor details, don't re-fetch on every refresh
        sensor_details = self.sensor_details_cache.get(sensor_name, {})
        mps = sensor_details.get('measurements_per_second', 0.0)
        
        # Get current limit from cache
        limit = self.sensor_limits.get(sensor_name, 0.0)
        
        return {
            "items": [
                {"text": f"{sensor_name}", "type": "static"},
                {"text": f"Rate: {mps:.1f} mps", "type": "static"},
                {"text": f"Threshold", "type": "threshold_bar", "sensor": sensor_name, "min": 0, "max": 150},
                {"text": "Back", "type": "back"}
            ]
        }

    def _scan_aps(self) -> List[Tuple[str, int]]:
        """Scan for visible WiFi access points.
        
        Returns:
            List of (SSID, signal) tuples sorted by signal desc.
        """
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return []
            entries = []
            for line in result.stdout.splitlines():
                if not line:
                    continue
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                ssid, signal = parts[0].strip(), parts[1].strip()
                if not ssid:
                    ssid = "<hidden>"
                try:
                    signal_val = int(signal)
                except ValueError:
                    signal_val = 0
                entries.append((ssid, signal_val))
            entries.sort(key=lambda item: item[1], reverse=True)
            return entries[:10]
        except Exception as e:
            logger.error(f"Failed to scan APs: {e}")
            return []

    def _reset_wifi(self):
        """Reset WiFi and allow system networking to reconnect using saved priorities."""
        logger.info("Resetting WiFi")

        # Keep this minimal: bounce radio/interface and let system-managed priority order reconnect
        try:
            subprocess.run(["wpa_cli", "-i", "wlan0", "disconnect"], check=False, timeout=3)
            time.sleep(1)
            subprocess.run(["wpa_cli", "-i", "wlan0", "reconfigure"], check=False, timeout=3)
            subprocess.run(["wpa_cli", "-i", "wlan0", "reconnect"], check=False, timeout=3)
        except Exception as e:
            logger.warning(f"wpa_cli WiFi reset failed: {e}")
            try:
                subprocess.run(["nmcli", "radio", "wifi", "off"], check=False, timeout=3)
                time.sleep(1)
                subprocess.run(["nmcli", "radio", "wifi", "on"], check=False, timeout=3)
            except Exception as fallback_error:
                logger.warning(f"nmcli WiFi reset fallback failed: {fallback_error}")

        time.sleep(2)

        # Refresh displayed dynamic values immediately
        self.dynamic_values["get_wifi_ssid"] = get_wifi_ssid()
        self.dynamic_values["get_ip_address"] = get_ip_address()
        self.refresh_timers["get_wifi_ssid"] = time.time()
        self.refresh_timers["get_ip_address"] = time.time()
        self._refresh_current_menu(preserve_position=True)
    
    def _do_ap_scan(self):
        """Background thread method to scan APs and update menu."""
        self.scanned_aps = self._scan_aps()
        self.scanning_aps = False
        # Refresh menu if still on scan_aps page
        if self.current_menu_name == "scan_aps":
            self._refresh_current_menu(preserve_position=True)
    
    def _get_service_status_map(self) -> Dict[str, str]:
        """Get status of all monitored services.
        
        Returns:
            Dict mapping service display name to status string
        """
        services = [
            ("limit", "db-sentry-limit.service"),
            ("interface", "db-sentry-interface.service"),
            ("influxd", "influxd.service"),
            ("mosquitto", "mosquitto.service"),
            ("telegraf", "telegraf.service")
        ]
        
        status_map = {}
        for display_name, service_name in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                status = result.stdout.strip()
                # Map to short status
                if status == "active":
                    status_str = "[up]"
                elif status == "inactive":
                    status_str = "[down]"
                elif status == "failed":
                    status_str = "[fail]"
                else:
                    status_str = status[:4] if status else "?"
                status_map[display_name] = status_str
            except Exception as e:
                logger.debug(f"Failed to check {service_name}: {e}")
                status_map[display_name] = "?"
        
        return status_map
    
    def _create_services_menu_config(self) -> Dict:
        """Create a dynamic menu configuration for services status."""
        status_map = self._get_service_status_map()
        
        items = [
            {"text": name, "type": "static", "right_text": status}
            for name, status in status_map.items()
        ]
        items.append({"text": "Back", "type": "back"})
        return {"items": items}

    def _create_scan_aps_menu_config(self) -> Dict:
        """Create a dynamic menu configuration for WiFi AP scan."""
        def _signal_bars(signal: int) -> str:
            if signal >= 75:
                return "||||"
            if signal >= 50:
                return "|||"
            if signal >= 25:
                return "||"
            if signal > 0:
                return "|"
            return ""

        if self.scanning_aps:
            # Show loading state
            items = [
                {"text": "Scanning ...", "type": "static"},
                {"text": "Back", "type": "back"}
            ]
        else:
            # Show results
            items = [
                {"text": ssid, "type": "static", "right_text": _signal_bars(signal)}
                for ssid, signal in self.scanned_aps
            ]
            items.append({"text": "Back", "type": "back"})
        return {"items": items}

    def _call_setup_service(self, path: str, method: str = "GET") -> Optional[Union[Dict, str]]:
        """Call setup-service API endpoint.

        Args:
            path: API path (e.g., /api/status)
            method: HTTP method

        Returns:
            Parsed JSON dict, raw text, or None on failure
        """
        url = f"http://localhost:5000{path}"
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read().decode("utf-8").strip()
                if not body:
                    return ""
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return body
        except Exception as e:
            logger.error(f"Failed to call setup-service {path}: {e}")
            return None

    def _parse_setup_status_value(self, value: Any) -> Optional[bool]:
        """Parse various status values into a boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("on", "true", "1", "enabled", "running", "active", "started"):
                return True
            if normalized in ("off", "false", "0", "disabled", "stopped", "inactive"):
                return False
        return None

    def _fetch_setup_mode_status(self, force: bool = False) -> Optional[bool]:
        """Fetch setup mode status from setup-service with simple caching."""
        now = time.time()
        if not force and self.setup_mode_status_time and (now - self.setup_mode_status_time) < self.setup_mode_status_ttl:
            return self.setup_mode_status

        data = self._call_setup_service("/api/status", method="GET")
        status: Optional[bool] = None

        if isinstance(data, dict):
            for key in ("ap_mode", "setup_mode", "enabled", "active", "running", "ap_running", "apMode", "ap_enabled", "status"):
                if key in data:
                    status = self._parse_setup_status_value(data.get(key))
                    if status is not None:
                        break
        elif isinstance(data, str):
            status = self._parse_setup_status_value(data)

        self.setup_mode_status = status
        self.setup_mode_status_time = now
        return status

    def _get_setup_mode_status(self) -> str:
        """Get setup mode status as 'on'/'off'/'?' for display."""
        status = self._fetch_setup_mode_status(force=False)
        if status is True:
            return "on"
        if status is False:
            return "off"
        return "?"

    def _set_setup_mode(self, enable: bool) -> None:
        """Start or stop setup mode via setup-service."""
        path = "/api/start-ap" if enable else "/api/stop-ap"
        response = self._call_setup_service(path, method="POST")
        if response is None:
            # Try GET as fallback
            response = self._call_setup_service(path, method="GET")

        if response is not None:
            self.setup_mode_status = enable
            self.setup_mode_status_time = time.time()
            self.dynamic_values["get_setup_mode_status"] = "on" if enable else "off"
        else:
            logger.error("Setup mode change failed.")

        # Return to previous menu after action
        self._navigate_back()

    def _start_setup_mode(self) -> None:
        """Enable setup mode."""
        self._set_setup_mode(True)

    def _stop_setup_mode(self) -> None:
        """Disable setup mode."""
        self._set_setup_mode(False)

    def _create_setup_mode_confirm_menu_config(self) -> Dict:
        """Create confirmation menu for toggling setup mode."""
        status = self.setup_mode_status
        if status is None:
            cached_value = self.dynamic_values.get("get_setup_mode_status")
            status = True if cached_value == "on" else False if cached_value == "off" else None

        if status is True:
            prompt = "Turn off setup mode?"
            action_func = "stop_setup_mode"
        else:
            prompt = "Turn on setup mode?"
            action_func = "start_setup_mode"

        items = [
            {"text": prompt, "type": "static"},
            {"text": "[no]", "type": "back"},
            {"text": "[yes]", "type": "action", "function": action_func}
        ]
        return {"items": items}
    
    def _get_current_menu_config(self) -> Dict:
        """Get configuration for current menu.
        
        Returns:
            Menu configuration dictionary
        """
        # Check if this is a dynamic sensor submenu
        if self.current_menu_name.startswith("sensor_"):
            sensor_name = self.current_menu_name.removeprefix("sensor_")
            return self._create_sensor_menu_config(sensor_name)

        # Check if this is the AP scan submenu
        if self.current_menu_name == "scan_aps":
            return self._create_scan_aps_menu_config()
        
        # Check if this is the services submenu
        if self.current_menu_name == "services":
            return self._create_services_menu_config()

        # Check if this is the setup mode confirm submenu
        if self.current_menu_name == "setup_mode_confirm":
            return self._create_setup_mode_confirm_menu_config()
        
        return self.config["menus"].get(self.current_menu_name, {})
    
    def _refresh_current_menu(self, preserve_position: bool = False):
        """Refresh and display the current menu.
        
        Args:
            preserve_position: If True, keep current scroll/cursor position
        """
        with self.refresh_lock:
            if self.display_sleeping:
                return
            
            menu_config = self._get_current_menu_config()
            items = menu_config.get("items", [])
            
            # Save current position if preserving, but reset if we're on sensors menu
            # (sensors list can change dynamically)
            saved_scroll = self.display.scroll_index if preserve_position else 0
            if self.current_menu_name == "main" and preserve_position:
                # Check if sensor list size changed
                has_sensor_summary = any(item.get("type") == "sensor_summary" for item in items)
                if has_sensor_summary:
                    saved_scroll = 0  # Reset scroll when sensors might have changed
            
            # Expand sensor_summary items into actual sensor list
            expanded_items = []
            for item in items:
                if item.get("type") == "sensor_summary":
                    # Fetch active sensors and current limits from API
                    sensors = self.limit_api.get_sensors()
                    self.sensor_limits = self.limit_api.get_limits()
                    
                    # Only show sensors that are actually active
                    active_sensor_names = sensors if sensors else []
                    
                    # Check if sensor list changed - if so, reset scroll position
                    if active_sensor_names != self.last_sensor_list:
                        self.last_sensor_list = active_sensor_names
                        saved_scroll = 0  # Reset on sensor change
                    
                    # Add the summary line
                    expanded_items.append(item)
                    # Add individual sensor lines as clickable submenus (only active ones)
                    for sensor_name in sorted(active_sensor_names):
                        sensor_item = {
                            "text": sensor_name,
                            "type": "submenu",
                            "submenu": f"sensor_{sensor_name}"  # Dynamic submenu name
                        }
                        expanded_items.append(sensor_item)
                else:
                    expanded_items.append(item)
            
            # Refresh dynamic items on navigate
            for item in expanded_items:
                if item.get("type") in ("dynamic", "dynamic_submenu"):
                    func_name = item.get("function")
                    if func_name:
                        self.dynamic_values[func_name] = self._get_dynamic_value(func_name)
                        self.refresh_timers[func_name] = time.time()
            
            # Format menu text
            menu_texts: List[MenuItem] = [self._format_menu_text(item) for item in expanded_items]
            
            # Create static Menu for display
            menu = Menu(menu_texts)
            
            # Set menu and position, then display once
            self.display.current_menu = menu
            if preserve_position:
                self.display.scroll_index = saved_scroll
            else:
                self.display.scroll_index = 0
            
            # Display the menu at the correct position
            self.display._display_current_menu()
    
    def _start_refresh_thread(self):
        """Start background thread for timed menu refreshes."""
        self.stop_refresh.clear()
        self.refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self.refresh_thread.start()
    
    def _refresh_loop(self):
        """Background loop for refreshing dynamic menu items."""
        while not self.stop_refresh.is_set():
            try:
                # Check for display sleep
                self._check_sleep()
                
                if not self.display_sleeping and not self.edit_mode:
                    menu_config = self._get_current_menu_config()
                    items = menu_config.get("items", [])
                    
                    # Check which items need refresh
                    needs_refresh = False
                    for item in items:
                        if item.get("type") in ("dynamic", "dynamic_submenu") and self._should_refresh_item(item):
                            func_name = item.get("function")
                            if func_name:
                                self.dynamic_values[func_name] = self._get_dynamic_value(func_name)
                                self.refresh_timers[func_name] = time.time()
                                needs_refresh = True
                    
                    # Refresh display if any items changed
                    if needs_refresh:
                        self._refresh_current_menu(preserve_position=True)
                
                # Sleep briefly to avoid busy-waiting
                time.sleep(0.1)
            
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
    
    def stop(self):
        """Stop the dynamic menu system and background threads."""
        self.boot_screen_active = False
        self.stop_refresh.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=2)
        if self.boot_check_thread:
            self.boot_check_thread.join(timeout=2)
    
    # Navigation methods
    
    def move_cursor_down(self):
        """Move cursor down."""
        self._wake_display()
        if self.boot_screen_active or self.edit_mode:
            return
        with self.refresh_lock:
            self.display.move_cursor_down()
    
    def move_cursor_up(self):
        """Move cursor up."""
        self._wake_display()
        if self.boot_screen_active or self.edit_mode:
            return
        with self.refresh_lock:
            self.display.move_cursor_up()
    
    def encoder_rotated(self, delta: int):
        """Handle encoder rotation.
        
        Args:
            delta: Rotation delta (+/- for direction)
        """
        self._wake_display()
        
        if self.boot_screen_active:
            return
        
        if self.edit_mode:
            # Calculate step size based on bar width for brightness_bar mode
            if self.edit_config.get("type") == "brightness_bar":
                # Make each encoder step = 1 pixel change on the bar
                bar_width = 110  # Must match _render_brightness_bar
                min_val = self.edit_config.get("min", 0)
                max_val = self.edit_config.get("max", 255)
                step = (max_val - min_val) / bar_width  # Each step = 1 pixel
                
                old_value = self.edit_value
                self.edit_value += (step if delta < 0 else -step)
                
                # Clamp to min/max
                self.edit_value = max(
                    self.edit_config.get("min", 0),
                    min(self.edit_config.get("max", 255), self.edit_value)
                )
                # Round to nearest integer for brightness values
                self.edit_value = int(round(self.edit_value))
                
                # Apply display brightness in real-time for immediate feedback
                func_name = self.edit_config.get("function", "")
                if "display_brightness" in func_name:
                    # Remap 0-255 to 5-255 for actual hardware effective range
                    # The SSD1306 doesn't get much dimmer below ~5
                    hardware_contrast = int(5 + (self.edit_value / 255.0) * (255 - 5))
                    self.display.set_contrast(hardware_contrast)
                elif "led_brightness" in func_name and self.showing_rainbow:
                    # Apply LED brightness in real-time for rainbow pattern
                    if self.led_controller:
                        self.led_controller.set_brightness(self.edit_value)
                
                # Refresh display
                self._render_brightness_bar()
            
            elif self.edit_config.get("type") == "hue_bar":
                # Hue bar mode - adjust hue value (0.0-1.0)
                bar_width = 110  # Must match _render_hue_bar
                step = 1.0 / bar_width  # Each step = 1 pixel
                
                self.edit_value_float += (step if delta < 0 else -step)
                
                # Clamp to 0.0-1.0
                self.edit_value_float = max(0.0, min(1.0, self.edit_value_float))
                
                # Show hue on LEDs in real-time
                if self.led_controller:
                    r, g, b = hsv_to_rgb(self.edit_value_float * 360.0, 100, 100)
                    self.led_controller.set_color(r, g, b)
                
                # Refresh display
                self._render_hue_bar()
            
            elif self.edit_config.get("type") == "threshold_bar":
                # Threshold bar mode - adjust threshold value (0-150)
                bar_width = 110  # Must match _render_threshold_bar
                min_val = self.edit_config.get("min", 0)
                max_val = self.edit_config.get("max", 150)
                step = (max_val - min_val) / bar_width  # Each step = 1 pixel
                
                self.edit_value += (step if delta < 0 else -step)
                
                # Clamp to min/max
                self.edit_value = max(min_val, min(max_val, self.edit_value))
                # Round to nearest integer
                self.edit_value = int(round(self.edit_value))
                
                # Refresh display
                self._render_threshold_bar()
            
            else:
                # Standard edit mode uses smaller steps
                step = 1 if abs(delta) == 1 else 5
                
                old_value = self.edit_value
                self.edit_value += (step if delta < 0 else -step)
                
                # Clamp to min/max
                self.edit_value = max(
                    self.edit_config.get("min", 0),
                    min(self.edit_config.get("max", 255), self.edit_value)
                )
                # Round to nearest integer for brightness values
                self.edit_value = int(round(self.edit_value))
                
                with self.refresh_lock:
                    self._refresh_current_menu()
        else:
            # Normal navigation
            if delta > 0:
                self.move_cursor_up()
            else:
                self.move_cursor_down()
    
    def button_pressed(self):
        """Handle encoder button press."""
        was_sleeping = self.display_sleeping
        self._wake_display()

        # If the display was asleep, consume this press as wake-only
        if was_sleeping:
            return
        
        if self.display_sleeping or self.boot_screen_active:
            return
        
        if self.edit_mode:
            # Save and exit edit mode
            self._save_edit_value()
            self.edit_mode = False
            self._refresh_current_menu()
            return
        
        # Get selected item - must reconstruct expanded items like in _refresh_current_menu
        menu_config = self._get_current_menu_config()
        items = menu_config.get("items", [])
        
        # Expand sensor_summary items into actual sensor list (same as _refresh_current_menu)
        expanded_items = []
        for item in items:
            if item.get("type") == "sensor_summary":
                # Fetch current active sensors from API
                sensors = self.limit_api.get_sensors()
                self.sensor_limits = self.limit_api.get_limits()
                
                # Only show sensors that are actually active
                active_sensor_names = sensors if sensors else []
                
                # Check if sensor list changed
                if active_sensor_names != self.last_sensor_list:
                    self.last_sensor_list = active_sensor_names
                    logger.info(f"Sensor list changed to: {active_sensor_names}")
                
                # Add the summary line
                expanded_items.append(item)
                # Add individual sensor lines as clickable submenus (only active ones)
                for sensor_name in sorted(active_sensor_names):
                    sensor_item = {
                        "text": sensor_name,
                        "type": "submenu",
                        "submenu": f"sensor_{sensor_name}"  # Dynamic submenu name
                    }
                    expanded_items.append(sensor_item)
            else:
                expanded_items.append(item)
        
        selected_index = self.display.get_selected_item_index()
        logger.info(f"Button pressed: menu={self.current_menu_name}, selected_index={selected_index}, total_items={len(expanded_items)}")
        
        if selected_index >= len(expanded_items):
            logger.warning(f"Selected index {selected_index} >= items count {len(expanded_items)}, ignoring")
            return
        
        item = expanded_items[selected_index]
        item_type = item.get("type", "static")
        logger.info(f"Selected item type: {item_type}, text: {item.get('text', '')}")
        
        if item_type == "back":
            self._navigate_back()
        elif item_type in ("submenu", "dynamic_submenu"):
            submenu_name = item.get("submenu")
            if submenu_name:
                self._navigate_to(submenu_name)
        elif item_type == "checkbox":
            self._handle_checkbox(item)
        elif item_type == "editable":
            self._enter_edit_mode(item)
        elif item_type == "brightness_bar":
            self._enter_brightness_bar_mode(item)
        elif item_type == "hue_bar":
            self._enter_hue_bar_mode(item)
        elif item_type == "threshold_bar":
            self._enter_threshold_bar_mode(item)
        elif item_type == "action":
            self._handle_action(item)
    
    def _navigate_to(self, menu_name: str):
        """Navigate to a submenu.
        
        Args:
            menu_name: Name of menu to navigate to
        """
        self.menu_stack.append(menu_name)
        self.current_menu_name = menu_name
        # Reset display position when entering a new menu
        self.display.scroll_index = 0
        
        # Fetch sensor details once when entering a sensor menu
        if menu_name.startswith("sensor_"):
            sensor_name = menu_name.removeprefix("sensor_")
            sensor_details = self.limit_api.get_sensor_details(sensor_name)
            if sensor_details:
                self.sensor_details_cache[sensor_name] = sensor_details
                logger.info(f"Cached sensor details for {sensor_name}: {sensor_details}")
        
        # Start async AP scan if navigating to scan_aps
        if menu_name == "scan_aps":
            self.scanning_aps = True
            self.scanned_aps = []
            self._refresh_current_menu()  # Show loading state
            # Start scan in background thread
            threading.Thread(target=self._do_ap_scan, daemon=True).start()
        else:
            self._refresh_current_menu()
    
    def _navigate_back(self):
        """Navigate back to previous menu."""
        if len(self.menu_stack) > 1:
            self.menu_stack.pop()
            self.current_menu_name = self.menu_stack[-1]
            # Reset display position when going back
            self.display.scroll_index = 0
            self._refresh_current_menu()
    
    def _handle_checkbox(self, item: Dict):
        """Handle checkbox item selection.
        
        Args:
            item: Checkbox item configuration
        """
        func_name = item.get("function")
        if func_name:
            func = self.function_registry.get(func_name)
            if func:
                func()
                self._refresh_current_menu()
    
    def _enter_edit_mode(self, item: Dict):
        """Enter edit mode for editable item.
        
        Args:
            item: Editable item configuration
        """
        self.edit_mode = True
        self.edit_config = item
        
        # Get current value
        func_name = item.get("function", "")
        if not func_name:
            # if this isn't recongized just use min as default
            self.edit_value = item.get("min", 0)
            return

        if "display_brightness" in func_name:
            self.edit_value = user_settings.get_display_brightness()
        elif "led_brightness" in func_name:
            self.edit_value = user_settings.get_led_brightness()
        else:
            self.edit_value = item.get("min", 0)
        
        self._refresh_current_menu()
    
    def _enter_brightness_bar_mode(self, item: Dict):
        """Enter brightness bar mode for visual brightness adjustment.
        
        Args:
            item: Brightness bar item configuration
        """
        self.edit_mode = True
        self.edit_config = item
        
        # Get current value
        func_name = item.get("function", "")
        if "display_brightness" in func_name:
            self.edit_value = user_settings.get_display_brightness()
        elif "led_brightness" in func_name:
            self.edit_value = user_settings.get_led_brightness()
            # Save current LED state and show rainbow pattern
            if self.led_controller:
                self.saved_led_state = {
                    "brightness": self.led_controller.get_brightness()
                }
                self._show_rainbow_pattern()
                self.showing_rainbow = True
        else:
            self.edit_value = item.get("min", 0)
        
        # Render the brightness bar interface
        self._render_brightness_bar()
    
    def _show_rainbow_pattern(self):
        """Show a rainbow pattern across the LED strip."""
        if not self.led_controller:
            return
        
        try:
            # Create rainbow colors across the strip
            num_pixels = self.led_controller.count
            for i in range(num_pixels):
                # Calculate hue for rainbow (0-360 degrees)
                hue = (i / num_pixels) * 360
                # Convert HSV to RGB
                r, g, b = hsv_to_rgb(hue, 100, 100)
                
                # Set pixel color (use low-level access if available)
                if hasattr(self.led_controller, 'strip') and self.led_controller.strip:
                    if hasattr(self.led_controller.strip, 'setPixelColor'):
                        try:
                            self.led_controller.strip.setPixelColor(
                                i, 
                                self.led_controller.Color(r, g, b)
                            )
                        except Exception:
                            pass
                    # Show the pixels
                    if hasattr(self.led_controller.strip, 'show'):
                        try:
                            self.led_controller.strip.show()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Error showing rainbow pattern: {e}")
    
    def _render_brightness_bar(self):
        """Render the brightness bar interface."""
        # Create image
        image = Image.new('1', (self.display.device.width, self.display.device.height), 0)
        draw = ImageDraw.Draw(image)
        
        # Line 1: "Brightness"
        draw.text((4, 4), "Brightness", fill=1)
        
        # Line 2: Bar showing current level
        bar_x = 4
        bar_y = 20
        bar_width = 110  # Width of bar
        bar_height = 8
        
        # Calculate fill based on current value
        min_val = self.edit_config.get("min", 0)
        max_val = self.edit_config.get("max", 255)
        percentage = (self.edit_value - min_val) / (max_val - min_val) if max_val > min_val else 0
        fill_width = int(bar_width * percentage)
        
        # Draw bar outline
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], outline=1, fill=0)
        
        # Draw filled portion (only if there's room for a visible rectangle)
        if fill_width > 1:
            draw.rectangle([(bar_x + 1, bar_y + 1), (bar_x + fill_width, bar_y + bar_height - 1)], fill=1)
        
        # Display the image (device handles rotation automatically)
        self.display.device.display(image)
    
    def _render_hue_bar(self):
        """Render the hue bar interface for alert color selection."""
        # Create image
        image = Image.new('1', (self.display.device.width, self.display.device.height), 0)
        draw = ImageDraw.Draw(image)
        
        # Line 1: Hue bar with cursor
        bar_x = 4
        bar_y = 4
        bar_width = 110
        bar_height = 8
        
        # Calculate cursor position based on hue value (0.0-1.0)
        cursor_pos = int(bar_x + bar_width * self.edit_value_float)
        
        # Draw bar outline
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], outline=1, fill=0)
        
        # Draw cursor (a small vertical line)
        cursor_width = 2
        draw.rectangle([(cursor_pos - 1, bar_y - 1), (cursor_pos + 1, bar_y + bar_height + 1)], outline=1, fill=0)
        
        # Line 2: Labels and value
        # Left label (0), right label (1), and current value
        draw.text((4, 20), "0", fill=1)
        draw.text((110, 20), "1", fill=1)
        value_str = f"{self.edit_value_float:.2f}"
        draw.text((55, 20), value_str, fill=1)
        
        # Display the image
        self.display.device.display(image)
    
    def _render_threshold_bar(self):
        """Render the threshold bar interface for sensor limit adjustment."""
        # Update live sensor reading every second
        current_time = time.time()
        if current_time - self.editing_sensor_last_update >= 1.0:
            if self.editing_sensor:
                sensor_details = self.limit_api.get_sensor_details(self.editing_sensor)
                if sensor_details:
                    self.editing_sensor_live_value = sensor_details.get('current_reading', 0.0)
                    # Also update the cache so mps is fresh when exiting threshold mode
                    self.sensor_details_cache[self.editing_sensor] = sensor_details
                self.editing_sensor_last_update = current_time
        
        # Create image
        image = Image.new('1', (self.display.device.width, self.display.device.height), 0)
        draw = ImageDraw.Draw(image)
        
        # Line 1: Threshold bar with cursor
        bar_x = 4
        bar_y = 4
        bar_width = 110
        bar_height = 8
        
        min_val = self.edit_config.get("min", 0)
        max_val = self.edit_config.get("max", 150)
        
        # Calculate cursor position based on threshold value
        value_range = max_val - min_val
        cursor_pos = int(bar_x + bar_width * ((self.edit_value - min_val) / value_range))
        
        # Draw bar outline
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)], outline=1, fill=0)
        
        # Draw cursor (a small vertical line)
        draw.rectangle([(cursor_pos - 1, bar_y - 1), (cursor_pos + 1, bar_y + bar_height + 1)], outline=1, fill=0)
        
        # Line 2: Limit and Live values
        live_rounded = int(round(self.editing_sensor_live_value))
        value_str = f"Limit: {self.edit_value}  |  Live: {live_rounded}"
        draw.text((4, 20), value_str, fill=1)
        
        # Display the image
        self.display.device.display(image)
    
    def _enter_hue_bar_mode(self, item: Dict):
        """Enter hue bar mode for alert color selection.
        
        Args:
            item: Hue bar item configuration
        """
        # Pause LED IPC updates while adjusting colors
        if self.led_ipc_server:
            self.led_ipc_server.pause_updates = True
        
        self.edit_mode = True
        self.edit_config = item
        
        # Get current hue value
        alert_type = item.get("alert_type", "normal")
        self.edit_value_float = user_settings.get_alert_hue(alert_type)
        
        # Show current hue color on LEDs immediately
        if self.led_controller:
            r, g, b = hsv_to_rgb(self.edit_value_float * 360.0, 100, 100)
            self.led_controller.set_color(r, g, b)
        
        # Render the hue bar interface
        self._render_hue_bar()
    
    def _enter_threshold_bar_mode(self, item: Dict):
        """Enter threshold bar mode for sensor limit adjustment.
        
        Args:
            item: Threshold bar item configuration
        """
        self.edit_mode = True
        self.edit_config = item
        
        # Store which sensor we're editing
        self.editing_sensor = item.get("sensor")
        
        # Get current threshold value
        if self.editing_sensor:
            self.edit_value = int(self.sensor_limits.get(self.editing_sensor, 0))
            # Initialize live value
            sensor_details = self.limit_api.get_sensor_details(self.editing_sensor)
            if sensor_details:
                self.editing_sensor_live_value = sensor_details.get('current_reading', 0.0)
            else:
                self.editing_sensor_live_value = 0.0
            self.editing_sensor_last_update = time.time()
        else:
            self.edit_value = 0
            self.editing_sensor_live_value = 0.0
            self.editing_sensor_last_update = 0.0
        
        # Render the threshold bar interface
        self._render_threshold_bar()
    
    def _save_edit_value(self):
        """Save the edited value."""
        if self.edit_config.get("type") == "hue_bar":
            # Hue bar mode - save float value
            alert_type = self.edit_config.get("alert_type", "normal")
            func_name = self.edit_config.get("function")
            if func_name:
                func = self.function_registry.get(func_name)
                if func:
                    func(self.edit_value_float)
            
            # Resume LED IPC updates
            if self.led_ipc_server:
                self.led_ipc_server.pause_updates = False
                # Render status history once to restore display
                self.led_ipc_server._render_status_history()
        
        elif self.edit_config.get("type") == "threshold_bar":
            # Threshold bar mode - update sensor limit via API
            if self.editing_sensor:
                success = self.limit_api.update_limit(self.editing_sensor, float(self.edit_value))
                if success:
                    # Update local cache
                    self.sensor_limits[self.editing_sensor] = float(self.edit_value)
                    logger.info(f"Updated {self.editing_sensor} limit to {self.edit_value}")
                else:
                    logger.error(f"Failed to update {self.editing_sensor} limit")
            self.editing_sensor = None
        
        else:
            # Regular edit mode or brightness bar - save integer value
            func_name = self.edit_config.get("function")
            if func_name:
                func = self.function_registry.get(func_name)
                if func:
                    func(self.edit_value)
        
        # Clear rainbow pattern and restore LED state after adjustment
        if self.showing_rainbow and self.led_controller:
            self.showing_rainbow = False
            # Clear the LEDs to return to previous state (off)
            try:
                self.led_controller.clear()
            except Exception as e:
                logger.error(f"Error clearing LEDs: {e}")
            self.saved_led_state = {}
    
    def _handle_action(self, item: Dict):
        """Handle action item.
        
        Args:
            item: Action item configuration
        """
        func_name = item.get("function")
        if func_name:
            func = self.function_registry.get(func_name)
            if func:
                func()
    
    # Settings action handlers
    
    def _set_orientation_left(self):
        """Set orientation to knob on left."""
        user_settings.set_orientation("left")
        self.display.set_rotation(180)
    
    def _set_orientation_right(self):
        """Set orientation to knob on right."""
        user_settings.set_orientation("right")
        self.display.set_rotation(0)
    
    def _set_display_brightness(self, value: int):
        """Set display brightness.
        
        Args:
            value: Brightness level (0-255)
        """
        user_settings.set_display_brightness(value)
        self.display.set_contrast(value)
    
    def _set_led_brightness(self, value: int):
        """Set LED brightness.
        
        Args:
            value: Brightness level (0-255)
        """
        user_settings.set_led_brightness(value)
        if self.led_controller:
            self.led_controller.set_brightness(value)
    
    def _set_alert_hue_normal(self, value: float):
        """Set hue for normal alert status."""
        user_settings.set_alert_hue("normal", value)
    
    def _set_alert_hue_warn(self, value: float):
        """Set hue for warn alert status."""
        user_settings.set_alert_hue("warn", value)
    
    def _set_alert_hue_alert(self, value: float):
        """Set hue for alert alert status."""
        user_settings.set_alert_hue("alert", value)
    
    def _get_sensor_count(self) -> int:
        """Get count of active sensors.
        
        Returns:
            Number of active sensors
        """
        sensors = self.limit_api.get_sensors()
        return len(sensors)
    
    def _shutdown_now(self):
        """Shutdown the system immediately."""
        try:
            logger.info("Shutting down system now...")
            subprocess.run(["sudo", "shutdown", "now"], check=False)
        except Exception as e:
            logger.error(f"Failed to shutdown: {e}")

    def _restart_now(self):
        """Restart the system immediately."""
        try:
            logger.info("Restarting system now...")
            subprocess.run(["sudo", "shutdown", "-r", "now"], check=False)
        except Exception as e:
            logger.error(f"Failed to restart: {e}")
