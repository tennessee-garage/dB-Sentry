#!/usr/bin/env python3
"""Test script for OLED display scrolling functionality.

This script demonstrates the smooth scrolling features by loading
8 menu items and scrolling through them up and down.
"""
import sys
import time
import logging
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from interface.oled_display import OledDisplay
from interface.menu import Menu

# Enable logging to see timing info
logging.basicConfig(level=logging.INFO, format='%(message)s')


def main():
    """Test the OLED display scrolling with menu items."""
    print("Initializing OLED display...")
    oled = OledDisplay(spi_speed_hz=32000000)
    
    # Create a menu with 8 items
    menu_items = [
        "1. View Status",
        "2. Set Threshold",
        "3. Calibrate Mic",
        "4. Network Info",
        "5. System Stats",
        "6. Alert History",
        "7. Settings",
        "8. About",
    ]
    
    print(f"Creating menu with {len(menu_items)} items...")
    menu = Menu(menu_items)
    
    # Load the menu into the display
    print("Loading menu into display...")
    oled.load_menu(menu)
    
    print("Display shows first two items")
    time.sleep(2)
    
    # Scroll down through all items
    print("\nScrolling down through menu...")
    for i in range(len(menu_items) - 2):
        print(f"  Scrolling to show items {i+2} and {i+3}")
        oled.scroll_down_smooth()
        time.sleep(1.5)  # Wait for animation and pause before next scroll
    
    print("\nReached bottom of menu")
    time.sleep(2)
    
    # Scroll back up to the top
    print("\nScrolling back up to top...")
    for i in range(len(menu_items) - 2):
        items_shown = len(menu_items) - 2 - i
        print(f"  Scrolling to show items {items_shown-1} and {items_shown}")
        oled.scroll_up_smooth()
        time.sleep(1.5)  # Wait for animation and pause before next scroll
    
    print("\nBack at top of menu")
    time.sleep(2)
    
    # Demonstrate rapid scrolling (interrupting animations)
    print("\nTesting rapid scroll changes...")
    print("  Quick down-down-down-up-up sequence:")
    oled.scroll_down_smooth()
    time.sleep(0.3)
    oled.scroll_down_smooth()
    time.sleep(0.3)
    oled.scroll_down_smooth()
    time.sleep(0.3)
    oled.scroll_up_smooth()
    time.sleep(0.3)
    oled.scroll_up_smooth()
    time.sleep(2)
    
    print("\nTest complete! Clearing display...")
    oled.clear()
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
