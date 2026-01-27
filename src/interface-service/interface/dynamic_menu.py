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
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Union, cast
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

logger = logging.getLogger(__name__)


class DynamicMenu:
    """Dynamic menu system with navigation, editing, and auto-refresh."""
    
    INACTIVITY_TIMEOUT = 60  # Seconds before display sleeps
    
    def __init__(self, display: OledDisplay, config_path: Optional[str] = None, led_controller=None):
        """Initialize dynamic menu system.
        
        Args:
            display: OledDisplay instance
            config_path: Path to menu_config.yaml
            led_controller: Optional LEDController instance for brightness control
        """
        self.display = display
        self.led_controller = led_controller
        
        # Load menu configuration
        config_file: Path
        if config_path is None:
            config_file = Path(__file__).parent.parent / "config" / "menu_config.yaml"
        else:
            config_file = Path(config_path)
        
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Navigation state
        self.menu_stack: List[str] = ["main"]  # Stack of menu names
        self.current_menu_name: str = "main"
        
        # Edit mode state
        self.edit_mode: bool = False
        self.edit_value: int = 0
        self.edit_config: Dict = {}
        
        # Refresh thread state
        self.refresh_lock = threading.Lock()
        self.refresh_thread: Optional[threading.Thread] = None
        self.stop_refresh = threading.Event()
        self.last_activity = time.time()
        self.display_sleeping = False
        
        # Dynamic content cache
        self.dynamic_values: Dict[str, str] = {}
        self.refresh_timers: Dict[str, float] = {}  # Last refresh time per function
        
        # Function registry for dynamic content
        self.function_registry: Dict[str, Callable] = {
            "get_wifi_ssid": get_wifi_ssid,
            "get_ip_address": get_ip_address,
            "get_uptime": get_uptime,
            "get_service_status": get_service_status,
            "get_load_average": get_load_average,
            "set_orientation_left": self._set_orientation_left,
            "set_orientation_right": self._set_orientation_right,
            "set_display_brightness": self._set_display_brightness,
            "set_led_brightness": self._set_led_brightness,
        }
        
        # Initialize and display first menu
        self.display.scroll_index = 0
        self.display.cursor_position = 0
        self._refresh_current_menu()
        self._start_refresh_thread()
    
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
    
    def _format_menu_text(self, item: Dict) -> str:
        """Format menu item text with dynamic values.
        
        Args:
            item: Menu item configuration
            
        Returns:
            Formatted text string
        """
        text = item.get("text", "")
        item_type = item.get("type", "static")
        
        if item_type == "dynamic":
            func_name = item.get("function")
            if func_name:
                value = self.dynamic_values.get(func_name, self._get_dynamic_value(func_name))
                # Replace placeholder in text
                for key in ["{wifi_ssid}", "{ip_address}", "{uptime}", "{service_status}", "{load_average}"]:
                    text = text.replace(key, value)
        
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
        
        return text
    
    def _get_current_menu_config(self) -> Dict:
        """Get configuration for current menu.
        
        Returns:
            Menu configuration dictionary
        """
        return self.config["menus"].get(self.current_menu_name, {})
    
    def _refresh_current_menu(self):
        """Refresh and display the current menu."""
        with self.refresh_lock:
            if self.display_sleeping:
                return
            
            menu_config = self._get_current_menu_config()
            items = menu_config.get("items", [])
            
            # Refresh dynamic items on navigate
            for item in items:
                if item.get("type") == "dynamic":
                    func_name = item.get("function")
                    if func_name:
                        self.dynamic_values[func_name] = self._get_dynamic_value(func_name)
                        self.refresh_timers[func_name] = time.time()
            
            # Format menu text
            menu_texts: List[MenuItem] = [self._format_menu_text(item) for item in items]
            
            # Create static Menu for display
            menu = Menu(menu_texts)
            self.display.load_menu(menu)
    
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
                        if item.get("type") == "dynamic" and self._should_refresh_item(item):
                            func_name = item.get("function")
                            if func_name:
                                self.dynamic_values[func_name] = self._get_dynamic_value(func_name)
                                self.refresh_timers[func_name] = time.time()
                                needs_refresh = True
                    
                    # Refresh display if any items changed
                    if needs_refresh:
                        with self.refresh_lock:
                            self._refresh_current_menu()
                
                # Sleep briefly to avoid busy-waiting
                time.sleep(0.1)
            
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
    
    def stop(self):
        """Stop the dynamic menu system and background threads."""
        self.stop_refresh.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=2)
    
    # Navigation methods
    
    def move_cursor_down(self):
        """Move cursor down."""
        self._wake_display()
        if not self.edit_mode:
            self.display.move_cursor_down()
    
    def move_cursor_up(self):
        """Move cursor up."""
        self._wake_display()
        if not self.edit_mode:
            self.display.move_cursor_up()
    
    def encoder_rotated(self, delta: int):
        """Handle encoder rotation.
        
        Args:
            delta: Rotation delta (+/- for direction)
        """
        self._wake_display()
        
        if self.edit_mode:
            # Adjust edit value
            step = 1 if abs(delta) == 1 else 5  # Larger steps for faster rotation
            self.edit_value += (step if delta > 0 else -step)
            
            # Clamp to min/max
            self.edit_value = max(
                self.edit_config.get("min", 0),
                min(self.edit_config.get("max", 255), self.edit_value)
            )
            
            # Refresh display
            with self.refresh_lock:
                self._refresh_current_menu()
        else:
            # Normal navigation
            if delta > 0:
                self.move_cursor_down()
            else:
                self.move_cursor_up()
    
    def button_pressed(self):
        """Handle encoder button press."""
        self._wake_display()
        
        if self.display_sleeping:
            return
        
        if self.edit_mode:
            # Save and exit edit mode
            self._save_edit_value()
            self.edit_mode = False
            self._refresh_current_menu()
            return
        
        # Get selected item
        menu_config = self._get_current_menu_config()
        items = menu_config.get("items", [])
        selected_index = self.display.get_selected_item_index()
        
        if selected_index >= len(items):
            return
        
        item = items[selected_index]
        item_type = item.get("type", "static")
        
        if item_type == "back":
            self._navigate_back()
        elif item_type == "submenu":
            submenu_name = item.get("submenu")
            if submenu_name:
                self._navigate_to(submenu_name)
        elif item_type == "checkbox":
            self._handle_checkbox(item)
        elif item_type == "editable":
            self._enter_edit_mode(item)
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
        self.display.cursor_position = 0
        self._refresh_current_menu()
    
    def _navigate_back(self):
        """Navigate back to previous menu."""
        if len(self.menu_stack) > 1:
            self.menu_stack.pop()
            self.current_menu_name = self.menu_stack[-1]
            # Reset display position when going back
            self.display.scroll_index = 0
            self.display.cursor_position = 0
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
        func_name = item.get("function")
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
    
    def _save_edit_value(self):
        """Save the edited value."""
        func_name = self.edit_config.get("function")
        if func_name:
            func = self.function_registry.get(func_name)
            if func:
                func(self.edit_value)
    
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
        self.display.set_rotation(0)
        logger.info("Orientation set to knob left")
    
    def _set_orientation_right(self):
        """Set orientation to knob on right."""
        user_settings.set_orientation("right")
        self.display.set_rotation(180)
        logger.info("Orientation set to knob right")
    
    def _set_display_brightness(self, value: int):
        """Set display brightness.
        
        Args:
            value: Brightness level (0-255)
        """
        user_settings.set_display_brightness(value)
        self.display.set_contrast(value)
        logger.info(f"Display brightness set to {value}")
    
    def _set_led_brightness(self, value: int):
        """Set LED brightness.
        
        Args:
            value: Brightness level (0-255)
        """
        user_settings.set_led_brightness(value)
        if self.led_controller:
            self.led_controller.set_brightness(value)
        logger.info(f"LED brightness set to {value}")
