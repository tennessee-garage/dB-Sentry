"""API client for limit-service.

Provides functions to fetch and update sensor limits from the limit-service web API.
"""

import logging
import urllib.request
import urllib.parse
import json
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LimitServiceAPI:
    """Client for limit-service API."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the API client.
        
        Args:
            base_url: Base URL of the limit-service (default: http://localhost:8000)
        """
        self.base_url = base_url.rstrip('/')
    
    def get_limits(self) -> Dict[str, float]:
        """Fetch current sensor limits from the API.
        
        Returns:
            Dictionary mapping sensor names to their threshold limits.
            Returns empty dict on error.
        """
        try:
            url = f"{self.base_url}/api/limits"
            with urllib.request.urlopen(url, timeout=2) as response:
                data = json.loads(response.read().decode('utf-8'))
                logger.info(f"Fetched limits from API: {data}")
                return data
        except Exception as e:
            logger.error(f"Failed to fetch sensor limits: {e}")
            return {}
    
    def get_window_seconds(self) -> Optional[int]:
        """Fetch current window_seconds setting from the API.
        
        Returns:
            Current window_seconds value, or None on error.
        """
        try:
            url = f"{self.base_url}/api/window_seconds"
            with urllib.request.urlopen(url, timeout=2) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('window_seconds')
        except Exception as e:
            logger.error(f"Failed to fetch window_seconds: {e}")
            return None
    
    def update_limit(self, sensor_name: str, limit: float) -> bool:
        """Update the threshold limit for a specific sensor.
        
        Args:
            sensor_name: Name of the sensor
            limit: New threshold limit value
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/limits"
            # Send as JSON payload
            data = {sensor_name: limit}
            json_data = json.dumps(data).encode('utf-8')
            
            logger.info(f"Updating limit for {sensor_name} to {limit}")
            logger.info(f"POST JSON: {json.dumps(data)}")
            
            req = urllib.request.Request(url, data=json_data, method='POST')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=2) as response:
                status = response.getcode()
                response_body = response.read().decode('utf-8')
                logger.info(f"Update limit response status: {status}")
                logger.info(f"Response body: {response_body[:200]}")  # First 200 chars
                # urllib follows redirects automatically, so we'll see 200 after the redirect
                return status == 200
        except Exception as e:
            logger.error(f"Failed to update limit for {sensor_name}: {e}")
            return False
