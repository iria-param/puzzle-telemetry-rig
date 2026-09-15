# Wiring Reference — Puzzle Telemetry Rig (Phase 1)

Doc ID: PFT/AIRL/WIR/2026-001 · Last updated: 11 Sep 2026 (rev 3 — single active HC-SR04)
**This file is the single source of truth for all pin assignments.** If a pin changes, change it here first, then in `src/config.yaml`.

Current installation: ONE HC-SR04 on Sensor 1 + ONE limit switch. Sensor 2 is not connected and is disabled in software.

Pi pin numbering: **BCM GPIO numbers** in code, **physical pin numbers** for wiring.

---

## 1. Master connection index — current bench wiring (20 Aug 2026)

| Ref | From (module pin) | To (Pi physical pin) | BCM | Notes |
|-----|-------------------|----------------------|-----|-------|
| J1 | Sensor 1 VCC | 2 (5V) | — | |
| J2 | Sensor 1 GND | 6 (GND) | — | |
| J3 | Sensor 1 Echo (via divider) | 11 | GPIO17 | confirmed |
| J4 | Sensor 1 Trig | 15 | GPIO22 | confirmed |
| J5–J8 | Sensor 2 | — | GPIO6/GPIO27 reserved | Not connected; disabled in `config.yaml` |
| J9 | Limit switch leg A | 37 | GPIO26 | internal pull-up; verified open idle, closed = LOW |
| J10 | Limit switch leg B | any GND | — | "-ve" leg |
| J11 | USB webcam (Brio 100) | USB-A port | — | /dev/video0 — verified 17 Aug 2026 |
| J12 | TM1637 display CLK | 16 | GPIO23 | Connected; standalone display test passed 15 Sep 2026 |
| J13 | TM1637 display DIO | 18 | GPIO24 | Connected; standalone display test passed 15 Sep 2026 |
| J14 | TM1637 display VCC | 1 (3V3) | — | 3.3 V measured at module; never use 5 V |
| J15 | TM1637 display GND | 6 (GND) | — | Connected |

The active Sensor 1 Echo line uses the fitted voltage divider (see §3).

## 2. Pi 40-pin header — used pins only (rev 3)

```
                     ┌───────────┐
              (1)    │ ▪ ▪ │   (2) ── 5V ────── Sensor 1 VCC   [J1]
              (3)    │ ▪ ▪ │   (4) ── 5V ────── Sensor 2 VCC   [J5]
              (5)    │ ▪ ▪ │   (6) ── GND ───── Sensor 1 GND   [J2]
              (7)    │ ▪ ▪ │   (8)
  [J6] Sensor 2 GND ── GND (9) │ ▪ ▪ │  (10)
  [J3] S1 Echo ─── GPIO17 (11) │ ▪ ▪ │  (12)
  [J7] S2 Echo ─── GPIO27 (13) │ ▪ ▪ │  (14)
  [J4] S1 Trig ─── GPIO22 (15) │ ▪ ▪ │  (16)
             (17)    │ ▪ ▪ │  (18)
             (19)    │ ▪ ▪ │  (20)
             (21)    │ ▪ ▪ │  (22)
             (23)    │ ▪ ▪ │  (24)
             (25)    │ ▪ ▪ │  (26)
             (27)    │ ▪ ▪ │  (28)
             (29)    │ ▪ ▪ │  (30)
  [J8] S2 Trig ──── GPIO6  (31) │ ▪ ▪ │  (32)
             (33)    │ ▪ ▪ │  (34)
             (35)    │ ▪ ▪ │  (36)
  [J9] limit switch ── GPIO26 (37) │ ▪ ▪ │  (38)
             (39 GND — switch/divider rail ok) │ ▪ ▪ │  (40)
                     └───────────┘
         (pin 1 is nearest the SD-card corner)
```

## 3. Echo voltage dividers — one per sensor, MANDATORY

Echo outputs **5 V**; Pi GPIO tolerates **3.3 V max**. Each sensor's Echo runs through:

```
ECHO (5 V) ──[ 1 kΩ ]──●──────► Pi GPIO (3.3 V)
                       │
                    [ 2 kΩ ]
                       │
                      GND
```

Check: 5 V × 2k/(1k+2k) = 3.33 V ✓. Status: **fitted on both sensors — confirmed 20 Aug 2026.**

## 4. Limit switch (replaces the START/STOP buttons)

Wired between **GPIO26 (pin 37)** and GND. No external resistor — code enables the internal pull-up.

```
GPIO26 (pin 37) ──► [ limit switch ] ──► GND        open = HIGH, closed = LOW
```

```python
from gpiozero import Button
switch = Button(26)          # is_pressed == True when the switch is closed
```

Verified 20 Aug 2026: the switch is wired **COM + NO**. It is open/released at idle and GPIO26 reads LOW when pressed. In the live dashboard, the first press starts only after confirming that the T is incomplete; each later press checks the T, and timing ends only when it verifies complete.

## 5. Pin verification

The confirmed sensor pairs are shown below. Run the probe after rewiring to verify their readings and the switch's idle state:

```bash
cd ~/phase_1 && source ~/puzzle-venv/bin/activate
python src/tools/probe_pins.py
```

Hold a hand ~30 cm in front of the sensor when prompted. PASS looks like exactly one line per sensor saying `[LOOKS RIGHT]` at ~30 cm. Then record the result here:

| | Trig | Echo | confirmed |
|---|---|---|---|
| Sensor 1 | GPIO22 | GPIO17 | 20 Aug 2026 |
| Sensor 2 | GPIO6 | GPIO27 | 20 Aug 2026 |
| Limit switch | GPIO26 | idle = open (released); press/release PASS | 20 Aug 2026 |

