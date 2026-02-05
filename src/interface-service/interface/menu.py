"""Menu system for OLED display.

Handles menu item storage and pre-rendering for optimal performance.
"""
import time
import logging
from typing import List, Dict, Tuple, Optional, Callable, Union, Any
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# Type alias for menu items: can be a string or a dict
MenuItem = Union[str, Dict[str, Any]]

# Cache the font so it's only loaded once
_cached_font = None


def _load_font():
    """Load the best available font for the display.
    
    Returns:
        PIL ImageFont object
    """
    global _cached_font
    
    # Return cached font if already loaded
    if _cached_font is not None:
        return _cached_font
    
    # Try fonts in order of preference for clarity at small sizes
    # Point sizes are larger than pixel heights - 12pt renders to ~10px on OLED
    font_options = [
        # TrueType fonts - try common proportional (non-monospace) fonts first
        ("fonts/PixelOperator8.ttf", 8),
        #("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    ]
    
    for font_path in font_options:
        try:
            if isinstance(font_path, tuple):
                path, size = font_path
                font = ImageFont.truetype(path, size)
                logger.info(f"Loaded font: {path} at {size}pt")
                _cached_font = font
                return font
            else:
                font = ImageFont.load(font_path)
                logger.info(f"Loaded bitmap font: {font_path}")
                _cached_font = font
                return font
        except Exception:
            continue
    
    # Fallback to PIL's built-in default bitmap font
    logger.debug("Using PIL default bitmap font")
    _cached_font = ImageFont.load_default()
    return _cached_font


class Menu:
    """Represents a menu with pre-rendered display frames."""
    
    def __init__(self, items: List[MenuItem], display_width: int = 128, display_height: int = 32):
        """
        Initialize a menu with items and pre-render all display frames.
        
        Args:
            items: List of menu items. Each item can be:
                   - A string (for display only)
                   - A dict with 'text' (str) and optional 'action' (callable)
            display_width: Width of the display in pixels (default 128)
            display_height: Height of the display in pixels (default 32)
        """
        # Add blank items at both start and end to allow scrolling
        # This lets the first item be centered when selected, and last item too
        self.raw_items = [""] + items + [""]
        self.items = [self._get_text(item) for item in self.raw_items]
        self.actions = [self._get_action(item) for item in self.raw_items]
        self.submenus = [self._is_submenu(item) for item in self.raw_items]
        self.right_texts = [self._get_right_text(item) for item in self.raw_items]
        self.display_width = display_width
        self.display_height = display_height
        
        # Load font for rendering
        self.font = _load_font()
        
        # Pre-rendered frame buffers for all possible two-line combinations
        # Key is (line1, line2, cursor_line) tuple, value is the rendered Image
        self._frame_cache: Dict[Tuple[int, Optional[int]], Image.Image] = {}
        
        # Pre-render all frames
        self._prerender_frames()
    
    def _get_text(self, item: MenuItem) -> str:
        """
        Extract the text from a menu item.
        
        Args:
            item: Menu item (string or dict)
            
        Returns:
            The display text for the item
        """
        if isinstance(item, str):
            return item
        elif isinstance(item, dict):
            text = item.get('text', '')
            return str(text) if text else ''
        return ''
    
    def _get_action(self, item: MenuItem) -> Optional[Callable]:
        """
        Extract the action callback from a menu item.
        
        Args:
            item: Menu item (string or dict)
            
        Returns:
            The action callback, or None if not specified
        """
        if isinstance(item, dict):
            action = item.get('action')
            if callable(action):
                return action
        return None
    
    def _is_submenu(self, item: MenuItem) -> bool:
        """Check if a menu item is a submenu."""
        return isinstance(item, dict) and item.get('submenu', False)

    def _get_right_text(self, item: MenuItem) -> str:
        """Extract right-aligned text from a menu item."""
        if isinstance(item, dict):
            right_text = item.get('right_text', '')
            return str(right_text) if right_text else ''
        return ''
    
    def _prerender_frames(self) -> None:
        """Pre-render all possible frame buffers for the menu."""
        logger.debug(f"Pre-rendering {len(self.items)} menu items...")
        start_time = time.perf_counter()
        
        # Pre-render all possible three-line combinations with all cursor positions
        # Stop when the last real item is centered (scroll_index + 1 = len - 2)
        for scroll_index in range(len(self.items) - 2):
            line1 = self.items[scroll_index] if scroll_index < len(self.items) else ""
            line2 = self.items[scroll_index + 1] if scroll_index + 1 < len(self.items) else ""
            line3 = self.items[scroll_index + 2] if scroll_index + 2 < len(self.items) else ""
            right1 = self.right_texts[scroll_index] if scroll_index < len(self.right_texts) else ""
            right2 = self.right_texts[scroll_index + 1] if scroll_index + 1 < len(self.right_texts) else ""
            right3 = self.right_texts[scroll_index + 2] if scroll_index + 2 < len(self.right_texts) else ""
            
            # Pre-render with cursor on line 2 (middle line)
            # Note: cursor_line 0 means active/selected
            frame_key = (scroll_index, 0)
            if frame_key not in self._frame_cache:
                frame = Image.new('1', (self.display_width, self.display_height), 0)
                draw = ImageDraw.Draw(frame)
                
                # Line 1 (inactive): normal text at y=3
                if line1:
                    draw.text((1, 3), line1, fill=1, font=self.font)
                    if right1:
                        bbox = draw.textbbox((0, 0), right1, font=self.font)
                        text_width = bbox[2] - bbox[0]
                        submenu_pad = 12 if self.submenus[scroll_index] else 0
                        text_x = max(1, self.display_width - text_width - 1 - submenu_pad)
                        draw.text((text_x, 3), right1, fill=1, font=self.font)
                    # Overlay >> for submenu items
                    if self.submenus[scroll_index]:
                        draw.text((self.display_width - 11, 3), ">>", fill=1, font=self.font)
                
                # Line 2 (active): inverted background with text at y=13
                if line2:
                    # Draw inverted background for active line (trimmed 1px top and bottom)
                    draw.rectangle([(0, 11), (self.display_width, 21)], fill=1)
                    # Draw text in black (inverted)
                    draw.text((1, 13), line2, fill=0, font=self.font)
                    if right2:
                        bbox = draw.textbbox((0, 0), right2, font=self.font)
                        text_width = bbox[2] - bbox[0]
                        submenu_pad = 12 if self.submenus[scroll_index + 1] else 0
                        text_x = max(1, self.display_width - text_width - 1 - submenu_pad)
                        draw.text((text_x, 13), right2, fill=0, font=self.font)
                    # Overlay >> for submenu items
                    if self.submenus[scroll_index + 1]:
                        draw.text((self.display_width - 11, 13), ">>", fill=0, font=self.font)
                
                # Line 3 (inactive): normal text at y=23
                if line3:
                    draw.text((1, 23), line3, fill=1, font=self.font)
                    if right3:
                        bbox = draw.textbbox((0, 0), right3, font=self.font)
                        text_width = bbox[2] - bbox[0]
                        submenu_pad = 12 if self.submenus[scroll_index + 2] else 0
                        text_x = max(1, self.display_width - text_width - 1 - submenu_pad)
                        draw.text((text_x, 23), right3, fill=1, font=self.font)
                    # Overlay >> for submenu items
                    if self.submenus[scroll_index + 2]:
                        draw.text((self.display_width - 11, 23), ">>", fill=1, font=self.font)
                
                # Cache the complete frame
                self._frame_cache[frame_key] = frame
        
        elapsed = time.perf_counter() - start_time
        logger.debug(f"Pre-rendered {len(self._frame_cache)} frames in {elapsed*1000:.1f}ms")
    
    def get_frame(self, scroll_index: int, cursor_line: Optional[int] = 0) -> Optional[Image.Image]:
        """
        Get a pre-rendered frame for the given scroll position.
        
        Args:
            scroll_index: Index of the first line in the menu
            cursor_line: Always 0 (cursor on top line), kept for compatibility
            
        Returns:
            Pre-rendered PIL Image, or None if not cached
        """
        # Clamp scroll_index to valid range (0 to len - 3)
        max_index = len(self.items) - 3
        if max_index < 0:
            max_index = 0
        clamped_index = max(0, min(scroll_index, max_index))
        return self._frame_cache.get((clamped_index, 0))
    
    def has_frame(self, scroll_index: int, cursor_line: Optional[int] = 0) -> bool:
        """
        Check if a frame is cached for the given scroll position.
        
        Args:
            scroll_index: Index of the first line in the menu
            cursor_line: Always 0 (cursor on top line), kept for compatibility
            
        Returns:
            True if frame is cached
        """
        # Clamp scroll_index to valid range (0 to len - 3)
        max_index = len(self.items) - 3
        if max_index < 0:
            max_index = 0
        clamped_index = max(0, min(scroll_index, max_index))
        return (clamped_index, 0) in self._frame_cache
    
    def get_item(self, index: int) -> str:
        """
        Get a menu item by index.
        
        Args:
            index: Index of the menu item
            
        Returns:
            Menu item string, or empty string if index out of range
        """
        return self.items[index] if 0 <= index < len(self.items) else ""
    
    def get_action(self, index: int) -> Optional[Callable]:
        """
        Get the action callback for a menu item by index.
        
        Args:
            index: Index of the menu item
            
        Returns:
            The action callback, or None if index out of range or no action defined
        """
        return self.actions[index] if 0 <= index < len(self.actions) else None
    
    def execute_action(self, index: int) -> bool:
        """
        Execute the action callback for a menu item by index.
        
        Args:
            index: Index of the menu item
            
        Returns:
            True if an action was executed, False otherwise
        """
        action = self.get_action(index)
        if action is not None:
            try:
                action()
                return True
            except Exception as e:
                logger.error(f"Error executing action for menu item {index}: {e}")
                return False
        return False
    
    def __len__(self) -> int:
        """Return the number of menu items."""
        return len(self.items)
