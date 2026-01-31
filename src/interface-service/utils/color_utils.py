"""Color conversion utilities for LED control.

Provides functions for converting between color spaces and generating color values.
"""


def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """Convert HSV color to RGB.
    
    Args:
        h: Hue (0-360 degrees)
        s: Saturation (0-100 percent)
        v: Value/Brightness (0-100 percent)
        
    Returns:
        Tuple of (r, g, b) values (0-255)
    """
    s = s / 100.0
    v = v / 100.0
    h = h / 60.0
    
    c = v * s
    x = c * (1 - abs((h % 2) - 1))
    m = v - c
    
    if h < 1:
        r, g, b = c, x, 0
    elif h < 2:
        r, g, b = x, c, 0
    elif h < 3:
        r, g, b = 0, c, x
    elif h < 4:
        r, g, b = 0, x, c
    elif h < 5:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    return (
        int((r + m) * 255),
        int((g + m) * 255),
        int((b + m) * 255)
    )


def hue_to_rgb(hue: float) -> tuple:
    """Convert hue (0.0-1.0) to RGB with full saturation and value.
    
    Args:
        hue: Hue value from 0.0 to 1.0
        
    Returns:
        Tuple of (r, g, b) values (0-255)
    """
    return hsv_to_rgb(hue * 360.0, 100, 100)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB values to hex color string.
    
    Args:
        r: Red component (0-255)
        g: Green component (0-255)
        b: Blue component (0-255)
        
    Returns:
        Hex color string (e.g., "#FF0000")
    """
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def clamp_rgb(r: int, g: int, b: int) -> tuple:
    """Clamp RGB values to valid range (0-255).
    
    Args:
        r: Red component
        g: Green component
        b: Blue component
        
    Returns:
        Tuple of clamped (r, g, b) values (0-255)
    """
    return (
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b))
    )