…and lock the same values into `src/config.yaml`.

## 6. Smoke tests (rev 2)

**T1 — SPI enabled** (still passes; needed only when the e-paper returns)
```bash
ls /dev/spidev0.*        # PASS: spidev0.0  spidev0.1
```

**T2 — limit switch** — **PASS, 20 Aug 2026.** Covered by the live dashboard or the probe (§5). Standalone check:
```bash
python3 -c "from gpiozero import Button; from signal import pause; \
b=Button(26); b.when_pressed=lambda: print('CLOSED'); \
b.when_released=lambda: print('open'); pause()"
```
PASS: pressing/releasing prints alternately.

**T3 — both sonars** (after the probe fills §5's table — use the confirmed pins):
```bash
python3 -c "from gpiozero import DistanceSensor; from time import sleep
s1 = DistanceSensor(echo=[S1_ECHO], trigger=[S1_TRIG], max_distance=2)
s2 = DistanceSensor(echo=[S2_ECHO], trigger=[S2_TRIG], max_distance=2)
[print(f'S1 {s1.distance*100:5.0f} cm   S2 {s2.distance*100:5.0f} cm') or sleep(0.5) for _ in range(10)]"
```
PASS: both columns track a hand independently (±2 cm).

**T4 — webcam** ✓ passed 17 Aug 2026 (Brio 100, /dev/video0).

**T5 — e-paper** — deferred until the display is (re)attached; see §7.

## 7. E-paper — DEFERRED + pin conflict & migration plan

Status 20 Aug 2026: display not attached; decision "later / maybe". The current sensor wiring **borrows one pin the display needs**:

| Pin | Now used by | E-paper needs it as |
|-----|-------------|---------------------|
| GPIO17 | Sensor 1 Echo | RST |

**Migration when the display arrives** (move one jumper, then update config.yaml + this file):

- Sensor 1 Echo on GPIO17 → move to **GPIO23** (pin 16)

GPIO23 is free in the current map, and the e-paper then connects exactly as rev 1 documented: VCC→3V3(17), GND→20, SDI→GPIO10(19), CLK→GPIO11(23), CS→GPIO8(24), DC→GPIO25(22), RST→GPIO17(11), BUSY→GPIO24(18). Driver: `epd2in9_V2` (SSD1680 batch) or legacy `epd2in9` (IL3820 batch) — test tells.

## 8. Troubleshooting (rev 2)

| Symptom | Layer | Probable cause | Diagnostic | Fix |
|---------|-------|----------------|------------|-----|
| Sonar stuck at max (~200 cm) | Signal | Trig/Echo swapped, or Echo divider broken | Probe both orders (§5); multimeter divider mid-point | Swap pins in config; rebuild divider §3 |
| Sonar reads 0 / erratic | Signal / Electrical | Loose VCC or shared-GND missing | Wiggle test; continuity sensor GND ↔ Pi GND | Re-seat J1/J2/J5/J6 |
| Both sonars interfere (jumpy readings) | Signal | Ultrasonic cross-talk — both pinging at once | Cover one sensor: does the other settle? | Poll them alternately in code (never simultaneously) |
| Switch always "pressed" | Signal | Wired via NC terminal, or leg on 3V3 | Probe idle state (§5) | Use COM+NO terminals, or invert logic in code |
| Switch never fires | Signal | GND leg not actually on GND | Continuity leg-B ↔ any GND pin | Re-seat J10 |
| Sensor is always `NO ECHO` | Signal / Electrical | Wrong pins, loose wire, or divider fault | Run `live_sensor_test.py` with a hand 20–50 cm away | Recheck the confirmed pins and the divider in §3 |
| Camera not found | Signal | Port/cable | `lsusb` before/after re-plug | Another USB port; `dmesg \| tail` |

Escalation: if a fault survives its fix column, isolate that one device on a bare Pi and re-run its smoke test before suspecting code.

## 9. TM1637 4-digit 7-segment display (added 09 Sep 2026)

Current status 15 Sep 2026: reconnected at a measured 3.3 V and enabled in
`src/config.yaml`. The all-segments, `1234`, `DONE`, and counter patterns passed
visually. Use `src/tools/test_display.py` for future isolated testing.

Session timer + status display (scrolling "START PUZZLE", MM:SS stopwatch, donE/TIME OUT
messages). Driven by `src/display/seven_segment.py` from the dashboard.

⚠ **VCC must be on 3.3 V, not 5 V.** The module's onboard pull-ups tie CLK/DIO to VCC;
at 5 V that puts 5 V on GPIO23/24, which the Pi does not tolerate long-term. The TM1637
runs correctly from 3.3 V (slightly dimmer). Move the VCC jumper to physical pin 1 or 17,
then activate per the steps in `config.yaml → display:`.

Pin note: "CLK 23 / DIO 24" is stored as **BCM** GPIO23 (physical 16) and GPIO24 (physical 18).
If the wires were actually plugged into physical positions 23/24 (= GPIO11/GPIO8, SPI pins),
`diagnose_sensors.py --display` detects that via the chip's ACK and prints the config fix.

E-paper impact: GPIO23 was reserved as the S1-Echo migration target and GPIO24 as EPD BUSY
(§7). With the TM1637 on those pins, the e-paper migration plan must pick new pins if that
display ever returns — plenty are free (GPIO5, 12, 13, 16, 18, 19, 20, 21, 25).

## References

- gpiozero recipes (Button, DistanceSensor): https://gpiozero.readthedocs.io
- Waveshare 2.9" wiki (for the deferred display): https://www.waveshare.com/wiki/2.9inch_e-Paper_Module
- MH-ET 2.9" controller identification: https://forum.arduino.cc/t/mh-et-live-2-9-inch-display-with-gxepd2/1078967
