#!/usr/bin/env python3
"""Example of how limit-service would use RemoteLEDClient to control LEDs.

This demonstrates the communication pattern between limit-service and interface-service.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ipc.led_ipc_client import RemoteLEDClient


def example_usage():
    """Example showing how to use the RemoteLEDClient."""
    
    # Create a client (connects to interface-service's IPC socket)
    led = RemoteLEDClient()
    
    print("Testing remote LED control...\n")
    
    # Show different alert levels
    print("1. Showing INFO alert (green)...")
    led.show_alert('info')
    time.sleep(1)
    
    print("2. Showing WARNING alert (yellow)...")
    led.show_alert('warning')
    time.sleep(1)
    
    print("3. Showing CRITICAL alert (red)...")
    led.show_alert('critical')
    time.sleep(1)
    
    # Set custom colors
    print("\n4. Setting custom colors...")
    led.set_color(0, 100, 255)  # Blue
    print("   Set to blue")
    time.sleep(1)
    
    led.set_color(255, 165, 0)  # Orange
    print("   Set to orange")
    time.sleep(1)
    
    # Clear
    print("\n6. Clearing LEDs...")
    led.clear()
    
    print("\nDone!")


def example_dB_level_display():
    """Example: Display dB level on LEDs (like limit-service would do)."""
    
    led = RemoteLEDClient()
    
    # Simulate reading dB levels
    dB_readings = [45, 65, 75, 82, 90, 88, 80]
    
    print("Simulating dB level alerts:\n")
    
    for dB in dB_readings:
        if dB < 70:
            alert_level = 'info'
            status = "Normal"
        elif dB < 80:
            alert_level = 'warning'
            status = "Elevated"
        else:
            alert_level = 'critical'
            status = "Critical"
        
        print(f"dB: {dB:3d} → {status:8s} ", end="")
        
        if led.show_alert(alert_level):
            print("✓")
        else:
            print("✗ (interface-service not available?)")
        
        time.sleep(1)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "db-level":
            example_dB_level_display()
        else:
            example_usage()
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
