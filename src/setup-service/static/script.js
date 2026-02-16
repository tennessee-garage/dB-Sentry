// DB-Sentry Setup - Client-side JavaScript

let selectedSSID = null;
let sensorCheckInterval = null;

// DOM Elements
const scanBtn = document.getElementById('scan-btn');
const loading = document.getElementById('loading');
const networkList = document.getElementById('network-list');
const wifiPassword = document.getElementById('wifi-password');
const togglePassword = document.getElementById('toggle-password');
const submitWifi = document.getElementById('submit-wifi');
const backToNetworks = document.getElementById('back-to-networks');
const finishSetup = document.getElementById('finish-setup');
const errorMessage = document.getElementById('error-message');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('DB-Sentry Setup initialized');
    
    // Event listeners
    scanBtn.addEventListener('click', scanNetworks);
    togglePassword.addEventListener('click', togglePasswordVisibility);
    submitWifi.addEventListener('click', submitWiFiConfig);
    backToNetworks.addEventListener('click', () => showStep(1));
    finishSetup.addEventListener('click', completeSetup);
});

// Show specific step
function showStep(stepNumber) {
    document.querySelectorAll('.step').forEach(step => {
        step.classList.remove('active');
    });
    document.getElementById(`step-${stepNumber}`).classList.add('active');
    
    // Start sensor polling when on step 3
    if (stepNumber === 3) {
        startSensorPolling();
    } else {
        stopSensorPolling();
    }
}

// Scan for WiFi networks
async function scanNetworks() {
    scanBtn.disabled = true;
    loading.classList.remove('hidden');
    networkList.classList.add('hidden');
    networkList.innerHTML = '';
    hideError();
    
    try {
        const response = await fetch('/api/scan-networks');
        const data = await response.json();
        
        if (data.success && data.networks.length > 0) {
            displayNetworks(data.networks);
        } else {
            showError('No networks found. Please try again.');
        }
    } catch (error) {
        console.error('Error scanning networks:', error);
        showError('Failed to scan networks. Please try again.');
    } finally {
        loading.classList.add('hidden');
        scanBtn.disabled = false;
    }
}

// Display network list
function displayNetworks(networks) {
    networkList.innerHTML = '<h3>Available Networks</h3>';
    
    networks.forEach(network => {
        const networkItem = document.createElement('div');
        networkItem.className = 'network-item';
        networkItem.onclick = () => selectNetwork(network.ssid);
        
        const signalIcon = getSignalIcon(network.signal);
        const securityIcon = network.security !== 'Open' ? '🔒' : '🔓';
        
        networkItem.innerHTML = `
            <div class="network-info">
                <div class="network-ssid">${escapeHtml(network.ssid)}</div>
                <div class="network-details">${securityIcon} ${network.security}</div>
            </div>
            <div class="signal-strength">${signalIcon}</div>
        `;
        
        networkList.appendChild(networkItem);
    });
    
    networkList.classList.remove('hidden');
}

// Select a network
function selectNetwork(ssid) {
    selectedSSID = ssid;
    document.getElementById('selected-ssid').textContent = ssid;
    wifiPassword.value = '';
    showStep(2);
}

// Toggle password visibility
function togglePasswordVisibility() {
    const type = wifiPassword.type === 'password' ? 'text' : 'password';
    wifiPassword.type = type;
    togglePassword.textContent = type === 'password' ? '👁️' : '🙈';
}

// Submit WiFi configuration
async function submitWiFiConfig() {
    const password = wifiPassword.value;
    
    if (!password) {
        showError('Please enter a password');
        return;
    }
    
    submitWifi.disabled = true;
    hideError();
    
    try {
        const response = await fetch('/api/configure-wifi', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ssid: selectedSSID,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('configured-ssid').textContent = selectedSSID;
            showStep(3);
        } else {
            showError(data.message || 'Failed to configure WiFi');
        }
    } catch (error) {
        console.error('Error configuring WiFi:', error);
        showError('Failed to configure WiFi. Please try again.');
    } finally {
        submitWifi.disabled = false;
    }
}

// Start polling for connected sensors
function startSensorPolling() {
    // Initial check
    checkSensors();
    
    // Poll every 2 seconds
    sensorCheckInterval = setInterval(checkSensors, 2000);
}

// Stop polling for sensors
function stopSensorPolling() {
    if (sensorCheckInterval) {
        clearInterval(sensorCheckInterval);
        sensorCheckInterval = null;
    }
}

// Check for connected sensors
async function checkSensors() {
    try {
        const response = await fetch('/api/sensors');
        const data = await response.json();
        
        if (data.sensors && data.sensors.length > 0) {
            displaySensors(data.sensors);
        }
    } catch (error) {
        console.error('Error checking sensors:', error);
    }
}

// Display connected sensors
function displaySensors(sensors) {
    const container = document.getElementById('sensors-container');
    container.innerHTML = '';
    
    sensors.forEach(sensor => {
        const sensorItem = document.createElement('div');
        sensorItem.className = 'sensor-item';
        
        const time = new Date(sensor.connected_at).toLocaleTimeString();
        
        sensorItem.innerHTML = `
            <div class="sensor-name">✅ ${escapeHtml(sensor.name)}</div>
            <div class="sensor-time">Connected at ${time}</div>
        `;
        
        container.appendChild(sensorItem);
    });
}

// Complete setup
async function completeSetup() {
    finishSetup.disabled = true;
    hideError();
    
    try {
        const response = await fetch('/api/stop-ap', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            const sensorCount = document.querySelectorAll('.sensor-item').length;
            document.getElementById('final-ssid').textContent = selectedSSID;
            document.getElementById('sensor-count').textContent = sensorCount;
            showStep(4);
            stopSensorPolling();
        } else {
            showError(data.message || 'Failed to complete setup');
            finishSetup.disabled = false;
        }
    } catch (error) {
        console.error('Error completing setup:', error);
        showError('Failed to complete setup. Please try again.');
        finishSetup.disabled = false;
    }
}

// Utility: Get signal strength icon
function getSignalIcon(signal) {
    const strength = parseInt(signal) || 0;
    if (strength >= 70) return '📶';
    if (strength >= 50) return '📶';
    if (strength >= 30) return '📡';
    return '📉';
}

// Utility: Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Show error message
function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove('hidden');
    setTimeout(() => {
        errorMessage.classList.add('hidden');
    }, 5000);
}

// Hide error message
function hideError() {
    errorMessage.classList.add('hidden');
}
