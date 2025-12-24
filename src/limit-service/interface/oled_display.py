# oled_display.py
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
from luma.core.render import canvas
from PIL import Image, ImageDraw
import time
import threading
import logging
from typing import List, Optional, Dict

from .menu import Menu

logger = logging.getLogger(__name__)


class OledDisplay:
    def __init__(self, spi_speed_hz: int = 16000000):
        """
        Initialize the OLED display.
        
        Args:
            spi_speed_hz: SPI bus speed in Hz (default 16MHz).
                          Typical range: 8MHz to 32MHz depending on hardware.
                          Higher speeds = faster screen updates = smoother scrolling.
        """
        serial = spi(
            port=0,
            device=0,
            gpio_DC=24,
            gpio_RST=25,
            bus_speed_hz=spi_speed_hz,
        )
        self.device = ssd1306(serial, width=128, height=32, mode=1)
        self.device.command(0xDA, 0x12) # Use alternate COM pin configuration
        self.device._colstart += 4
        self.device._colend += 4

        self.current_menu: Optional[Menu] = None
        self.scroll_index: int = 0
        self.cursor_position: int = 0  # Which line (0 or 1) has the cursor
        self._scroll_thread: Optional[threading.Thread] = None
        self._scroll_stop_event = threading.Event()
        self._target_scroll_index: Optional[int] = None

        # Reduce contrast to minimize ghosting (was 255)
        self.device.contrast(180)
        self.device.clear()

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
        Load a menu and display the first two items with cursor.
        
        Args:
            menu: Menu object with pre-rendered frames
        """
        self.current_menu = menu
        self.scroll_index = 0
        self.cursor_position = 0  # Start with cursor on first line
        self._display_current_menu()

    def _display_current_menu(self) -> None:
        """Display the current menu state with cursor."""
        if not self.current_menu:
            return
        
        line1 = self.current_menu.get_item(self.scroll_index)
        line2 = self.current_menu.get_item(self.scroll_index + 1)
        
        # Try to use pre-rendered frame with cursor
        frame = self.current_menu.get_frame(line1, line2, self.cursor_position)
        if frame:
            self.device.display(frame)
        else:
            # Fallback to regular display
            self.show_lines(line1, line2)
    
    def get_selected_item_index(self) -> int:
        """
        Get the index of the currently selected menu item.
        
        Returns:
            Index of the selected item
        """
        return self.scroll_index + self.cursor_position
    
    def move_cursor_down(self) -> None:
        """Move cursor down to the next line or scroll if at bottom."""
        if not self.current_menu:
            return
        
        if self.cursor_position == 0 and len(self.current_menu) > self.scroll_index + 1:
            # Move cursor to second line
            self.cursor_position = 1
            self._display_current_menu()
        elif self.cursor_position == 1 and len(self.current_menu) > self.scroll_index + 2:
            # Scroll down, keep cursor on second line
            self.scroll_index += 1
            self._display_current_menu()
    
    def move_cursor_up(self) -> None:
        """Move cursor up to the previous line or scroll if at top."""
        if not self.current_menu:
            return
        
        if self.cursor_position == 1:
            # Move cursor to first line
            self.cursor_position = 0
            self._display_current_menu()
        elif self.cursor_position == 0 and self.scroll_index > 0:
            # Scroll up, keep cursor on first line
            self.scroll_index -= 1
            self._display_current_menu()

    def scroll_up(self) -> None:
        """
        Scroll the display up by one line (show earlier lines).
        """
        if not self.current_menu:
            return
            
        if self.scroll_index > 0:
            self.scroll_index -= 1
            line1 = self.current_menu.get_item(self.scroll_index)
            line2 = self.current_menu.get_item(self.scroll_index + 1)
            self.show_lines(line1, line2)

    def scroll_down(self) -> None:
        """
        Scroll the display down by one line (show later lines).
        """
        if not self.current_menu:
            return
            
        if len(self.current_menu) > 2 and self.scroll_index < len(self.current_menu) - 2:
            self.scroll_index += 1
            line1 = self.current_menu.get_item(self.scroll_index)
            line2 = self.current_menu.get_item(self.scroll_index + 1)
            self.show_lines(line1, line2)

    def _smooth_scroll_worker(self, direction: str, steps: int = 4, delay: float = 0.005) -> None:
        """
        Worker function that performs smooth scrolling animation with easing.
        Uses ease-in-out curve: starts slow, accelerates in middle, decelerates at end.
        
        Args:
            direction: 'up' or 'down'
            steps: Number of animation frames (default 4). Lower = faster animation.
                   Each frame requires a full SPI display refresh (~15-30ms).
                   Recommended: 3-6 frames for balance of smoothness and speed.
            delay: Additional delay between frames in seconds (default 0.005).
                   Values below ~0.015s have minimal effect due to SPI overhead.
        """
        if not self.current_menu:
            self._target_scroll_index = None
            return
            
        if direction == 'up' and self.scroll_index <= 0:
            self._target_scroll_index = None
            return
        if direction == 'down' and (len(self.current_menu) <= 2 or self.scroll_index >= len(self.current_menu) - 2):
            self._target_scroll_index = None
            return

        # Get current and next lines
        if direction == 'up':
            next_index = self.scroll_index - 1
        else:
            next_index = self.scroll_index + 1

        # Store the target index
        self._target_scroll_index = next_index

        current_line1 = self.current_menu.get_item(self.scroll_index)
        current_line2 = self.current_menu.get_item(self.scroll_index + 1)
        
        if direction == 'up':
            next_line1 = self.current_menu.get_item(next_index)
            next_line2 = current_line1
        else:
            next_line1 = current_line2
            next_line2 = self.current_menu.get_item(next_index + 1)

        # Ease-in-out function for smooth acceleration/deceleration
        def ease_in_out(t: float) -> float:
            """Cubic ease-in-out: t^3 for first half, mirrored for second half."""
            if t < 0.5:
                return 4 * t * t * t
            else:
                return 1 - pow(-2 * t + 2, 3) / 2

        # Check if we have pre-rendered frames for faster rendering
        use_prerendered = (self.current_menu and 
                          self.current_menu.has_frame(current_line1, current_line2) and 
                          self.current_menu.has_frame(next_line1, next_line2))

        # Animate the scroll with easing
        for step in range(steps + 1):
            if self._scroll_stop_event.is_set():
                break
            
            # Calculate eased position (0.0 to 1.0)
            progress = step / steps
            eased_progress = ease_in_out(progress)
            
            # Convert to pixel offset
            offset = int(eased_progress * 12)  # Always 12 pixels for one line scroll
            if direction == 'up':
                offset = -offset
            
            if use_prerendered:
                # Use pre-rendered frames - just paste them at offset positions
                frame = Image.new('1', (128, 32), 0)
                
                # Paste current frame shifting out
                current_frame = self.current_menu.get_frame(current_line1, current_line2)
                if current_frame:
                    frame.paste(current_frame, (0, -offset))
                
                # Paste next frame shifting in
                next_frame = self.current_menu.get_frame(next_line1, next_line2)
                if next_frame:
                    if direction == 'down':
                        frame.paste(next_frame, (0, 32 - offset))
                    else:  # up
                        frame.paste(next_frame, (0, -32 - offset))
            else:
                # Fallback to drawing text (slower)
                frame = Image.new('1', (128, 32), 0)
                frame_draw = ImageDraw.Draw(frame)
                
                # Draw current lines shifting out
                if current_line1:
                    frame_draw.text((4, 4 - offset), current_line1, fill=1)
                if current_line2:
                    frame_draw.text((4, 16 - offset), current_line2, fill=1)
                
                # Draw next lines shifting in
                if direction == 'down':
                    if next_line2:
                        frame_draw.text((4, 28 - offset), next_line2, fill=1)
                else:  # up
                    if next_line1:
                        frame_draw.text((4, -8 - offset), next_line1, fill=1)
            
            self.device.display(frame)
            time.sleep(delay)

        # Update the scroll index after animation completes
        if not self._scroll_stop_event.is_set():
            self.scroll_index = next_index
            self.show_lines(next_line1, next_line2)
        
        self._target_scroll_index = None

    def _complete_existing_scroll(self) -> None:
        if self._scroll_thread and self._scroll_thread.is_alive():
            self._scroll_stop_event.set()
            self._scroll_thread.join()
            
            if self._target_scroll_index is not None and self.current_menu:
                self.scroll_index = self._target_scroll_index
                line1 = self.current_menu.get_item(self.scroll_index)
                line2 = self.current_menu.get_item(self.scroll_index + 1)
                self.show_lines(line1, line2)
                self._target_scroll_index = None

    def _smooth_scroll_handler(self, direction: str) -> None:
        # Stop any existing scroll animation and jump to its end state
        self._complete_existing_scroll()

        # Start new scroll animation
        self._scroll_stop_event.clear()
        self._scroll_thread = threading.Thread(target=self._smooth_scroll_worker, args=(direction,))
        self._scroll_thread.daemon = True
        self._scroll_thread.start()

    def scroll_up_smooth(self) -> None:
        """
        Scroll the display up by one line with smooth animation (non-blocking).
        This method returns immediately while the animation runs in the background.
        """
        self._smooth_scroll_handler('up')

    def scroll_down_smooth(self) -> None:
        """
        Scroll the display down by one line with smooth animation (non-blocking).
        This method returns immediately while the animation runs in the background.
        """
        self._smooth_scroll_handler('down')

    def clear(self):
        # Stop any running scroll animation
        if self._scroll_thread and self._scroll_thread.is_alive():
            self._scroll_stop_event.set()
            self._scroll_thread.join()
        self.device.clear()


if __name__ == "__main__":
    oled = OledDisplay()
    oled.show_lines("Hello,", "dB Sentry!")
    time.sleep(5)
    oled.clear()