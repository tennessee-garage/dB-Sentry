#!/usr/bin/env python3
"""Demo script showing various patterns on a 20 pixel neopixel strip on GPIO18.

This script demonstrates different LED patterns:
- Rainbow: Cycles through rainbow colors
- Chase: A colored light chasing across the strip
- Pulse: All LEDs pulsing in and out
- Alternate: Alternating colors

Run with optional arguments:
    python3 neopixel_pattern_demo.py [pattern] [duration]
    
Examples:
    python3 neopixel_pattern_demo.py rainbow 10
    python3 neopixel_pattern_demo.py chase 5
    python3 neopixel_pattern_demo.py pulse 8
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from rpi_ws281x import PixelStrip, Color  # type: ignore
except ImportError:
    print("Warning: rpi_ws281x not available. Install with:")
    print("  pip install rpi-ws281x")
    sys.exit(1)


class NeopixelDemo:
    """Demo controller for neopixel patterns."""
    
    def __init__(self, pin=18, count=20):
        """Initialize the neopixel strip.
        
        Args:
            pin: GPIO pin number
            count: Number of pixels
        """
        self.pin = pin
        self.count = count
        
        # Initialize the strip with just count and pin
        self.strip = PixelStrip(count, pin)
        if hasattr(self.strip, 'begin'):
            self.strip.begin()
        
    def clear(self):
        """Turn off all pixels."""
        for i in range(self.count):
            self.strip.setPixelColor(i, Color(0, 0, 0))
        self.strip.show()
        
    def rainbow(self, duration=10, speed=0.02):
        """Display a rainbow pattern cycling through the strip.
        
        Args:
            duration: How long to run the pattern (seconds)
            speed: Delay between frames (seconds)
        """
        print("Running rainbow pattern...")
        start_time = time.time()
        
        while time.time() - start_time < duration:
            for offset in range(256):
                for i in range(self.count):
                    hue = (offset + i * 256 // self.count) % 256
                    color = self._hsv_to_rgb(hue, 255, 255)
                    self.strip.setPixelColor(i, color)
                self.strip.show()
                time.sleep(speed)
                
                if time.time() - start_time >= duration:
                    break
                    
    def chase(self, duration=10, speed=0.05):
        """Display a colored light chasing across the strip.
        
        Args:
            duration: How long to run the pattern (seconds)
            speed: Delay between frames (seconds)
        """
        print("Running chase pattern...")
        start_time = time.time()
        chase_color = Color(0, 255, 0)  # Green
        
        while time.time() - start_time < duration:
            for pos in range(self.count):
                self.clear()
                self.strip.setPixelColor(pos, chase_color)
                if pos > 0:
                    self.strip.setPixelColor(pos - 1, Color(0, 100, 0))  # Dimmer
                self.strip.show()
                time.sleep(speed)
                
                if time.time() - start_time >= duration:
                    break
                    
    def pulse(self, duration=10, speed=0.05):
        """Display all LEDs pulsing in and out.
        
        Args:
            duration: How long to run the pattern (seconds)
            speed: Delay between frames (seconds)
        """
        print("Running pulse pattern...")
        start_time = time.time()
        pulse_color_base = (255, 0, 0)  # Red
        
        while time.time() - start_time < duration:
            # Pulse in
            for brightness in range(0, 256, 5):
                for i in range(self.count):
                    r = int(pulse_color_base[0] * brightness / 255)
                    g = int(pulse_color_base[1] * brightness / 255)
                    b = int(pulse_color_base[2] * brightness / 255)
                    self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
                time.sleep(speed)
                
                if time.time() - start_time >= duration:
                    break
                    
            # Pulse out
            for brightness in range(255, -1, -5):
                for i in range(self.count):
                    r = int(pulse_color_base[0] * brightness / 255)
                    g = int(pulse_color_base[1] * brightness / 255)
                    b = int(pulse_color_base[2] * brightness / 255)
                    self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
                time.sleep(speed)
                
                if time.time() - start_time >= duration:
                    break
                    
    def alternate(self, duration=10, speed=0.1):
        """Display alternating colors on the strip.
        
        Args:
            duration: How long to run the pattern (seconds)
            speed: Delay between frames (seconds)
        """
        print("Running alternate pattern...")
        start_time = time.time()
        color1 = Color(255, 0, 0)  # Red
        color2 = Color(0, 0, 255)  # Blue
        
        while time.time() - start_time < duration:
            # Pattern 1
            for i in range(self.count):
                color = color1 if i % 2 == 0 else color2
                self.strip.setPixelColor(i, color)
            self.strip.show()
            time.sleep(speed)
            
            if time.time() - start_time >= duration:
                break
                
            # Pattern 2
            for i in range(self.count):
                color = color2 if i % 2 == 0 else color1
                self.strip.setPixelColor(i, color)
            self.strip.show()
            time.sleep(speed)
            
            if time.time() - start_time >= duration:
                break
    
    @staticmethod
    def _hsv_to_rgb(h, s, v):
        """Convert HSV color to RGB Color object.
        
        Args:
            h: Hue (0-255)
            s: Saturation (0-255)
            v: Value (0-255)
            
        Returns:
            Color object
        """
        h = h % 256
        s = s / 255.0
        v = v / 255.0
        
        c = v * s
        x = c * (1 - abs((h / 42.666) % 2 - 1))
        m = v - c
        
        if h < 42.666:
            r, g, b = c, x, 0
        elif h < 85.333:
            r, g, b = x, c, 0
        elif h < 127.999:
            r, g, b = 0, c, x
        elif h < 170.666:
            r, g, b = 0, x, c
        elif h < 213.333:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
            
        return Color(
            int((r + m) * 255),
            int((g + m) * 255),
            int((b + m) * 255)
        )
    
    def cleanup(self):
        """Clean up and turn off the strip."""
        self.clear()
        print("Strip cleaned up.")


def main():
    """Main entry point."""
    # Parse arguments
    pattern = sys.argv[1] if len(sys.argv) > 1 else "rainbow"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    valid_patterns = ["rainbow", "chase", "pulse", "alternate"]
    
    if pattern not in valid_patterns:
        print(f"Invalid pattern: {pattern}")
        print(f"Valid patterns: {', '.join(valid_patterns)}")
        sys.exit(1)
    
    demo = None
    try:
        demo = NeopixelDemo(pin=18, count=20)
        
        if pattern == "rainbow":
            demo.rainbow(duration=duration)
        elif pattern == "chase":
            demo.chase(duration=duration)
        elif pattern == "pulse":
            demo.pulse(duration=duration)
        elif pattern == "alternate":
            demo.alternate(duration=duration)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if demo:
	        demo.cleanup()


if __name__ == "__main__":
    main()
