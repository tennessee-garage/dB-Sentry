#!/usr/bin/env python3
"""Example showing how to use menu items with action callbacks.

This demonstrates the new menu system that supports both plain strings
and dictionaries with 'text' and 'action' keys.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interface.menu import Menu


def make_action(message):
    """Create an action that prints a message.
    
    Args:
        message: Message to print when action is executed
        
    Returns:
        Action function
    """
    def action():
        print(f">>> {message}")
        if "Exiting" in message:
            sys.exit(0)
    return action


def main():
    """Main entry point."""
    # Create menu items with action callbacks
    menu_items = [
        {"text": "1. View Status", "action": make_action("Viewing Status...")},
        {"text": "2. Set Threshold", "action": make_action("Setting Threshold...")},
        {"text": "3. Calibrate Mic", "action": make_action("Calibrating Microphone...")},
        "4. Just a Label",  # String item (no action)
        {"text": "5. Network Info", "action": make_action("Displaying Network Info...")},
        {"text": "6. Exit", "action": make_action("Exiting application...")},
    ]
    
    print("Creating menu with mixed items (strings and dicts)...\n")
    menu = Menu(menu_items)
    
    print(f"Menu has {len(menu)} items:")
    for i in range(len(menu)):
        text = menu.get_item(i)
        has_action = "✓" if menu.get_action(i) else "✗"
        print(f"  [{i}] {text} (action: {has_action})")
    
    print("\n--- Testing action execution ---")
    
    # Test executing actions
    test_indices = [0, 3, 2]
    for idx in test_indices:
        print(f"\nExecuting action for item {idx}:")
        result = menu.execute_action(idx)
        print(f"Action executed: {result}")
    
    print("\n--- Example complete! ---")


if __name__ == "__main__":
    main()
