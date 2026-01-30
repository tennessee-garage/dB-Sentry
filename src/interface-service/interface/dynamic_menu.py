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
        
        # Apply saved user settings on startup
        self._apply_startup_settings()
        
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
        
        elif item_type == "brightness_bar":
            # Don't show value in menu, just the label
            pass
        
        return text
    
    def _get_current_menu_config(self) -> Dict:
        """Get configuration for current menu.
        
        Returns:
            Menu configuration dictionary
        """
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
            
            # Save current position if preserving
            saved_scroll = self.display.scroll_index if preserve_position else 0
            
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
                        if item.get("type") == "dynamic" and self._should_refresh_item(item):
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
        self.stop_refresh.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=2)
    
    # Navigation methods
    
    def move_cursor_down(self):
        """Move cursor down."""
        self._wake_display()
        if not self.edit_mode:
            with self.refresh_lock:
                self.display.move_cursor_down()
    
    def move_cursor_up(self):
        """Move cursor up."""
        self._wake_display()
        if not self.edit_mode:
            with self.refresh_lock:
                self.display.move_cursor_up()
    
    def encoder_rotated(self, delta: int):
        """Handle encoder rotation.
        
        Args:
            delta: Rotation delta (+/- for direction)
        """
        self._wake_display()
        
        if self.edit_mode:
            # Calculate step size based on bar width for brightness_bar mode
            if self.edit_config.get("type") == "brightness_bar":
                # Make each encoder step = 1 pixel change on the bar
                bar_width = 110  # Must match _render_brightness_bar
                min_val = self.edit_config.get("min", 0)
                max_val = self.edit_config.get("max", 255)
                step = (max_val - min_val) / bar_width  # Each step = 1 pixel
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
            
            # Refresh display - check if we're in brightness bar mode
            if self.edit_config.get("type") == "brightness_bar":
                self._render_brightness_bar()
            else:
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
        elif item_type == "brightness_bar":
            self._enter_brightness_bar_mode(item)
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
                r, g, b = self._hsv_to_rgb(hue, 100, 100)
                
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
    
    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """Convert HSV color to RGB.
        
        Args:
            h: Hue (0-360)
            s: Saturation (0-100)
            v: Value (0-100)
            
        Returns:
            Tuple of (r, g, b) values (0-255)
        """
        s = s / 100.0
        v = v / 100.0
        h = h / 60.0
        
        c = v * s
        x = c * (1 - abs((h % 2) - 1))
        m = v - c
        
        if h < 1:
            r, g, b = c, x, 0
        elif h < 2:
            r, g, b = x, c, 0
        elif h < 3:
            r, g, b = 0, c, x
        elif h < 4:
            r, g, b = 0, x, c
        elif h < 5:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        return (
            int((r + m) * 255),
            int((g + m) * 255),
            int((b + m) * 255)
        )
    
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
    
    def _save_edit_value(self):
        """Save the edited value."""
        func_name = self.edit_config.get("function")
        if func_name:
            func = self.function_registry.get(func_name)
            if func:
                func(self.edit_value)
        
        # Clear rainbow pattern and restore LED state after brightness adjustment
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
