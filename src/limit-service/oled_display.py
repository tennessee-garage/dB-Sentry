# oled_display.py
from luma.core.interface.serial import spi
from luma.oled.device import ssd1306
from luma.core.render import canvas
import time


class OledDisplay:
    def __init__(self):
        serial = spi(
            port=0,
            device=0,
            gpio_DC=24,
            gpio_RST=25,
        )

        self.device = ssd1306(serial, width=128, height=32)

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
            draw.rectangle(self.device.bounding_box, outline=1, fill=0)
            if line1:
                draw.text((4, 4), line1, fill=1)
            if line2:
                draw.text((4, 16), line2, fill=1)

    def clear(self):
        self.device.clear()


if __name__ == "__main__":
    oled = OledDisplay()
    oled.show_lines("Hello,", "dB Sentry!")
    time.sleep(5)
    oled.clear()