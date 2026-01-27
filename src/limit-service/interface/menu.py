"""Menu system for OLED display.

Handles menu item storage and pre-rendering for optimal performance.
"""
import time
import logging
from typing import List, Dict, Tuple, Optional, Callable, Union
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


# Type alias for menu items: can be a string or a dict with 'text' and 'action'
MenuItem = Union[str, Dict[str, Union[str, Callable]]]


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
        self.raw_items = items
        self.items = [self._get_text(item) for item in items]
        self.actions = [self._get_action(item) for item in items]
        self.display_width = display_width
        self.display_height = display_height
        
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
    
    def _prerender_frames(self) -> None:
        """Pre-render all possible frame buffers for the menu."""
        logger.info(f"Pre-rendering {len(self.items)} menu items...")
        start_time = time.perf_counter()
        
        # Pre-render all possible two-line combinations with all cursor positions
        for scroll_index in range(len(self.items)):
            line1 = self.items[scroll_index] if scroll_index < len(self.items) else ""
            line2 = self.items[scroll_index + 1] if scroll_index + 1 < len(self.items) else ""
            
            # Pre-render with cursor on line 1, line 2, and no cursor
            for cursor_line in [0, 1, None]:
                frame_key = (scroll_index, cursor_line)
                if frame_key in self._frame_cache:
                    continue
                
                # Create a full frame with these two lines
                frame = Image.new('1', (self.display_width, self.display_height), 0)
                draw = ImageDraw.Draw(frame)
                
                if line1:
                    prefix1 = "> " if cursor_line == 0 else "  "
                    draw.text((4, 4), prefix1 + line1, fill=1)
                if line2:
                    prefix2 = "> " if cursor_line == 1 else "  "
                    draw.text((4, 16), prefix2 + line2, fill=1)
                
                # Cache the complete frame
                self._frame_cache[frame_key] = frame
        
        elapsed = time.perf_counter() - start_time
        logger.info(f"Pre-rendered {len(self._frame_cache)} frames in {elapsed*1000:.1f}ms")
    
    def get_frame(self, scroll_index: int, cursor_line: Optional[int] = None) -> Optional[Image.Image]:
        """
        Get a pre-rendered frame for the given two lines with optional cursor.
        
        Args:
            scroll_index: Index of the first line in the menu
            cursor_line: Which line has the cursor (0=first, 1=second, None=no cursor)
            
        Returns:
            Pre-rendered PIL Image, or None if not cached
        """
        return self._frame_cache.get((scroll_index, cursor_line))
    
    def has_frame(self, scroll_index: int, cursor_line: Optional[int] = None) -> bool:
        """
        Check if a frame is cached for the given two lines with cursor position.
        
        Args:
            line1: First line of text
            line2: Second line of text
            cursor_line: Which line has the cursor (0=first, 1=second, None=no cursor)
            
        Returns:
            True if frame is cached
        """
        return (scroll_index, cursor_line) in self._frame_cache
    
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
