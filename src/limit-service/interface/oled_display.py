# oled_display.py
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
from luma.core.render import canvas
import time
import threading
from typing import List, Optional


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

        self.device = ssd1306(serial, width=128, height=32)
        self.lines: List[str] = []
        self.scroll_index: int = 0
        self._scroll_thread: Optional[threading.Thread] = None
        self._scroll_stop_event = threading.Event()
        self._target_scroll_index: Optional[int] = None

        # --- SSD1305-specific quirks ---
        # COM pins config
        self.device.command(0xDA, 0x12)

        # Shift visible window right a bit
        try:
            self.device._colstart += 4
            self.device._colend   += 4
        except AttributeError:
            pass
        # -------------------------------

        self.device.contrast(255)
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

    def set_lines(self, lines: List[str]) -> None:
        """
        Set the lines array and display the first two lines.
        
        Args:
            lines: Array of strings where each entry is a line of text
        """
        self.lines = lines
        self.scroll_index = 0
        line1 = lines[0] if len(lines) > 0 else ""
        line2 = lines[1] if len(lines) > 1 else ""
        self.show_lines(line1, line2)

    def scroll_up(self) -> None:
        """
        Scroll the display up by one line (show earlier lines).
        """
        if self.scroll_index > 0:
            self.scroll_index -= 1
            line1 = self.lines[self.scroll_index] if self.scroll_index < len(self.lines) else ""
            line2 = self.lines[self.scroll_index + 1] if self.scroll_index + 1 < len(self.lines) else ""
            self.show_lines(line1, line2)

    def scroll_down(self) -> None:
        """
        Scroll the display down by one line (show later lines).
        """
        if len(self.lines) > 2 and self.scroll_index < len(self.lines) - 2:
            self.scroll_index += 1
            line1 = self.lines[self.scroll_index] if self.scroll_index < len(self.lines) else ""
            line2 = self.lines[self.scroll_index + 1] if self.scroll_index + 1 < len(self.lines) else ""
            self.show_lines(line1, line2)

    def _smooth_scroll_worker(self, direction: str, steps: int = 8, delay: float = 0.01) -> None:
        """
        Worker function that performs smooth scrolling animation with easing.
        Uses ease-in-out curve: starts slow, accelerates in middle, decelerates at end.
        
        Args:
            direction: 'up' or 'down'
            steps: Number of animation frames (default 8). Lower = faster animation.
                   Note: Display SPI refresh (~15-30ms) dominates timing, not delay.
            delay: Additional delay between frames in seconds (default 0.01).
                   Values below ~0.015s have minimal effect due to SPI overhead.
        """
        if direction == 'up' and self.scroll_index <= 0:
            self._target_scroll_index = None
            return
        if direction == 'down' and (len(self.lines) <= 2 or self.scroll_index >= len(self.lines) - 2):
            self._target_scroll_index = None
            return

        # Get current and next lines
        if direction == 'up':
            next_index = self.scroll_index - 1
        else:
            next_index = self.scroll_index + 1

        # Store the target index
        self._target_scroll_index = next_index

        current_line1 = self.lines[self.scroll_index] if self.scroll_index < len(self.lines) else ""
        current_line2 = self.lines[self.scroll_index + 1] if self.scroll_index + 1 < len(self.lines) else ""
        
        if direction == 'up':
            next_line1 = self.lines[next_index] if next_index < len(self.lines) else ""
            next_line2 = current_line1
        else:
            next_line1 = current_line2
            next_line2 = self.lines[next_index + 1] if next_index + 1 < len(self.lines) else ""

        # Ease-in-out function for smooth acceleration/deceleration
        def ease_in_out(t: float) -> float:
            """Cubic ease-in-out: t^3 for first half, mirrored for second half."""
            if t < 0.5:
                return 4 * t * t * t
            else:
                return 1 - pow(-2 * t + 2, 3) / 2

        # Animate the scroll with easing
        for step in range(steps + 1):
            if self._scroll_stop_event.is_set():
                break
            
            # Calculate eased position (0.0 to 1.0)
            progress = step / steps
            eased_progress = ease_in_out(progress)
            
            # Convert to pixel offset (0 to 12)
            offset = int(eased_progress * steps)
            if direction == 'up':
                offset = -offset
            
            with canvas(self.device) as draw:
                # Explicitly clear the display to prevent ghosting
                draw.rectangle(self.device.bounding_box, outline=0, fill=0)
                
                # Draw current lines shifting out
                if current_line1:
                    draw.text((4, 4 - offset), current_line1, fill=1)
                if current_line2:
                    draw.text((4, 16 - offset), current_line2, fill=1)
                
                # Draw next lines shifting in
                if direction == 'down':
                    if next_line2:
                        draw.text((4, 28 - offset), next_line2, fill=1)
                else:  # up
                    if next_line1:
                        draw.text((4, -8 - offset), next_line1, fill=1)
            
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
            
            if self._target_scroll_index is not None:
                self.scroll_index = self._target_scroll_index
                line1 = self.lines[self.scroll_index] if self.scroll_index < len(self.lines) else ""
                line2 = self.lines[self.scroll_index + 1] if self.scroll_index + 1 < len(self.lines) else ""
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