# CLAUDE.md — Puzzle Telemetry Rig (Phase 1)

Doc ID: PFT/AIRL/CTX/2026-001 · Owner: AI & Robotics Lab, Param Foundation · Last updated: 24 Aug 2026 (rev 5 — five-minute safety timeout)
This is the project context file. Read this first. It routes you to every other file in the repo.

---

## 1. Purpose

Measure how visitors solve physical puzzle boards, automatically:

1. **Detect a person approaching** the table (2× HC-SR04 ultrasonic — rev 2).
2. **Time the solve** — a **limit switch** press starts timing (only if the T isn't already solved) and a later press stops it (only when the camera verifies completion) — see §4.
3. **Show the solve time** on a 2.9" e-paper display *(deferred — not currently attached, see wiring.md §7; the dashboard page shows it meanwhile)*.
4. **Verify the puzzle is actually complete** from the camera image ← *implemented (v1 reference check), see §8.*

Everything runs headless on a Raspberry Pi 4, developed over SSH from a Windows PC.

## 2. System at a glance

```
                 ┌──────────────────────────────┐
 person walks    │        Raspberry Pi 4        │
 up to table     │  (Raspberry Pi OS, Python)   │
      │          │                              │
HC-SR04 #1 ────►│ GPIO22/17          SPI0 ─────┼────► MH-ET 2.9" e-paper
HC-SR04 #2 ────►│ GPIO6/27                     │      (DEFERRED — wiring.md §7)
 (distances)     │                              │
 limit switch ──►│ GPIO26             CSV/JPG ──┼────► data/ (sessions log)
 USB webcam ────►│ USB-A (hands-only framing)   │
                 └──────────────────────────────┘
```

One session = READY → START CHECK → TIMING → STOP CHECK → DONE → back to READY.
Visual version: open **docs/architecture.html** in a browser.

## 3. Hardware inventory

| # | Item | Interface | Pi connection |
|---|------|-----------|---------------|
| 1 | Raspberry Pi 4 | — | Official 5 V/3 A USB-C PSU |
| 2 | USB webcam — Logitech Brio 100 | USB/V4L2 | USB-A → `/dev/video0` (confirmed 17 Aug 2026) |
| 3 | HC-SR04 sensor 1 | GPIO (5 V, Echo divider fitted ✓) | Trigger GPIO22, Echo GPIO17 |
| 4 | HC-SR04 sensor 2 | GPIO (5 V, Echo divider fitted ✓) | Trigger GPIO6, Echo GPIO27 |
| 5 | Limit switch (replaces start/stop buttons) | GPIO, internal pull-up | GPIO26 → GND; COM+NO, idle open and press/release verified 20 Aug 2026 |
| 6 | MH-ET Live 2.9" e-paper (296×128) | SPI0 | **DEFERRED** — GPIO17/24 currently used by sensors; migration plan in wiring.md §7 |

Full pin-by-pin wiring, voltage divider, and smoke tests: **docs/wiring.md**. Do not re-derive pins anywhere else — that file is the single source of truth.

## 4. Session state machine

| State | Entered when | System does | Exits to |
|-------|-------------|-------------|----------|
| READY | boot / after a saved session | Poll both sonars; record an approach after sustained proximity | START CHECK on the first GPIO26 press |
| START CHECK | first GPIO26 press | Check that the puzzle is not already complete; attach any pending approach | TIMING if incomplete; READY if already solved |
| TIMING | valid first press | Record `start_ts`; calculate `approach_to_start_s` when an approach was detected; show the live stopwatch; approach tracking is paused | STOP CHECK on the next GPIO26 press; **READY after `safety_timeout_s` (5 min) — row saved with `completed=abandoned`** |
| STOP CHECK | next GPIO26 press | Check the current camera frame against the T reference before the safety deadline | DONE if complete; back to TIMING if incomplete; READY with `completed=abandoned` if the deadline is reached |
| DONE | complete puzzle verified and saved | Show elapsed time and completion result; append one CSV row | START CHECK on the next GPIO26 press |

All thresholds live in `src/config.yaml` — never hardcode them.

## 5. Data schema — `data/sessions.csv`

| Column | Type | Notes |
|--------|------|-------|
| session_id | str | e.g. `2026-08-17_0042` — anonymous, sequential |
| approach_ts / start_ts / stop_ts | ISO 8601 | timestamps of the three events |
| approach_to_start_s | float | sustained ultrasonic approach to valid first press; blank if no approach was detected |
| solve_time_s | float | stop − start (the headline metric) |
| min_distance_cm | float | closest valid ultrasonic reading during the recorded approach |
| hand_frames_pct | float | RESERVED for Milestone C — always blank today |
| frames_total | int | RESERVED for Milestone C — always blank today |
| verify_photo | path | RESERVED — the dashboard stores **no** per-session photo; always blank today |
| completed | `yes` / `abandoned` | written by the dashboard: `yes` = reference check passed at stop; `abandoned` = 5-min safety timeout. No manual labelling in the current system |
| notes | str | auto-filled by the dashboard (verification scores, approach sensors, timeout reason) |

## 6. File routing — where to look / where to put things

```
phase_1/
├── CLAUDE.md                 ← this file (context + routing)
├── docs/
│   ├── wiring.md             ← GPIO pin map, divider, smoke tests  [SOURCE OF TRUTH for pins]
│   ├── architecture.html     ← realistic bench wiring + rev-3 session flow (open in browser; matches wiring.md)
│   ├── current-system-flow.html ← current dashboard/session flow, metrics, and edge cases
│   └── verify_algorithm.html ← visual explainer of the §8 v1 completion check (open in browser)
├── deploy/
│   └── puzzle-dashboard.service ← systemd unit for dashboard autostart on the Pi
├── src/
│   ├── main.py               ← LEGACY STUB (exits with a pointer) — the runtime is tools/live_dashboard.py
│   ├── config.yaml           ← ALL thresholds, pins, camera settings
│   ├── tools/
│   │   ├── probe_pins.py     ← verifies confirmed Trig/Echo pairs + switch state after rewiring
│   │   ├── live_sensor_test.py ← terminal-only sensor/switch monitor
│   │   └── live_dashboard.py ← **THE RUNTIME**: dashboard page + session state machine + CSV logging
│   ├── sensors/
│   │   ├── ultrasonic.py     ← HC-SR04 on-demand reader (sequential pings)
│   │   └── buttons.py        ← rev-1 START/STOP buttons (legacy — limit switch replaces them)
│   ├── vision/
│   │   ├── camera.py         ← USB webcam capture for in-memory JPEG frames (OpenCV)
│   │   ├── hands.py          ← hand detection (MediaPipe Hand Landmarker)
│   │   └── verify.py         ← live puzzle-completion reference check
│   ├── display/
│   │   └── epaper.py         ← MH-ET 2.9" wrapper (Waveshare epd2in9_V2 driver)
│   └── datalog/
│       └── logger.py         ← CSV append
├── data/                     ← collected sessions (never commit to git)
│   ├── sessions.csv
│   └── images/
└── requirements.txt
```

| If you need to… | Go to |
|-----------------|-------|
| Change distance threshold / timings / camera index | `src/config.yaml` |
| Change session flow logic | `src/tools/live_dashboard.py` (`StopwatchSession`) |
| Fix a sensor or button | `src/sensors/` + `docs/wiring.md` |
| Work on hand detection or completion check | `src/vision/` |
| Change what the display shows | `src/display/epaper.py` |
| View the live webcam and hardware status | `python src/tools/live_dashboard.py` on the Pi, then use the printed SSH tunnel |
| Review current flow, metrics, and edge cases | `docs/current-system-flow.html` |
| Add a logged metric | `src/datalog/logger.py` + §5 table above |
| Re-wire anything | `docs/wiring.md` first, then update `config.yaml` |

## 7. Software stack + SSH workflow

| Layer | Component | Notes |
|-------|-----------|-------|
| OS | Raspberry Pi OS 64-bit (Bookworm) | 64-bit required for MediaPipe |
| Runtime | Python 3.11 (venv) | `~/puzzle-venv`, created with `--system-site-packages` |
| GPIO | gpiozero | Button, DistanceSensor |
| Vision | OpenCV (apt) + MediaPipe | `hand_landmarker.task` model file in `src/vision/` |
| Display | Waveshare `epd2in9_V2` driver | MH-ET 2.9" uses SSD1680 — same panel class; older batches are IL3820, see wiring.md §7 |
| Data | CSV via stdlib | upgrade to SQLite only if needed |
| Entry point | `src/tools/live_dashboard.py` | dashboard + session state machine + CSV logging (main.py = legacy stub) |
| Autostart | systemd `puzzle-dashboard.service` | installed and enabled on the Pi 24 Aug 2026; starts and restarts the dashboard after boot |

```bash
# connect (from Windows PowerShell) — Tailscale, works from anywhere (preferred)
ssh raspberrypi@puzzle-rig-pi               # MagicDNS name (added to tailnet 17 Aug 2026, Tailscale SSH on)
ssh raspberrypi@[100.x.y.z]                 # or its Tailscale IP — run `tailscale ip -4` on the Pi and fill in
ssh raspberrypi@172.16.80.148               # lab-LAN fallback — DHCP, may change

# one-time Pi setup (SSH + SPI already enabled 17 Aug 2026)
sudo apt update && sudo apt install -y python3-opencv python3-gpiozero python3-lgpio python3-pip git v4l-utils
python3 -m venv ~/puzzle-venv --system-site-packages
source ~/puzzle-venv/bin/activate
git clone https://github.com/waveshare/e-Paper ~/e-Paper
pip install ~/e-Paper/RaspberryPi_JetsonNano/python
pip install pyyaml pillow spidev            # mediapipe gets added at Milestone C

# deploy code from Windows (run in Desktop\phase_1)
scp -r src requirements.txt raspberrypi@puzzle-rig-pi:~/phase_1/

# run manually only when diagnosing (THE entry point — dashboard page + full session state machine)
cd ~/phase_1 && python3 src/tools/live_dashboard.py
# then from Windows:  ssh -N -L 8000:127.0.0.1:8000 raspberrypi@puzzle-rig-pi   →  open http://127.0.0.1:8000

# normal operation: the dashboard starts automatically after Pi boot
sudo systemctl status puzzle-dashboard.service
sudo systemctl restart puzzle-dashboard.service
sudo journalctl -u puzzle-dashboard.service -n 50 --no-pager
```

Tip: VS Code Remote-SSH gives you editing directly on the Pi instead of scp round-trips.

## 8a. Design decisions — RESOLVED (20–24 Aug 2026)

1. **Limit switch semantics (implemented):** first press starts timing only when the puzzle is verified incomplete; each later press checks the T and the timer stops + saves only when it verifies complete; a session with no successful stop is auto-ended after `safety_timeout_s` and saved as `abandoned`. Wiring verified COM+NO: idle open, press = GPIO26 LOW.
2. **Role of each ultrasonic sensor (implemented):** either sensor can record a sustained approach (≤ `approach_cm` held for `approach_hold_s`); the session stores which sensor(s) and the closest reading. Tracking is **paused while a session is active** so bystanders can't seed the next session's approach. Placement/interpretation can be refined after pilot data.

## 8. Puzzle completion verification ("thing 2") — v1 LIVE

The camera judges completion at every switch press (start check + stop checks). Staged plan:

| Stage | Approach | How it works | Status |
|-------|----------|--------------|--------|
| v1 | T-shape reference match | Save one solved-T view in the dashboard; HSV-segment the tan cardboard, take the largest connected component, compare contour (`matchShapes`) + area with the solved T | **LIVE** in `vision/verify.py` — thresholds in `config.yaml → completion:`; calibrate against real solves |
| — | Manual label | *Superseded:* the current system stores no per-session photos and takes no manual labels — `completed` is auto-written (`yes`/`abandoned`) | Re-introduce photo capture only if a labelled dataset is wanted for v2 |
| fallback | Contour/gap detection | Unfilled slots show as dark gaps/edges | Only if v1 fights the lighting |
| v2 | Small CNN classifier | Train complete-vs-incomplete on labelled photos | Needs photo capture re-enabled first — not currently collecting |

Constraints that make v1 workable: camera is fixed, top-down, hands leave the frame at each press, one known puzzle per station. It matches the reference shape within thresholds — it does not semantically "recognise" a T, so false results are possible until calibrated.
Visual walkthrough of v1 (solved vs scattered vs almost-solved, step by step): **docs/verify_algorithm.html** — thresholds shown there mirror `config.yaml → completion:`.

## 9. Data & privacy rules (DPDP)

Camera is framed on **hands + board only** — mount top-down so faces cannot enter the frame. No video and **no per-session photos** are stored; the dashboard serves only current in-memory frames, and the only images on disk are the solved-reference photo + mask captured once at setup. `session_id` is anonymous — never log names, phone numbers, or other personal data. Put signage at the table stating solve time is being measured. Collected data stays on the Pi and syncs only to the approved Google Workspace shared drive.

## 10. Roadmap

- [x] SSH working (`raspberrypi@172.16.80.148`) + webcam verified: Brio 100 on `/dev/video0` — T4 ✓ 17 Aug 2026
- [x] Pi on Tailscale as `puzzle-rig-pi` (Tailscale SSH on, key expiry disabled) — 17 Aug 2026
- [x] Bench rewire (rev 2): 2× HC-SR04 (Echo dividers ✓) + limit switch on GPIO26 — 20 Aug 2026
- [x] Live hardware check: GPIO26 limit switch is open at idle and reports press/release transitions — 20 Aug 2026
- [x] Lock confirmed sonar pairs into `config.yaml` + `wiring.md` (S1: GPIO22→17; S2: GPIO6→27)
- [x] §8a decided + implemented: switch semantics and sensor roles (see §8a) — 20 Aug 2026
- [x] Dashboard stopwatch: start only if the puzzle is incomplete; presses keep timing until the T verifies complete, then append a CSV session row — 20 Aug 2026
- [x] `live_dashboard.py` made the documented runtime; `main.py` retired to a legacy stub — 24 Aug 2026
- [x] 5-min safety timeout implemented: abandoned sessions saved with `completed=abandoned`, rig returns to READY — 24 Aug 2026
- [x] Approach tracking gated to pre-session states (no bystander carry-over between visitors) — 24 Aug 2026
- [x] Docs reconciled with actual behaviour (schema truth, no per-session photos) — 24 Aug 2026
- [ ] Calibrate `completion:` thresholds with real solves (watch shape_score / area_ratio on the dashboard)
- [ ] Milestone C — webcam hand tracking (`hand_frames_pct`, `frames_total`)
- [ ] E-paper return: move S1 Echo GPIO17 → GPIO23 per wiring.md §7, then attach the display
- [x] systemd autostart: `puzzle-dashboard.service` installed, enabled, and restart-tested on the Pi — 24 Aug 2026
- [ ] Pilot at the gallery
- [ ] Put `phase_1` under git (it is currently plain files — no version history)

## References

- Waveshare 2.9" e-paper wiki (driver + examples): https://www.waveshare.com/wiki/2.9inch_e-Paper_Module
- MH-ET Live 2.9" = SSD1680 / GDEM029T94 panel (GxEPD2_290_T94 class): https://forum.arduino.cc/t/mh-et-live-2-9-inch-display-with-gxepd2/1078967
- MediaPipe Hand Landmarker on Raspberry Pi (official sample): https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/hand_landmarker/raspberry_pi/README.md
- Alternative pure-Python SSD1680 driver: https://github.com/jairosh/raspberrypi-ssd1680
