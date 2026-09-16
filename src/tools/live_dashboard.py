"""Serve a local webcam and hardware-status dashboard for the puzzle rig.

Run on the Pi:
    cd ~/phase_1
    python3 src/tools/live_dashboard.py

The dashboard serves current webcam frames and GPIO status only. It does not
record video or images. By default it listens only on the Pi's localhost and
is reached remotely through the Pi's private Tailscale Serve URL.
"""

import argparse
import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml
from gpiozero import Button

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.ultrasonic import HCSR04Reader
from datalog.logger import SessionLogger
from vision.camera import CameraStream
from vision.verify import CompletionVerifier
from display.seven_segment import SessionDisplay

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Puzzle Rig Dashboard</title>
<style>
body { background: #f3f4f6; color: #172033; font: 16px system-ui, sans-serif; margin: 0; }
main { max-width: 1100px; margin: auto; padding: 24px; }
h1 { margin: 0 0 6px; } .hint { color: #526070; margin: 0 0 20px; }
.grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); gap: 18px; }
.card { background: white; border-radius: 12px; box-shadow: 0 1px 3px #0002; padding: 16px; }
img { background: #101826; border-radius: 8px; display: block; max-width: 100%; width: 100%; }
.reading { border-bottom: 1px solid #e5e7eb; padding: 13px 0; } .label { color: #526070; font-size: 14px; }
.value { font-size: 25px; font-weight: 700; margin-top: 3px; } .ok { color: #168046; } .warn { color: #b45309; }
button { background: #173e77; border: 0; border-radius: 7px; color: white; cursor: pointer; font: inherit; margin: 8px 6px 0 0; padding: 9px 12px; }
button:disabled { opacity: .55; cursor: wait; } .result { font-size: 16px; line-height: 1.45; margin-top: 10px; }
.detail { color: #526070; font-size: 14px; margin-top: 4px; }
ul { margin: 8px 0 0; padding-left: 20px; } footer { color: #526070; font-size: 13px; margin-top: 16px; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
<h1>Puzzle Telemetry Rig</h1>
<p class="hint">Live view only. No video is recorded. Keep the camera framed on the board and hands.</p>
<div class="grid">
  <section class="card"><img id="live-frame" src="/frame.jpg" alt="Live puzzle webcam stream"><div id="camera-status" class="detail">Connecting to camera...</div></section>
  <section class="card">
    <div class="reading"><div class="label">Sensor 1</div><div id="sensor1" class="value">Waiting...</div><div id="sensor1-detail" class="detail"></div></div>
    <div class="reading"><div class="label">Sensor 2</div><div id="sensor2" class="value">Waiting...</div><div id="sensor2-detail" class="detail"></div></div>
    <div class="reading"><div class="label">Visitor approach</div><div id="approach" class="value">WAITING</div><div id="approach-detail" class="detail">Waiting for a sustained nearby sensor reading.</div></div>
    <div class="reading"><div class="label">Stopwatch (limit switch)</div><div id="stopwatch" class="value">READY</div><div id="stopwatch-detail" class="detail">Press the limit switch to start.</div></div>
    <div class="reading"><div class="label">Limit switch (GPIO7 / physical pin 26)</div><div id="switch" class="value">Waiting...</div></div>
    <div class="reading"><div class="label">Four-digit display preview</div><div id="display-preview" class="value" style="white-space:pre; font-family:monospace">    </div><div id="display-detail" class="detail"></div></div>
    <div class="reading"><div class="label">Recent switch events</div><ul id="events"><li>None yet</li></ul></div>
    <div class="reading"><div class="label">T-puzzle completion</div>
      <button id="save-reference" onclick="runCheck('/api/reference/capture')">Save solved T reference</button>
      <button id="check-puzzle" onclick="runCheck('/api/reference/check')">Check current puzzle</button>
      <div id="verification" class="result">Waiting for a solved reference.</div>
    </div>
  </section>
</div>
<footer id="updated">Connecting...</footer>
</main>
<script>
function distance(value, diagnostic) {
  if (diagnostic && diagnostic.result === 'disabled') return 'NOT CONNECTED';
  return value === null || value === undefined ? 'NO ECHO' : value.toFixed(1) + ' cm';
}
const liveFrame = document.querySelector('#live-frame');
const cameraStatus = document.querySelector('#camera-status');
function refreshCamera() {
  const next = new Image();
  next.onload = () => {
    liveFrame.src = next.src;
    cameraStatus.textContent = 'Live camera view';
  };
  next.onerror = () => { cameraStatus.textContent = 'Camera frame unavailable; retrying...'; };
  next.src = '/frame.jpg?t=' + Date.now();
}
function duration(value) {
  const total = Math.max(0, value || 0); const minutes = Math.floor(total / 60);
  return String(minutes).padStart(2, '0') + ':' + (total - minutes * 60).toFixed(1).padStart(4, '0');
}
function stopwatchText(session) {
  if (session.state === 'validating_start') return ['CHECKING START...', 'Confirming that the puzzle is not already complete.'];
  if (session.state === 'running') return ['TIMING ' + duration(session.elapsed_s), session.message || 'Press the limit switch again to check completion.'];
  if (session.state === 'verifying_stop') return ['CHECKING...', 'The timer continues if the T is incomplete.'];
  if (session.state === 'complete') {
    const verification = session.verification || {}; const outcome = verification.state || 'pending';
    return ['FINISHED ' + duration(session.elapsed_s), (session.message || outcome.toUpperCase()) + ' - saved as ' + (session.session_id || 'session') + '. Press again to start the next session.'];
  }
  return ['READY', session.message || 'Press the limit switch to start.'];
}
function approachText(approach) {
  if (approach.state === 'approached') {
    const closest = approach.min_distance_cm === null ? '' : '; closest ' + approach.min_distance_cm.toFixed(1) + ' cm';
    return ['APPROACH DETECTED', 'Sensor ' + approach.sensors.join(', ') + closest + '. The next valid start will be linked to it.'];
  }
  if (approach.state === 'detecting') return ['DETECTING...', 'Waiting for sustained proximity.'];
  return ['WAITING', 'Waiting for a sustained nearby sensor reading.'];
}
function verificationText(verification) {
  const result = verification.last_result;
  if (!verification.reference_saved || result.state === 'reference_required') return 'Save a clean solved-T reference first.';
  if (result.state === 'reference_saved') return 'Reference saved. Move the pieces, then select Check current puzzle.';
  if (result.state === 'complete' || result.state === 'incomplete') {
    if (result.message) return result.state.toUpperCase() + ' - ' + result.message;
    return result.state.toUpperCase() + ' - shape score ' + result.shape_score + ', area ratio ' + result.area_ratio;
  }
  return result.message || 'Unable to check the puzzle.';
}
async function refresh() {
  try {
    const status = await (await fetch('/api/status', {cache: 'no-store'})).json();
    for (const number of [1, 2]) {
      const info = (status.sensor_diagnostics || {})['Sensor ' + number];
      document.querySelector('#sensor' + number).textContent = distance(status.sensors['Sensor ' + number], info);
      if (info) {
        document.querySelector('#sensor' + number + '-detail').textContent = info.result === 'disabled'
          ? 'This sensor channel is disabled in config.'
          : 'Trig GPIO' + info.trigger + ' / Echo GPIO' + info.echo + ': ' + info.result.replaceAll('_', ' ');
      }
    }
    const display = status.display || {};
    const digits = display.text || '    ';
    document.querySelector('#display-preview').textContent = display.colon ? digits.slice(0, 2) + ':' + digits.slice(2) : digits;
    document.querySelector('#display-detail').textContent = display.message || 'Display unavailable';
    const approach = approachText(status.approach); const approachBox = document.querySelector('#approach');
    approachBox.textContent = approach[0]; approachBox.className = 'value ' + (status.approach.state === 'approached' ? 'ok' : '');
    document.querySelector('#approach-detail').textContent = approach[1];
    const stopwatch = stopwatchText(status.session); const stopwatchBox = document.querySelector('#stopwatch');
    stopwatchBox.textContent = stopwatch[0]; stopwatchBox.className = 'value ' + (status.session.state === 'running' ? 'ok' : '');
    document.querySelector('#stopwatch-detail').textContent = stopwatch[1];
    const switchBox = document.querySelector('#switch');
    switchBox.textContent = status.switch.pressed ? 'PRESSED (closed to GND)' : 'RELEASED (open)';
    switchBox.className = 'value ' + (status.switch.pressed ? 'ok' : 'warn');
    const events = document.querySelector('#events'); events.replaceChildren();
    (status.switch.events.length ? status.switch.events : ['None yet']).forEach((item) => {
      const row = document.createElement('li'); row.textContent = item; events.appendChild(row);
    });
    const result = document.querySelector('#verification'); result.textContent = verificationText(status.verification);
    result.className = 'result ' + (status.verification.last_result.state === 'complete' ? 'ok' : 'warn');
    document.querySelector('#updated').textContent = 'Updated ' + status.updated;
  } catch (_) { document.querySelector('#updated').textContent = 'Waiting for hardware status...'; }
}
async function runCheck(path) {
  const buttons = document.querySelectorAll('button'); buttons.forEach((button) => button.disabled = true);
  try {
    const response = await fetch(path, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).message || 'Request failed');
    await refresh();
  } catch (error) { document.querySelector('#verification').textContent = error.message; }
  finally { buttons.forEach((button) => button.disabled = false); }
}
refreshCamera(); setInterval(refreshCamera, 750);
refresh(); setInterval(refresh, 400);
</script>
</body></html>"""


def load_config() -> dict:
    with (Path(__file__).parents[1] / "config.yaml").open() as config_file:
        return yaml.safe_load(config_file)


class ApproachTracker:
    """Record one sustained ultrasonic approach until a valid session consumes it."""

    def __init__(self, session_config: dict):
        self._threshold_cm = session_config["approach_cm"]
        self._hold_s = session_config["approach_hold_s"]
        self._reset_s = session_config["approach_reset_s"]
        self._expiry_s = session_config["near_timeout_s"]
        self._lock = threading.Lock()
        self._candidate_started = None
        self._candidate_sensors: set[str] = set()
        self._candidate_min_distance = None
        self._approach = None
        self._last_near = None

    def update(self, readings: dict[str, float | None]) -> None:
        now = time.monotonic()
        near = {name: value for name, value in readings.items() if value is not None and value <= self._threshold_cm}
        with self._lock:
            if self._approach is not None:
                if near:
                    self._last_near = now
                elif self._last_near is not None and now - self._last_near >= self._reset_s:
                    self._approach = None
                    self._last_near = None
                return

            if not near:
                self._candidate_started = None
                self._candidate_sensors.clear()
                self._candidate_min_distance = None
                return

            if self._candidate_started is None:
                self._candidate_started = now
                self._candidate_sensors = set(near)
                self._candidate_min_distance = min(near.values())
            else:
                self._candidate_sensors.update(near)
                self._candidate_min_distance = min(self._candidate_min_distance, min(near.values()))

            if now - self._candidate_started >= self._hold_s:
                self._approach = {
                    "id": f"{now:.6f}",
                    "approach_ts": datetime.now().isoformat(timespec="seconds"),
                    "approach_monotonic": now,
                    "sensors": sorted(self._candidate_sensors),
                    "min_distance_cm": self._candidate_min_distance,
                }
                self._last_near = now
                self._candidate_started = None
                self._candidate_sensors.clear()
                self._candidate_min_distance = None

    def snapshot(self) -> dict | None:
        with self._lock:
            if self._approach is None:
                return None
            if time.monotonic() - self._approach["approach_monotonic"] > self._expiry_s:
                self._approach = None
                return None
            return self._approach.copy()

    def consume(self, approach_id: str) -> dict | None:
        with self._lock:
            if self._approach is None or self._approach["id"] != approach_id:
                return None
            approach = self._approach
            self._approach = None
            self._last_near = None
            return approach

    def clear_candidate(self) -> None:
        """Drop any in-progress candidate. Called while a session is active so a
        bystander's proximity during one visitor's solve cannot become the
        approach attached to the NEXT visitor's session."""
        with self._lock:
            self._candidate_started = None
            self._candidate_sensors.clear()
            self._candidate_min_distance = None

    def status(self) -> dict:
        with self._lock:
            if self._approach is not None:
                if time.monotonic() - self._approach["approach_monotonic"] <= self._expiry_s:
                    return {"state": "approached", "sensors": self._approach["sensors"], "min_distance_cm": self._approach["min_distance_cm"]}
                self._approach = None
            return {"state": "detecting" if self._candidate_started is not None else "waiting", "sensors": [], "min_distance_cm": None}


class HardwareMonitor:
    """Poll both sensors in sequence and expose the current GPIO state."""

    def __init__(self, config: dict, approach_tracker: ApproachTracker, on_switch_press=None, session_active=None):
        pins = config["pins"]
        test_config = config["sensor_test"]
        self._interval = test_config["sample_interval_s"]
        enabled = set(config.get("sensors", {}).get("enabled", [1, 2]))
        self._readers = {}
        for number in (1, 2):
            if number not in enabled:
                continue
            self._readers[f"Sensor {number}"] = HCSR04Reader(
                pins[f"sensor{number}_trigger"], pins[f"sensor{number}_echo"],
                test_config["echo_timeout_s"], test_config["max_distance_cm"],
                test_config.get("min_distance_cm", 2),
            )
        self._switch = Button(pins["limit_switch"], pull_up=True, bounce_time=test_config["switch_bounce_s"])
        self._lock = threading.Lock()
        self._readings = {f"Sensor {number}": None for number in (1, 2)}
        self._diagnostics = {
            f'Sensor {number}': {'trigger': pins[f'sensor{number}_trigger'],
                                'echo': pins[f'sensor{number}_echo'],
                                'result': 'waiting' if number in enabled else 'disabled'}
            for number in (1, 2)
        }
        self._events: deque[str] = deque(maxlen=5)
        self._running = threading.Event()
        self._thread = None
        self._on_switch_press = on_switch_press
        self._approach_tracker = approach_tracker
        self._session_active = session_active
        self._switch.when_pressed = self._handle_switch_press
        self._switch.when_released = lambda: self._record_switch_event("RELEASED")

    def _handle_switch_press(self) -> None:
        self._record_switch_event("PRESSED")
        if self._on_switch_press is not None:
            self._on_switch_press()

    def _record_switch_event(self, event: str) -> None:
        with self._lock:
            self._events.append(f"{time.strftime('%H:%M:%S')} {event}")

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._poll, name="hardware-poll", daemon=True)
        self._thread.start()

    def _poll(self) -> None:
        while self._running.is_set():
            readings = {}
            for name, reader in self._readers.items():
                try:
                    reading = reader.read_cm()
                    diagnostic = reader.last_diagnostic
                except Exception as exc:  # Keep software errors distinct from a missing echo.
                    reading = None
                    diagnostic = f'reader_error: {type(exc).__name__}: {exc}'
                with self._lock:
                    self._readings[name] = reading
                    self._diagnostics[name]['result'] = diagnostic
                readings[name] = reading
                time.sleep(self._interval)
            # Approach tracking is gated to pre-session states (READY / START CHECK):
            # while a session runs, nearby readings must not seed the next session's approach.
            if self._session_active is not None and self._session_active():
                self._approach_tracker.clear_candidate()
            else:
                self._approach_tracker.update(readings)

    def status(self) -> dict:
        with self._lock:
            readings = self._readings.copy()
            events = list(self._events)
            diagnostics = {name: info.copy() for name, info in self._diagnostics.items()}
        return {
            "sensors": readings,
            "sensor_diagnostics": diagnostics,
            "approach": self._approach_tracker.status(),
            "switch": {"pressed": self._switch.is_pressed, "events": events},
            "updated": time.strftime("%H:%M:%S"),
        }

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
        for reader in self._readers.values():
            reader.close()
        self._switch.close()


class StopwatchSession:
    """A start press must see an incomplete puzzle; a stop press must see a complete T."""

    def __init__(
        self, camera: CameraStream, verifier: CompletionVerifier, logger: SessionLogger,
        approach_tracker: ApproachTracker, safety_timeout_s: float,
    ):
        self._camera = camera
        self._verifier = verifier
        self._logger = logger
        self._approach_tracker = approach_tracker
        self._safety_timeout_s = safety_timeout_s
        self._lock = threading.Lock()
        self._state = "ready"
        self._message = ""
        self._feedback_revision = 0
        self._started_at = None
        self._started_monotonic = None
        self._stopped_at = None
        self._elapsed_s = None
        self._verification = None
        self._session_id = None
        self._approach = None
        threading.Thread(target=self._watch_timeout, name="session-watchdog", daemon=True).start()

    def is_active(self) -> bool:
        """True while a visitor's session is in progress (TIMING / STOP CHECK)."""
        with self._lock:
            return self._state in {"running", "verifying_stop"}

    def _watch_timeout(self) -> None:
        """End a session that does not successfully verify before its deadline."""
        while True:
            time.sleep(1.0)
            with self._lock:
                if self._state not in {"running", "verifying_stop"} or self._started_monotonic is None:
                    continue
                elapsed_s = time.monotonic() - self._started_monotonic
                if elapsed_s < self._safety_timeout_s:
                    continue
                started_at = self._started_at
                started_monotonic = self._started_monotonic
                approach = self._approach
                self._state = "saving_abandoned"  # presses are ignored in this state
                self._elapsed_s = elapsed_s
            self._abandon(started_at, started_monotonic, elapsed_s, approach)

    def _abandon(self, started_at: datetime, started_monotonic: float, elapsed_s: float, approach: dict | None) -> None:
        """Record an explicit abandoned outcome, then return to READY."""
        stopped_at = datetime.now()
        approach_ts = "" if approach is None else approach["approach_ts"]
        approach_to_start_s = ""
        min_distance_cm = ""
        if approach is not None:
            approach_to_start_s = f"{started_monotonic - approach['approach_monotonic']:.1f}"
            min_distance_cm = f"{approach['min_distance_cm']:.1f}"
        notes = f"abandoned: safety timeout after {int(self._safety_timeout_s)} s; completion not verified"
        if approach is not None:
            notes += f"; approach_sensors={','.join(approach['sensors'])}"
        try:
            session_id = self._logger.next_session_id()
            self._logger.append(
                {
                    "session_id": session_id,
                    "approach_ts": approach_ts,
                    "start_ts": started_at.isoformat(timespec="seconds"),
                    "stop_ts": stopped_at.isoformat(timespec="seconds"),
                    "approach_to_start_s": approach_to_start_s,
                    "solve_time_s": f"{elapsed_s:.1f}",
                    "min_distance_cm": min_distance_cm,
                    "completed": "abandoned",
                    "notes": notes,
                }
            )
            minutes = int(self._safety_timeout_s // 60)
            message = f"Previous session timed out after {minutes} min and was saved as abandoned. Press to start."
        except Exception as exc:  # The rig must return to READY even if the CSV write fails.
            session_id = None
            message = f"Timeout reached, but the abandoned session could not be saved: {exc}"
        with self._lock:
            self._verification = None
            self._session_id = session_id
            self._stopped_at = stopped_at
            self._started_at = None
            self._started_monotonic = None
            self._approach = None
            self._state = "ready"
            self._message = message

    def on_switch_press(self) -> None:
        """Handle a debounced press from the configured GPIO without blocking the callback."""
        now = datetime.now()
        jpeg, _ = self._camera.latest_jpeg()
        approach = self._approach_tracker.snapshot()
        with self._lock:
            if self._state in {"ready", "complete"}:
                self._state = "validating_start"
                self._message = "Checking that the puzzle has been reset."
                self._verification = None
                self._session_id = None
                self._started_at = None
                self._started_monotonic = None
                self._stopped_at = None
                self._elapsed_s = None
                self._approach = None
                threading.Thread(
                    target=self._validate_start,
                    args=(now, time.monotonic(), jpeg, approach),
                    name="session-start-check",
                    daemon=True,
                ).start()
                return
            if self._state != "running":
                return
            started_at = self._started_at
            started_monotonic = self._started_monotonic
            elapsed_s = time.monotonic() - self._started_monotonic
            self._state = "verifying_stop"
            self._elapsed_s = elapsed_s
            self._message = "Checking whether the T is complete."

        threading.Thread(
            target=self._verify_stop,
            args=(started_at, started_monotonic, now, elapsed_s, jpeg),
            name="session-stop-check",
            daemon=True,
        ).start()

    def _check_frame(self, jpeg: bytes | None) -> dict:
        try:
            if jpeg is None:
                return {"state": "error", "message": "camera frame is not ready"}
            return self._verifier.check(jpeg)
        except Exception as exc:  # The next press must remain usable if vision has a transient fault.
            return {"state": "error", "message": f"verification failed: {exc}"}

    def _validate_start(
        self, started_at: datetime, started_monotonic: float, jpeg: bytes | None, approach: dict | None,
    ) -> None:
        verification = self._check_frame(jpeg)
        with self._lock:
            self._verification = verification
            self._feedback_revision += 1
            if verification["state"] == "incomplete":
                self._state = "running"
                self._message = "Timer running. Press again to check completion."
                self._started_at = started_at
                self._started_monotonic = started_monotonic
                self._approach = None if approach is None else self._approach_tracker.consume(approach["id"])
            elif verification["state"] == "complete":
                self._state = "ready"
                self._message = "Puzzle is already complete. Reset it before starting."
            else:
                self._state = "ready"
                self._message = verification.get("message", "Cannot verify the starting puzzle state.")

    def _verify_stop(
        self, started_at: datetime, started_monotonic: float, stopped_at: datetime, elapsed_s: float, jpeg: bytes | None,
    ) -> None:
        verification = self._check_frame(jpeg)
        with self._lock:
            # The watchdog may have claimed this session while camera verification was running.
            if self._state != "verifying_stop":
                return
            deadline_elapsed_s = time.monotonic() - started_monotonic
            if deadline_elapsed_s >= self._safety_timeout_s:
                approach = self._approach
                self._state = "saving_abandoned"
                self._elapsed_s = deadline_elapsed_s
                timed_out = True
            else:
                approach = self._approach
                timed_out = False

        if timed_out:
            self._abandon(started_at, started_monotonic, deadline_elapsed_s, approach)
            return

        if verification["state"] != "complete":
            with self._lock:
                if self._state != "verifying_stop":
                    return
                self._state = "running"
                self._elapsed_s = None
                self._verification = verification
                self._message = "Puzzle is incomplete - timer continues." if verification["state"] == "incomplete" else verification.get("message", "Verification failed; try again.")
                self._feedback_revision += 1
            return

        with self._lock:
            # Claim the completion before writing CSV so the watchdog cannot also abandon it.
            if self._state != "verifying_stop":
                return
            self._state = "saving_complete"
        approach_to_start_s = ""
        approach_ts = ""
        min_distance_cm = ""
        if approach is not None:
            approach_ts = approach["approach_ts"]
            approach_to_start_s = f"{started_monotonic - approach['approach_monotonic']:.1f}"
            min_distance_cm = f"{approach['min_distance_cm']:.1f}"
        notes = f"dashboard stopwatch; verification=complete; shape_score={verification['shape_score']}; area_ratio={verification['area_ratio']}"
        if approach is not None:
            notes += f"; approach_sensors={','.join(approach['sensors'])}"
        try:
            session_id = self._logger.next_session_id()
            self._logger.append(
                {
                    "session_id": session_id,
                    "approach_ts": approach_ts,
                    "start_ts": started_at.isoformat(timespec="seconds"),
                    "stop_ts": stopped_at.isoformat(timespec="seconds"),
                    "approach_to_start_s": approach_to_start_s,
                    "solve_time_s": f"{elapsed_s:.1f}",
                    "min_distance_cm": min_distance_cm,
                    "completed": "yes",
                    "notes": notes,
                }
            )
            message = "Complete puzzle verified."
        except Exception as exc:  # Preserve the dashboard state even if a CSV write fails.
            session_id = None
            verification = {"state": "error", "message": f"could not save session: {exc}"}
            message = verification["message"]

        with self._lock:
            self._verification = verification
            self._session_id = session_id
            self._stopped_at = stopped_at
            self._elapsed_s = elapsed_s
            self._state = "complete"
            self._message = message
            self._feedback_revision += 1

    def status(self) -> dict:
        with self._lock:
            elapsed_s = self._elapsed_s
            if self._state in {"running", "verifying_stop"}:
                elapsed_s = time.monotonic() - self._started_monotonic
            return {
                "state": self._state,
                "message": self._message,
                "feedback_revision": self._feedback_revision,
                "elapsed_s": elapsed_s,
                "started_at": None if self._started_at is None else self._started_at.isoformat(timespec="seconds"),
                "stopped_at": None if self._stopped_at is None else self._stopped_at.isoformat(timespec="seconds"),
                "verification": self._verification,
                "session_id": self._session_id,
            }


def make_handler(monitor: HardwareMonitor, camera: CameraStream, verifier: CompletionVerifier, stopwatch: StopwatchSession, display=None):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path == "/":
                self._send_bytes(HTTPStatus.OK, "text/html; charset=utf-8", PAGE.encode())
            elif path == "/api/status":
                status = monitor.status()
                status["camera"] = camera.status()
                status["verification"] = verifier.status()
                status["session"] = stopwatch.status()
                status["display"] = display.status() if display else {"state": "disabled"}
                payload = json.dumps(status).encode()
                self._send_bytes(HTTPStatus.OK, "application/json", payload)
            elif path == "/stream.mjpg":
                self._stream_mjpeg()
            elif path == "/frame.jpg":
                jpeg, _ = camera.latest_jpeg()
                if jpeg is None:
                    self._send_bytes(HTTPStatus.SERVICE_UNAVAILABLE, "text/plain; charset=utf-8", b"camera frame is not ready")
                else:
                    self._send_bytes(HTTPStatus.OK, "image/jpeg", jpeg)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            jpeg, _ = camera.latest_jpeg()
            if jpeg is None:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"message": "camera frame is not ready"})
                return
            try:
                if path == "/api/reference/capture":
                    result = verifier.capture_reference(jpeg)
                elif path == "/api/reference/check":
                    result = verifier.check(jpeg)
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            except (OSError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"message": str(exc)})
                return
            self._send_json(HTTPStatus.OK, result)

        def _send_bytes(self, status: HTTPStatus, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: HTTPStatus, payload: dict) -> None:
            self._send_bytes(status, "application/json", json.dumps(payload).encode())

        def _stream_mjpeg(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last_sequence = -1
            try:
                while True:
                    jpeg, sequence = camera.latest_jpeg()
                    if jpeg is None or sequence == last_sequence:
                        time.sleep(0.05)
                        continue
                    last_sequence = sequence
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args) -> None:
            return

    return DashboardHandler


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description="Serve the local puzzle-rig webcam and hardware dashboard.")
    parser.add_argument("--host", default=config["dashboard"]["host"])
    parser.add_argument("--port", type=int, default=config["dashboard"]["port"])
    args = parser.parse_args()

    verifier = CompletionVerifier(config["completion"])
    camera_config = config["camera"]
    camera = CameraStream(
        camera_config["index"], camera_config["width"], camera_config["height"],
        camera_config["fps"], config["dashboard"]["jpeg_quality"],
    )
    logger = SessionLogger(config["data"]["dir"], config["data"]["csv"], config["data"]["images_dir"])
    approach_tracker = ApproachTracker(config["session"])
    stopwatch = StopwatchSession(camera, verifier, logger, approach_tracker, config["session"]["safety_timeout_s"])
    display_settings = config.get('display', {})
    if display_settings.get('enabled'):
        display_pins = [display_settings['clk'], display_settings['dio']]
        if len(set(display_pins)) != 2 or set(display_pins) & set(config['pins'].values()):
            raise ValueError('Display pins overlap each other or an existing sensor/switch')
    display = SessionDisplay(display_settings, stopwatch.status, config['session']['result_hold_s'])
    monitor = HardwareMonitor(
        config, approach_tracker,
        on_switch_press=stopwatch.on_switch_press,
        session_active=stopwatch.is_active,
    )
    try:
        camera.start()
        monitor.start()
        display.start()
        server = ThreadingHTTPServer((args.host, args.port), make_handler(monitor, camera, verifier, stopwatch, display))
        print(f"Dashboard running at http://{args.host}:{args.port}")
        if args.host in {"127.0.0.1", "localhost"}:
            print("Remote access is provided by the Pi's private Tailscale Serve URL.")
        print("Press Ctrl+C to stop. Webcam frames stay in memory and are not recorded.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        if "server" in locals():
            server.server_close()
        camera.stop()
        display.stop()
        monitor.stop()


if __name__ == "__main__":
    main()
