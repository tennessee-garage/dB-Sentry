# oled_display.py
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
from luma.core.render import canvas
import time
import logging
from typing import List, Optional, Dict
from gpiozero import OutputDevice

from .menu import Menu

logger = logging.getLogger(__name__)


class OledDisplay:
    DEFAULT_DC_PIN = 24
    DEFAULT_RST_PIN = 25

    def __init__(self, contrast: int = 180, spi_speed_hz: int = 16000000):
        """
        Initialize the OLED display.
        
        Args:
            contrast: Display contrast level (0-255, default 180)
            spi_speed_hz: SPI bus speed in Hz (default 16MHz).
                          Typical range: 8MHz to 32MHz depending on hardware.
                          Higher speeds = faster screen updates = smoother scrolling.
        """

        self.screen_reset()
        
        serial = spi(
            port=0,
            device=0,
            gpio_DC=self.DEFAULT_DC_PIN,
            gpio_RST=self.DEFAULT_RST_PIN,
            bus_speed_hz=spi_speed_hz,
        )
        self.device = ssd1306(serial, width=128, height=32, mode=1)
        self.device.command(0xDA, 0x12) # Use alternate COM pin configuration
        self.device._colstart += 4
        self.device._colend += 4

        # Reduce contrast to minimize ghosting (was 255)
        self.device.contrast(contrast)
        self.device.clear()

        self.current_menu: Optional[Menu] = None
        self.scroll_index: int = 0
        self.rotation: int = 0  # 0 or 180 degrees

    def screen_reset(self) -> None:
        """
        Reset the OLED display via GPIO. In theory the ssd1306 class does this, but
        in practice it seems to need this or the screen does not light up.
        """
        rst_pin = OutputDevice(self.DEFAULT_RST_PIN)
        rst_pin.off()  # Pull low (reset)
        time.sleep(0.01)  # 10ms
        rst_pin.on()   # Pull high (out of reset)
        time.sleep(0.1)  # 100ms for display to stabilize
        rst_pin.close()

    def set_contrast(self, contrast: int) -> None:
        """
        Set the display contrast.
        
        Args:
            contrast: Contrast level (0-255)
        """
        if contrast < 0 or contrast > 255:
            raise ValueError("Contrast must be between 0 and 255")

        self.device.contrast(contrast)
    
    def set_rotation(self, degrees: int) -> None:
        """
        Set display rotation.
        
        Args:
            degrees: Rotation in degrees (0 or 180)
        """
        if degrees not in [0, 180]:
            raise ValueError("Rotation must be 0 or 180 degrees")
        
        self.rotation = degrees
        
        # SSD1306 command for segment remap and COM scan direction
        if degrees == 0:
            # Normal orientation (knob on left)
            self.device.command(0xA0)  # Column address 0 is mapped to SEG0
            self.device.command(0xC0)  # Normal COM scan direction
        else:
            # Rotated 180 degrees (knob on right)
            self.device.command(0xA1)  # Column address 127 is mapped to SEG0
            self.device.command(0xC8)  # Remapped COM scan direction
        
        # Redraw current display
        if self.current_menu:
            self._display_current_menu()
    
    def get_rotation(self) -> int:
        """Get current display rotation in degrees.
        
        Returns:
            Current rotation (0 or 180)
        """
        return self.rotation

    def show_lines(self, line1: str = "", line2: str = ""):
        """
        Draw up to two lines of text on the display.
        """
        with canvas(self.device) as draw:
            # Explicitly clear the display
            draw.rectangle(self.device.bounding_box, outline=0, fill=0)
            if line1:
                draw.text((4, 4), line1, fill=1)
            if line2:
                draw.text((4, 16), line2, fill=1)

    def load_menu(self, menu: Menu) -> None:
        """
        Load a menu and display the first item with cursor.
        
        Args:
            menu: Menu object with pre-rendered frames
        """
        self.current_menu = menu
        self.scroll_index = 0
        self._display_current_menu()

    def _display_current_menu(self) -> None:
        """Display the current menu state with cursor on line 0."""
        if not self.current_menu:
            return
        
        # Use pre-rendered frame with cursor always on line 0
        frame = self.current_menu.get_frame(self.scroll_index, 0)
        if frame:
            self.device.display(frame)
        else:
            # Fallback to regular display
            line1 = self.current_menu.get_item(self.scroll_index)
            line2 = self.current_menu.get_item(self.scroll_index + 1)
            self.show_lines(line1, line2)
    
    def get_selected_item_index(self) -> int:
        """
        Get the index of the currently selected menu item.
        
        Returns:
            Index of the selected item (always scroll_index since cursor is on line 0)
        """
        return self.scroll_index
    
    def move_cursor_down(self) -> None:
        """Scroll down to the next menu item (cursor stays on line 0)."""
        if not self.current_menu:
            return
        
        total_items = len(self.current_menu)
        
        # Don't scroll past the last valid item (menu frames only render up to len - 3)
        if self.scroll_index >= total_items - 3:
            return
        
        self.scroll_index += 1
        self._display_current_menu()
    
    def move_cursor_up(self) -> None:
        """Scroll up to the previous menu item (cursor stays on line 0)."""
        if not self.current_menu:
            return
        
        # Don't scroll past the top
        if self.scroll_index <= 0:
            return
        
        self.scroll_index -= 1
        self._display_current_menu()

    def clear(self):
        self.device.clear()


if __name__ == "__main__":
    oled = OledDisplay()
    oled.show_lines("Hello,", "dB Sentry!")
    time.sleep(5)
    oled.clear()
