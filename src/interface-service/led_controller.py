import logging
from config import cfg
from typing import Optional, Any, TYPE_CHECKING

logger = logging.getLogger(__name__)


# For type-checkers, import rpi types only during type checking so editors
# can resolve names if the package is available in the environment.
if TYPE_CHECKING:  # pragma: no cover
    from rpi_ws281x import PixelStrip, Color  # type: ignore

try:
    # runtime import: may fail on non-Raspberry Pi systems
    from rpi_ws281x import PixelStrip, Color  # type: ignore
    _HAVE_RPI_WS281X = True
except Exception:
    PixelStrip = None  # type: ignore
    Color = None  # type: ignore
    _HAVE_RPI_WS281X = False


class LEDController:
    """Controls an LED strip, or logs actions when running in simulate mode.

    Behavior:
    - If `cfg.led_simulate` is true, controller logs color changes instead of
      touching hardware.
    - If `cfg.led_simulate` is false but the `rpi_ws281x` package is not
      importable, the controller falls back to simulation mode automatically.
    """

    def __init__(self):
        self.simulate: bool = cfg.led_simulate or (not _HAVE_RPI_WS281X)
        self.count: int = cfg.led_count
        self.brightness: int = 255  # Default full brightness
        # hardware objects (only set when real hardware is available)
        self.strip: Optional[Any] = None
        self.Color: Optional[Any] = None

        if not self.simulate and _HAVE_RPI_WS281X and PixelStrip is not None:
            try:
                # Typical defaults; user can modify via env if desired
                self.strip = PixelStrip(self.count, 18)
                # PixelStrip.begin may not be present in stubbed environments
                if self.strip and hasattr(self.strip, 'begin'):
                    self.strip.begin()
                self.Color = Color
            except Exception as e:
                logger.exception("Failed to init rpi_ws281x; falling back to simulate: %s", e)
                self.simulate = True

    def set_color(self, r: int, g: int, b: int):
        """Set the whole strip to the given RGB color.

        When simulating, the action is logged. When running with hardware,
        the method validates the hardware objects before calling into them.
        Colors are adjusted by current brightness level.
        """
        # Apply brightness scaling
        r = int(r * self.brightness / 255)
        g = int(g * self.brightness / 255)
        b = int(b * self.brightness / 255)
        
        if self.simulate:
            logger.info("LEDs set to R=%d G=%d B=%d (simulated)", r, g, b)
            return

        if self.strip is None or self.Color is None:
            logger.warning("LED hardware not initialized; running in simulate mode")
            logger.info("LEDs set to R=%d G=%d B=%d (simulated)", r, g, b)
            return

        for i in range(self.count):
            # use provided API; if methods are missing, fallback to logging
            try:
                self.strip.setPixelColor(i, self.Color(r, g, b))
            except Exception:
                logger.exception("Failed to set pixel color on hardware; switching to simulate")
                self.simulate = True
                logger.info("LEDs set to R=%d G=%d B=%d (simulated)", r, g, b)
                return

        if hasattr(self.strip, 'show'):
            try:
                self.strip.show()
            except Exception:
                logger.exception("Failed to show strip; ignoring")

    def set_brightness(self, level: int):
        """Set LED brightness level (0-255).
        
        Args:
            level: Brightness level from 0 (off) to 255 (full brightness)
        """
        self.brightness = max(0, min(255, level))
        mode = "simulated" if self.simulate else "hardware"
        logger.info(f"LED brightness set to {self.brightness} ({mode})")
    
    def get_brightness(self) -> int:
        """Get current LED brightness level (0-255).
        
        Returns:
            Current brightness level
        """
        return self.brightness

    def set_by_value(self, value: float, limits: dict):
        """Simple evaluation: if value < low -> green, between low/mid -> yellow, > high -> red."""
        low = limits.get("low")
        mid = limits.get("mid")
        high = limits.get("high")
        if low is None or mid is None or high is None:
            logger.warning("Limits incomplete, setting LEDs to blue (unknown)")
            self.set_color(0, 0, 255)
            return
        if value <= low:
            # green
            self.set_color(0, 255, 0)
        elif value <= mid:
            # yellow
            self.set_color(255, 255, 0)
        elif value <= high:
            # orange
            self.set_color(255, 120, 0)
        else:
            # red
            self.set_color(255, 0, 0)
