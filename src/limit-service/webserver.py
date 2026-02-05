from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
from influx_client import create_influx_client
import uvicorn
import threading
import logging

from typing import Dict, Optional, Any

logger = logging.getLogger('limit-service.webserver')

app = FastAPI()
influx = create_influx_client()

# Signals to main loop that configuration has changed
limits_changed_event: Optional[threading.Event] = None
window_seconds_changed_event: Optional[threading.Event] = None
monitor_ref: Optional[Any] = None  # Reference to Monitor object from main.py

def set_limits_changed_event(event: threading.Event):
	"""Called by main.py to register the event for signaling limit changes."""
	global limits_changed_event
	limits_changed_event = event

def set_window_seconds_changed_event(event: threading.Event):
	"""Called by main.py to register the event for signaling window_seconds changes."""
	global window_seconds_changed_event
	window_seconds_changed_event = event

def set_monitor(monitor: Any):
	"""Called by main.py to register the monitor object for sensor queries."""
	global monitor_ref
	monitor_ref = monitor

INDEX_HTML = """
<!doctype html>
<html>
  <head>
	<meta charset="utf-8">
	<title>Limit Service</title>
	<script>
	  async function loadLimits() {
		try {
		  const limitsResp = await fetch('/api/limits');
		  const limits = await limitsResp.json();
		  
		  const windowResp = await fetch('/api/window_seconds');
		  const windowData = await windowResp.json();
		  
		  document.getElementById('window_seconds').value = windowData.window_seconds;
		  
		  const container = document.getElementById('limits-container');
		  container.innerHTML = '';
		  
		  if (Object.keys(limits).length === 0) {
			container.innerHTML = '<p>No sensor limits configured yet.</p>';
		  } else {
			for (const [sensor, value] of Object.entries(limits)) {
			  const div = document.createElement('div');
			  const label = document.createElement('label');
			  const input = document.createElement('input');
			  input.type = 'text';
			  input.name = sensor;
			  input.value = value;
			  label.appendChild(document.createTextNode(sensor + ': '));
			  label.appendChild(input);
			  div.appendChild(label);
			  container.appendChild(div);
			}
		  }
		} catch (error) {
		  console.error('Error loading limits:', error);
		}
	  }
	  
	  window.addEventListener('load', loadLimits);
	  
	  async function handleSubmit(event) {
		event.preventDefault();
		const formData = new FormData(event.target);
		const data = {};
		
		for (const [key, value] of formData.entries()) {
		  if (value !== '') {
			data[key] = isNaN(value) ? value : parseFloat(value);
		  }
		}
		
		try {
		  const response = await fetch('/limits', {
			method: 'POST',
			headers: {
			  'Content-Type': 'application/json'
			},
			body: JSON.stringify(data)
		  });
		  
		  if (response.ok) {
			loadLimits();
		  } else {
			console.error('Error updating limits');
		  }
		} catch (error) {
		  console.error('Error submitting limits:', error);
		}
	  }
	</script>
  </head>
  <body>
	<h1>Sensor Limits</h1>
	  <div>
		<label>Lookback window in seconds: <input type="text" id="window_seconds" name="window_seconds"/></label>
	  </div>
	  <hr/>
	<form onsubmit="handleSubmit(event)">
	  <div id="limits-container">
		<p>Loading...</p>
	  </div>
	  <button type="submit">Save</button>
	</form>
  </body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
	"""Serve the main UI page."""
	return INDEX_HTML

@app.get("/api/limits")
async def get_limits():
	"""Get all sensor limits as JSON.
	
	Returns only sensors that have active data or configured limits.
	"""
	active = influx.read_active_sensors()
	limits = influx.read_sensor_limits()
	
	result = {}
	for sensor in active:
		result[sensor] = limits.get(sensor, 0)
	
	return result

@app.get("/api/window_seconds")
async def get_window_seconds():
	"""Get the current window seconds setting."""
	try:
		window_seconds = influx.read_window_seconds()
	except Exception:
		window_seconds = 30
	
	return {"window_seconds": window_seconds}

@app.get("/api/sensor")
async def get_sensors():
	"""Get a list of all currently active sensor names.
	
	Returns:
		JSON array of sensor names that have recent data in the monitor
	"""
	if monitor_ref is None:
		return {"error": "Monitor not available"}, 503
	
	# Get all sensors from the monitor's sensor_averages (filters out stale sensors)
	sensors = list(monitor_ref.sensor_averages().keys())
	
	return {"sensors": sensors}

@app.get("/api/sensor/{sensor_name}")
async def get_sensor_current_reading(sensor_name: str):
	"""Get the most recent dBA reading for a specific sensor.
	
	Args:
		sensor_name: Name of the sensor to query
		
	Returns:
		JSON with sensor name, current reading (max across bands), average, timestamp,
		and measurements per second
		Returns 404 if sensor not found or has no recent data
	"""
	if monitor_ref is None:
		return {"error": "Monitor not available"}, 503
	
	# Check if sensor exists and has data
	if sensor_name not in monitor_ref.sensors:
		return {"error": f"Sensor '{sensor_name}' not found"}, 404
	
	bands = monitor_ref.sensors[sensor_name]
	
	# Get the most recent reading across all bands
	most_recent_time = 0
	most_recent_value = None
	
	for band, window in bands.items():
		if len(window.dq) > 0:
			timestamp, value = window.dq[-1]  # Last item is most recent
			if timestamp > most_recent_time:
				most_recent_time = timestamp
				most_recent_value = value
	
	if most_recent_value is None:
		return {"error": f"Sensor '{sensor_name}' has no recent data"}, 404
	
	# Also get the max average across bands (similar to check_alerts logic)
	max_avg = max(band.average() for band in bands.values())
	
	# Calculate measurements per second
	total_readings = 0
	for window in bands.values():
		total_readings += len(window.dq)
	
	measurements_per_second = total_readings / monitor_ref.window_seconds if monitor_ref.window_seconds > 0 else 0
	
	return {
		"sensor": sensor_name,
		"current_reading": most_recent_value,
		"average": max_avg,
		"timestamp": most_recent_time,
		"measurements_per_second": measurements_per_second
	}

@app.post("/limits")
async def update_limits(request: Request):
	"""Update sensor limits and/or window_seconds from JSON payload.
	
	Expects JSON with sensor names as keys and numeric limits as values.
	Optional 'window_seconds' key to update the monitoring window.
	
	Example: {"sensor1": 50, "sensor2": 75, "window_seconds": 60}
	"""
	try:
		data = await request.json()
	except Exception as e:
		logger.error(f"Error parsing JSON: {e}")
		return {"error": "Invalid JSON"}
	
	# Separate window_seconds from sensor limits
	window_seconds = data.pop('window_seconds', None)
	updated_sensors = {}
	
	# Process sensor limits
	for sensor, limit in data.items():
		try:
			updated_sensors[sensor] = int(float(limit))
		except (ValueError, TypeError):
			logger.warning(f"Invalid limit value for {sensor}: {limit}")
			continue
	
	# Update sensors
	if updated_sensors:
		logger.info(f"Updating {len(updated_sensors)} sensor limit(s)")
		for sensor, limit in updated_sensors.items():
			influx.set_sensor_limit(sensor, limit)
		# Signal main loop to refresh sensor limits
		if limits_changed_event:
			limits_changed_event.set()
	
	# Update window_seconds if provided
	if window_seconds is not None:
		try:
			ws_val = int(float(window_seconds))
			logger.info(f"Updating window_seconds to {ws_val}")
			influx.set_window_seconds(ws_val)
			# Signal main loop to refresh window_seconds
			if window_seconds_changed_event:
				window_seconds_changed_event.set()
		except (ValueError, TypeError):
			logger.warning(f"Invalid window_seconds value: {window_seconds}")
	
	return {"status": "ok"}

def run(host='0.0.0.0', port=8000):
	uvicorn.run(app, host=host, port=port)

# run in background thread helper
def run_in_thread(host='0.0.0.0', port=8000):
	t = threading.Thread(target=run, kwargs={'host':host, 'port':port}, daemon=True)
	t.start()
