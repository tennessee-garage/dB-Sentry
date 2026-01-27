"""System information collectors for menu display.

Provides functions to gather network, system, and service information
with appropriate fallback text for error conditions.
"""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_wifi_ssid() -> str:
    """Get the current WiFi SSID.
    
    Returns:
        SSID name or "Not connected" if unavailable
    """
    try:
        # Try iwgetid first (common on Raspberry Pi)
        result = subprocess.run(
            ["iwgetid", "-r"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        
        # Fallback to nmcli if available
        result = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("yes:"):
                    return line.split(":", 1)[1]
        
        return "Not connected"
    except Exception as e:
        logger.debug(f"Failed to get WiFi SSID: {e}")
        return "Not connected"


def get_ip_address() -> str:
    """Get the current IP address.
    
    Returns:
        IP address or "No IP" if unavailable
    """
    try:
        # Get hostname -I output
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return first IP address (usually the primary one)
            ips = result.stdout.strip().split()
            if ips:
                return ips[0]
        
        return "No IP"
    except Exception as e:
        logger.debug(f"Failed to get IP address: {e}")
        return "No IP"


def get_uptime() -> str:
    """Get system uptime formatted as 'Xh Ym Zs'.
    
    Returns:
        Formatted uptime or "Unknown" if unavailable
    """
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return f"{hours}h {minutes}m {seconds}s"
    except Exception as e:
        logger.debug(f"Failed to get uptime: {e}")
        return "Unknown"


def get_service_status() -> str:
    """Get the status of the db-sentry-limit service.
    
    Returns:
        Service status (active/inactive/failed) or "Unavailable"
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "db-sentry-limit.service"],
            capture_output=True,
            text=True,
            timeout=2
        )
        status = result.stdout.strip()
        
        # Map systemctl output to friendly names
        status_map = {
            "active": "Active",
            "inactive": "Inactive",
            "failed": "Failed",
            "activating": "Starting",
            "deactivating": "Stopping"
        }
        
        return status_map.get(status, status.capitalize() if status else "Unavailable")
    except Exception as e:
        logger.debug(f"Failed to get service status: {e}")
        return "Unavailable"


def get_load_average() -> str:
    """Get system load averages (1m / 5m / 15m).
    
    Returns:
        Load averages formatted as "X.XX / Y.YY / Z.ZZ" or "N/A"
    """
    try:
        with open("/proc/loadavg", "r") as f:
            load_data = f.read().split()[:3]
        
        if len(load_data) >= 3:
            return f"{load_data[0]} / {load_data[1]} / {load_data[2]}"
        
        return "N/A"
    except Exception as e:
        logger.debug(f"Failed to get load average: {e}")
        return "N/A"
