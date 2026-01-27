#!/usr/bin/env python3
"""Example showing how to use menu items with action callbacks.

This demonstrates the new menu system that supports both plain strings
and dictionaries with 'text' and 'action' keys.
"""
import sys
from pathlib import Path

# Get the absolute path to the parent directory (limit-service)
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent

# Add to path if not already there
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from interface.menu import Menu


def action_status():
    """Action for viewing status."""
    print(">>> Viewing Status...")


def action_threshold():
    """Action for setting threshold."""
    print(">>> Setting Threshold...")


def action_calibrate():
    """Action for calibrating microphone."""
    print(">>> Calibrating Microphone...")


def action_network():
    """Action for network info."""
    print(">>> Displaying Network Info...")


def action_exit():
    """Action for exiting."""
    print(">>> Exiting application...")
    sys.exit(0)


def main():
    """Main entry point."""
    # Example 1: Mix of strings and dicts with actions
    menu_items = [
        {"text": "1. View Status", "action": action_status},
        {"text": "2. Set Threshold", "action": action_threshold},
        {"text": "3. Calibrate Mic", "action": action_calibrate},
        "4. Just a Label",  # String item (no action)
        {"text": "5. Network Info", "action": action_network},
        {"text": "6. Exit", "action": action_exit},
    ]
    
    print("Creating menu with mixed items (strings and dicts)...")
    menu = Menu(menu_items)
    
    print(f"\nMenu has {len(menu)} items:")
    for i in range(len(menu)):
        text = menu.get_item(i)
        action = menu.get_action(i)
        has_action = "✓" if action else "✗"
        print(f"  [{i}] {text} (action: {has_action})")
    
    print("\n--- Testing action execution ---")
    
    # Execute action for item 0
    print("\nExecuting action for item 0:")
    result = menu.execute_action(0)
    print(f"Action executed: {result}")
    
    # Try to execute action for item 3 (string with no action)
    print("\nExecuting action for item 3 (no action):")
    result = menu.execute_action(3)
    print(f"Action executed: {result}")
    
    # Execute action for item 2
    print("\nExecuting action for item 2:")
    result = menu.execute_action(2)
    print(f"Action executed: {result}")
    
    print("\n--- Example complete! ---")


if __name__ == "__main__":
    main()
