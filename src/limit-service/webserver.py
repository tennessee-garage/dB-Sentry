from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template
from influx_client import create_influx_client
import uvicorn
import threading
import logging

from typing import Dict, Optional

logger = logging.getLogger('limit-service.webserver')

app = FastAPI()
influx = create_influx_client()

# Signals to main loop that configuration has changed
limits_changed_event: Optional[threading.Event] = None
window_seconds_changed_event: Optional[threading.Event] = None

def set_limits_changed_event(event: threading.Event):
	"""Called by main.py to register the event for signaling limit changes."""
	global limits_changed_event
	limits_changed_event = event

def set_window_seconds_changed_event(event: threading.Event):
	"""Called by main.py to register the event for signaling window_seconds changes."""
	global window_seconds_changed_event
	window_seconds_changed_event = event

INDEX_HTML = """
<!doctype html>
<html>
  <head>
	<meta charset="utf-8">
	<title>Limit Service</title>
  </head>
  <body>
	<h1>Sensor Limits</h1>
	  <div>
		<label>Lookback window in seconds: <input type="text" name="window_seconds" value="{{ window_seconds }}"/></label>
	  </div>
	  <hr/>
	<form method="post" action="/limits">
	  {% if limits %}
		{% for sensor, value in limits.items() %}
		  <div>
			<label>{{ sensor }}: <input type="text" name="{{ sensor }}" value="{{ value }}"/></label>
		  </div>
		{% endfor %}
	  {% else %}
		<p>No sensor limits configured yet.</p>
	  {% endif %}
	  <button type="submit">Save</button>
	</form>
  </body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
	# Fetch the active sensors, and any configured limits.  Merge them to show
	# the limits for all active sensors, defaulting to zero if there is no limit set.
	active = influx.read_active_sensors()
	limits = influx.read_sensor_limits()
	active_limits: Dict[str, int] = {}
	
	for sensor in active:
		if sensor not in limits:
			active_limits[sensor] = 0
		else:
			active_limits[sensor] = limits[sensor]

	try:
		window_seconds = influx.read_window_seconds()
	except Exception:
		window_seconds = 30
	template = Template(INDEX_HTML)
	return template.render(limits=active_limits, window_seconds=window_seconds)

@app.post("/limits")
async def update_limits(request: Request):
	form = await request.form()
	# process each form field; treat 'window_seconds' specially
	updated: Dict[str, int] = {}
	for key, val in form.items():
		if val is None or not isinstance(val, str) or val == "":
			continue
		if key == 'window_seconds':
			# handle later
			continue
		try:
			updated[key] = int(val)
		except ValueError:
			# ignore invalid numeric entries
			updated[key] = 0
			continue

	if updated:
		logger.info(f"Updating {len(updated)} sensor limit(s)")
		# Signal main loop to refresh sensor limits
		if limits_changed_event:
			limits_changed_event.set()
	else:
		logger.info("No sensor limits to update")

	# persist updated limits via the influx client's set_sensor_limit (v1) or write
	for sensor, limit in updated.items():
		influx.set_sensor_limit(sensor, int(limit))

	# window_seconds handling
	ws = form.get('window_seconds')
	if isinstance(ws, str) and ws != "":
		ws_val = int(ws)
		logger.info(f"Updating window_seconds to {ws_val}")
		influx.set_window_seconds(ws_val)
		# Signal main loop to refresh window_seconds
		if window_seconds_changed_event:
			window_seconds_changed_event.set()

	return RedirectResponse(url='/', status_code=303)

def run(host='0.0.0.0', port=8000):
	uvicorn.run(app, host=host, port=port)

# run in background thread helper
def run_in_thread(host='0.0.0.0', port=8000):
	t = threading.Thread(target=run, kwargs={'host':host, 'port':port}, daemon=True)
	t.start()
