"""System information collectors for menu display.

Provides functions to gather network, system, and service information
with appropriate fallback text for error conditions.
"""

import subprocess
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


def _safe_execute(func: Callable[[], str], fallback: str) -> str:
    """Safely execute a function with error handling.
    
    Args:
        func: Function that returns a string value
        fallback: Value to return if function fails
        
    Returns:
        Function result or fallback value
    """
    try:
        return func()
    except Exception as e:
        logger.debug(f"Error: {e}")
        return fallback


def get_wifi_ssid() -> str:
    """Get the current WiFi SSID.
    
    Returns:
        SSID name or "Not connected" if unavailable
    """
    def _get_ssid():
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
    
    return _safe_execute(_get_ssid, "Not connected")


def get_ip_address() -> str:
    """Get the current IP address.
    
    Returns:
        IP address or "No IP" if unavailable
    """
    def _get_ip():
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
    
    return _safe_execute(_get_ip, "No IP")


def get_uptime() -> str:
    """Get system uptime formatted as 'Xh Ym Zs'.
    
    Returns:
        Formatted uptime or "Unknown" if unavailable
    """
    def _get_uptime():
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return f"{hours}h {minutes}m {seconds}s"
    
    return _safe_execute(_get_uptime, "Unknown")


def get_service_status() -> str:
    """Get the status of the db-sentry-limit service.
    
    Returns:
        Service status (active/inactive/failed) or "Unavailable"
    """
    def _get_status():
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
    
    return _safe_execute(_get_status, "Unavailable")


def get_load_average() -> str:
    """Get system load averages (1m / 5m / 15m).
    
    Returns:
        Load averages formatted as "X.XX / Y.YY / Z.ZZ" or "N/A"
    """
    def _get_load():
        with open("/proc/loadavg", "r") as f:
            load_data = f.read().split()[:3]
        
        if len(load_data) >= 3:
            return f"{load_data[0]}/{load_data[1]}/{load_data[2]}"
        
        return "N/A"
    
    return _safe_execute(_get_load, "N/A")
