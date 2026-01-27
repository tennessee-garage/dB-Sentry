"""SentryHub Interface - Main application for OLED/encoder UI with dynamic menus."""

import sys
import time
import signal
import logging
from pathlib import Path

from interface.oled_display import OledDisplay
from interface.dynamic_menu import DynamicMenu
from interface.encoder import EncoderControl
from led_controller import LEDController

logger = logging.getLogger(__name__)


class SentryHubInterface:
    """Main application for SentryHub interface with OLED display and rotary encoder."""
    
    def __init__(self):
        """Initialize interface components."""
        logger.info("Initializing SentryHub interface...")
        
        # Initialize display
        self.display = OledDisplay(contrast=180)
        logger.info("Display initialized")
        
        # Initialize LED controller (may run in simulate mode)
        self.led_controller = LEDController()
        logger.info(f"LED controller initialized (simulate={self.led_controller.simulate})")
        
        # Initialize dynamic menu
        self.menu = DynamicMenu(
            display=self.display,
            led_controller=self.led_controller
        )
        logger.info("Dynamic menu initialized")
        
        # Initialize encoder
        self.encoder = EncoderControl()
        self.encoder.register_rotate_callback(self.on_encoder_rotate)
        self.encoder.register_button_callback(self.on_encoder_button)
        logger.info("Encoder initialized")
        
        # Set up signal handler for clean shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        logger.info("SentryHub interface ready! Use encoder to navigate menus.")
        logger.info("- Rotate: Move cursor up/down or adjust values in edit mode")
        logger.info("- Press: Select item, enter submenus, or save edits")
        logger.info("- Display will sleep after 60 seconds of inactivity")
    
    def on_encoder_rotate(self, delta: int, steps: int):
        """Handle encoder rotation.
        
        Args:
            delta: Rotation delta (+/- for direction)
            steps: Current encoder step position
        """
        logger.debug(f"Encoder rotated: {delta}")
        self.menu.encoder_rotated(delta)
    
    def on_encoder_button(self):
        """Handle encoder button press."""
        logger.debug("Encoder button pressed")
        self.menu.button_pressed()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info("Shutdown signal received, cleaning up...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")
        
        # Stop menu refresh thread
        self.menu.stop()
        
        # Clear display
        self.display.clear()
        
        logger.info("Cleanup complete")
    
    def run(self):
        """Run the interface (blocks until interrupted)."""
        try:
            logger.info("Interface running. Press Ctrl+C to exit.")
            
            # Keep the main thread alive
            while True:
                time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        
        finally:
            self.cleanup()
