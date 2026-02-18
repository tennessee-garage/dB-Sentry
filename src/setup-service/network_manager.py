"""Network management utilities for WiFi AP mode and scanning."""
import subprocess
import os
import time
from typing import List, Dict, Optional
from config_manager import ConfigManager


class NetworkManager:
    """Manages WiFi access point mode and network scanning."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.ap_active = False
        self.previous_connection_name: Optional[str] = None
        self.web_port = 5000

    def _set_captive_http_redirect(self, interface: str) -> None:
        """Redirect AP HTTP traffic (port 80) to the setup service port."""
        ap_ip = str(self.config.get('ap_ip', '192.168.4.1'))
        redirect_port = str(self.web_port)

        subprocess.run([
            'sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING',
            '-i', interface,
            '-p', 'tcp',
            '--dport', '80',
            '-j', 'DNAT',
            '--to-destination', f'{ap_ip}:{redirect_port}'
        ], capture_output=True)

        subprocess.run([
            'sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING',
            '-i', interface,
            '-p', 'tcp',
            '--dport', '80',
            '-j', 'DNAT',
            '--to-destination', f'{ap_ip}:{redirect_port}'
        ], capture_output=True)

    def _clear_captive_http_redirect(self, interface: str) -> None:
        """Remove AP HTTP redirect rule if present."""
        ap_ip = str(self.config.get('ap_ip', '192.168.4.1'))
        redirect_port = str(self.web_port)

        subprocess.run([
            'sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING',
            '-i', interface,
            '-p', 'tcp',
            '--dport', '80',
            '-j', 'DNAT',
            '--to-destination', f'{ap_ip}:{redirect_port}'
        ], capture_output=True)

    def get_ip_address(self) -> Optional[str]:
        """Get the current IP address for the AP interface."""
        interface: str = str(self.config.get('ap_interface', 'wlan0'))
        try:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', interface],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('inet '):
                    return line.split()[1].split('/')[0]
            return None
        except Exception as e:
            print(f"Error reading IP address: {e}")
            return None
        
    def scan_wifi_networks(self) -> List[Dict[str, str]]:
        """Scan for available WiFi networks."""
        interface: str = str(self.config.get('ap_interface', 'wlan0'))
        try:
            # Use nmcli to scan for networks
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                # Fallback to iwlist if nmcli fails
                return self._scan_with_iwlist(interface)
            
            networks = []
            seen_ssids = set()
            
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) >= 3:
                    ssid = parts[0].strip()
                    if ssid and ssid not in seen_ssids:
                        signal = parts[1].strip()
                        security = parts[2].strip()
                        networks.append({
                            'ssid': ssid,
                            'signal': signal,
                            'security': security if security else 'Open'
                        })
                        seen_ssids.add(ssid)
            
            # Sort by signal strength
            networks.sort(key=lambda x: int(x['signal']) if x['signal'].isdigit() else 0, reverse=True)
            return networks
            
        except Exception as e:
            print(f"Error scanning WiFi: {e}")
            return []
    
    def _scan_with_iwlist(self, interface: str) -> List[Dict[str, str]]:
        """Fallback WiFi scan using iwlist."""
        try:
            result = subprocess.run(
                ['sudo', 'iwlist', interface, 'scan'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            networks = []
            current_network = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if 'ESSID:' in line:
                    ssid = line.split('ESSID:')[1].strip('"')
                    if ssid:
                        current_network['ssid'] = ssid
                elif 'Quality=' in line:
                    parts = line.split()
                    for part in parts:
                        if 'Quality=' in part:
                            quality = part.split('=')[1].split('/')[0]
                            current_network['signal'] = quality
                elif 'Encryption key:' in line:
                    if 'on' in line:
                        current_network['security'] = 'Secured'
                    else:
                        current_network['security'] = 'Open'
                    if 'ssid' in current_network:
                        networks.append(current_network.copy())
                        current_network = {}
            
            return networks
        except Exception as e:
            print(f"Error with iwlist scan: {e}")
            return []
    
    def start_ap_mode(self) -> bool:
        """Start access point mode."""
        try:
            interface: str = str(self.config.get('ap_interface', 'wlan0'))
            ssid: str = str(self.config.get('ap_ssid', 'DB-Sentry-Setup'))
            password: str = str(self.config.get('ap_password', 'not-too-loud'))

            # Capture the active connection on this interface so we can restore it later
            self.previous_connection_name = self._get_active_connection_name(interface)
            
            # Create hostapd configuration
            hostapd_conf = f"""interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={self.config.get('ap_channel', 6)}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
            
            with open('hostapd.conf', 'w') as f:
                f.write(hostapd_conf)
            
            # Create dnsmasq configuration with captive portal support
            ap_ip = str(self.config.get('ap_ip', '192.168.4.1'))
            dnsmasq_conf = f"""interface={interface}
dhcp-range={self.config.get('dhcp_range_start', '192.168.4.2')},{self.config.get('dhcp_range_end', '192.168.4.20')},255.255.255.0,24h
domain=wlan
# Captive portal - redirect all DNS queries to our AP
address=/#/{ap_ip}
"""
            
            with open('dnsmasq.conf', 'w') as f:
                f.write(dnsmasq_conf)
            
            # Stop NetworkManager from managing the interface
            subprocess.run(['sudo', 'nmcli', 'dev', 'set', interface, 'managed', 'no'], 
                         capture_output=True)
            
            # Configure interface
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'], 
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', interface], 
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'addr', 'add', 
                          f"{self.config.get('ap_ip', '192.168.4.1')}/24", 
                          'dev', interface], 
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], 
                         capture_output=True)

            self._set_captive_http_redirect(interface)
            
            # Start dnsmasq
            subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], 
                         capture_output=True)
            subprocess.run(['sudo', 'dnsmasq', '-C', 'dnsmasq.conf'], 
                         capture_output=True)
            
            # Start hostapd
            subprocess.Popen(['sudo', 'hostapd', 'hostapd.conf'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            
            time.sleep(2)
            self.ap_active = True
            print(f"AP mode started: {ssid}")
            return True
            
        except Exception as e:
            print(f"Error starting AP mode: {e}")
            return False
    
    def stop_ap_mode(self) -> bool:
        """Stop access point mode."""
        try:
            interface: str = str(self.config.get('ap_interface', 'wlan0'))
            
            # Stop hostapd and dnsmasq
            subprocess.run(['sudo', 'pkill', 'hostapd'], capture_output=True)
            subprocess.run(['sudo', 'pkill', 'dnsmasq'], capture_output=True)

            self._clear_captive_http_redirect(interface)
            
            # Reset interface
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'], 
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', interface], 
                         capture_output=True)
            
            # Re-enable NetworkManager management
            subprocess.run(['sudo', 'nmcli', 'dev', 'set', interface, 'managed', 'yes'], 
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'up'], 
                         capture_output=True)
            
            self.ap_active = False
            print("AP mode stopped")
            return True
            
        except Exception as e:
            print(f"Error stopping AP mode: {e}")
            return False
    
    def connect_to_wifi(self, ssid: str, password: str) -> bool:
        """Connect to a WiFi network."""
        try:
            # Remove existing connection if it exists
            subprocess.run(['sudo', 'nmcli', 'con', 'delete', ssid], 
                         capture_output=True)
            
            # Create new connection
            result = subprocess.run(
                ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print(f"Connected to {ssid}")
                return True
            else:
                print(f"Failed to connect: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error connecting to WiFi: {e}")
            return False

    def restore_previous_connection(self) -> bool:
        """Restore the previous active connection if known."""
        if not self.previous_connection_name:
            print("No previous connection to restore")
            return False
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'con', 'up', self.previous_connection_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print(f"Restored connection: {self.previous_connection_name}")
                return True
            print(f"Failed to restore connection: {result.stderr}")
            return False
        except Exception as e:
            print(f"Error restoring connection: {e}")
            return False

    def _get_active_connection_name(self, interface: str) -> Optional[str]:
        """Get the active NetworkManager connection name for the interface."""
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME,DEVICE', 'con', 'show', '--active'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) == 2:
                    name, device = parts
                    if device == interface:
                        return name
            return None
        except Exception as e:
            print(f"Error reading active connection: {e}")
            return None
