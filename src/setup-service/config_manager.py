"""Configuration manager for DB-Sentry setup service."""
import json
import os
from typing import Dict, Any, Optional

CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "ap_ssid": "DB-Sentry-Setup",
    "ap_password": "not-too-loud",
    "ap_interface": "wlan0",
    "ap_channel": 6,
    "ap_ip": "192.168.4.1",
    "ap_netmask": "255.255.255.0",
    "dhcp_range_start": "192.168.4.2",
    "dhcp_range_end": "192.168.4.20"
}


class ConfigManager:
    """Manages configuration settings for the setup service."""
    
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                return DEFAULT_CONFIG.copy()
        else:
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
    
    def save_config(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Save configuration to file."""
        if config is None:
            config = self.config
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get(self, key: str, default=None):
        """Get a configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """Set a configuration value and save."""
        self.config[key] = value
        return self.save_config()
    
    def update(self, updates: Dict[str, Any]) -> bool:
        """Update multiple configuration values."""
        self.config.update(updates)
        return self.save_config()
