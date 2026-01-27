"""User settings persistence for runtime-editable configuration.

Manages user preferences like brightness levels and orientation,
initializing from config.py defaults and persisting changes to JSON.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from config import cfg

logger = logging.getLogger(__name__)


class UserSettings:
    """Manages persistent user settings with JSON storage."""
    
    DEFAULT_SETTINGS_PATH = Path(__file__).parent.parent / "config" / "user_settings.json"
    
    def __init__(self, settings_path: Optional[Path] = None):
        """Initialize user settings, loading from file or creating defaults.
        
        Args:
            settings_path: Path to settings JSON file (optional)
        """
        self.settings_path = settings_path or self.DEFAULT_SETTINGS_PATH
        self.settings: Dict[str, Any] = {}
        self._load_or_create()
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Get default settings from config.py.
        
        Returns:
            Dictionary of default settings
        """
        return {
            "display_brightness": 180,  # Default OLED contrast
            "led_brightness": 255,       # Default LED brightness (full)
            "orientation": "left",       # Default orientation (knob on left)
        }
    
    def _load_or_create(self):
        """Load settings from file or create with defaults."""
        if self.settings_path.exists():
            try:
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
                logger.info(f"Loaded user settings from {self.settings_path}")
            except Exception as e:
                logger.error(f"Failed to load settings, using defaults: {e}")
                self.settings = self._get_defaults()
        else:
            logger.info("No user settings file found, creating with defaults")
            self.settings = self._get_defaults()
            self._save()
    
    def _save(self):
        """Save settings to JSON file."""
        try:
            # Ensure config directory exists
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
            logger.debug(f"Saved user settings to {self.settings_path}")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value.
        
        Args:
            key: Setting key
            default: Default value if key doesn't exist
            
        Returns:
            Setting value or default
        """
        return self.settings.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set a setting value and persist to disk.
        
        Args:
            key: Setting key
            value: Setting value
        """
        self.settings[key] = value
        self._save()
    
    def get_display_brightness(self) -> int:
        """Get display brightness (0-255)."""
        return self.get("display_brightness", 180)
    
    def set_display_brightness(self, value: int):
        """Set display brightness (0-255)."""
        value = max(0, min(255, value))  # Clamp to valid range
        self.set("display_brightness", value)
    
    def get_led_brightness(self) -> int:
        """Get LED brightness (0-255)."""
        return self.get("led_brightness", 255)
    
    def set_led_brightness(self, value: int):
        """Set LED brightness (0-255)."""
        value = max(0, min(255, value))  # Clamp to valid range
        self.set("led_brightness", value)
    
    def get_orientation(self) -> str:
        """Get display orientation ('left' or 'right')."""
        return self.get("orientation", "left")
    
    def set_orientation(self, value: str):
        """Set display orientation ('left' or 'right')."""
        if value in ["left", "right"]:
            self.set("orientation", value)
        else:
            logger.warning(f"Invalid orientation value: {value}")


# Global settings instance
user_settings = UserSettings()
