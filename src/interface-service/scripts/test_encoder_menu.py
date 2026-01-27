#!/usr/bin/env python3
"""Test script for encoder-controlled menu navigation.

This script demonstrates using a rotary encoder to scroll through
a menu on the OLED display.
"""
import sys
import time
import logging
from pathlib import Path
import signal

# Get the absolute path to the parent directory (limit-service)
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent

# Add to path if not already there
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

print(f"Script directory: {script_dir}")
print(f"Parent directory: {parent_dir}")
print(f"Python path: {sys.path[:3]}")

# Now import the modules
try:
    from interface.oled_display import OledDisplay
    from interface.menu import Menu
    from interface.encoder import EncoderControl
except ImportError as e:
    print(f"\nImport error: {e}")
    print(f"\nMake sure you're running from: {parent_dir}")
    print(f"Or run with: cd {parent_dir} && python scripts/test_encoder_menu.py")
    sys.exit(1)

# Enable logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(message)s')


class EncoderMenuController:
    """Controls menu navigation with a rotary encoder."""
    
    def __init__(self):
        """Initialize the display, encoder, and menu."""
        print("Initializing OLED display...")
        self.oled = OledDisplay(spi_speed_hz=32000000)
        
        print("Initializing rotary encoder...")
        self.encoder = EncoderControl()
        
        # Track encoder state
        self.last_position = 0
        
        # Create menu
        menu_items = [
            "1. View Status",
            "2. Set Threshold",
            "3. Calibrate Mic",
            "4. Network Info",
            "5. System Stats",
            "6. Alert History",
            "7. Settings",
            "8. About",
            "9. Exit",
        ]
        
        print(f"Creating menu with {len(menu_items)} items...")
        self.menu = Menu(menu_items)
        
        # Load menu into display
        self.oled.load_menu(self.menu)
        
        # Register encoder callbacks
        self.encoder.register_rotate_callback(self.on_rotate)
        self.encoder.register_button_callback(self.on_button_press)
        
        print("\nMenu loaded! Use the encoder to navigate:")
        print("  - Rotate clockwise to move cursor down")
        print("  - Rotate counter-clockwise to move cursor up")
        print("  - Press button to select the item with the '>' cursor")
        print("  - Press Ctrl+C to exit\n")
    
    def on_rotate(self, delta: int, current_steps: int) -> None:
        """
        Handle encoder rotation.
        
        Args:
            delta: Change in steps since last rotation
            current_steps: Current absolute step count
        """
        if delta > 0:
            # Clockwise rotation - move cursor down
            for _ in range(abs(delta)):
                self.oled.move_cursor_down()
        elif delta < 0:
            # Counter-clockwise rotation - move cursor up
            for _ in range(abs(delta)):
                self.oled.move_cursor_up()
    
    def on_button_press(self) -> None:
        """Handle encoder button press."""
        selected_index = self.oled.get_selected_item_index()
        selected_item = self.menu.get_item(selected_index)
        print(f"\n*** SELECTED [{selected_index}]: {selected_item} ***\n")
        
        # Check for exit
        if "Exit" in selected_item:
            print("Exit selected. Shutting down...")
            self.cleanup()
            sys.exit(0)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        print("\nCleaning up...")
        self.oled.clear()
    
    def run(self) -> None:
        """Run the menu controller (blocks forever)."""
        # Set up signal handler for clean exit
        def signal_handler(sig, frame):
            print("\n\nInterrupt received...")
            self.cleanup()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Keep the program running
        print("Running... (waiting for encoder input)")
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup()
            sys.exit(0)

def main():
    """Main entry point."""
    try:
        controller = EncoderMenuController()
        controller.run()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
