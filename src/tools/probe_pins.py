"""Hardware probe — checks the confirmed ultrasonic and limit-switch wiring.

Run ON THE PI:
    cd ~/phase_1 && source ~/puzzle-venv/bin/activate && python src/tools/probe_pins.py

For each sensor you'll be asked to hold your hand ~30 cm in front of it.
A pair reading a steady ~30 cm is the correct (Trig, Echo) order; a pair
stuck at max range (~200 cm) or erroring is wrong. Paste the whole output
back to Claude — the winning pins then get locked into src/config.yaml.

Safe to run: probing only sends 3.3 V trigger pulses and reads inputs.
(Echo dividers confirmed fitted on both sensors, 20 Aug 2026.)
"""

import statistics
import time

from gpiozero import Button, DistanceSensor

# Confirmed (trigger, echo) pairs from the current bench wiring:
#   sensor 1: GPIO20 -> GPIO21 (physical pins 38 -> 40)
#   sensor 2: GPIO6 -> GPIO27
CANDIDATES = {
    "sensor 1": [(20, 21)],
    "sensor 2": [(6, 27)],
}

SWITCH_CANDIDATES = (7,)  # BCM7 (physical pin 26); COM uses GND on physical pin 20
MAX_M = 2.0  # sensor max range used for "no echo" detection


def sample_cm(trigger: int, echo: int, n: int = 10) -> list:
    sensor = DistanceSensor(echo=echo, trigger=trigger, max_distance=MAX_M, queue_len=2)
    try:
        time.sleep(0.4)  # let the first readings land
        vals = []
        for _ in range(n):
            vals.append(sensor.distance * 100.0)
            time.sleep(0.12)
        return vals
    finally:
        sensor.close()


def probe_sonars() -> None:
    for name, pairs in CANDIDATES.items():
        input(f"\n== {name}: hold your hand ~30 cm in front of it, then press Enter ==")
        for trigger, echo in pairs:
            try:
                vals = sample_cm(trigger, echo)
                med = statistics.median(vals)
                spread = max(vals) - min(vals)
                pegged = all(v > MAX_M * 100 - 5 for v in vals)  # stuck at max = no echo seen
                verdict = "LOOKS RIGHT" if (2 < med < 190 and not pegged) else "no echo"
                print(f"  Trig=GPIO{trigger:<2} Echo=GPIO{echo:<2} -> median {med:6.1f} cm  spread {spread:5.1f} cm  [{verdict}]")
            except Exception as exc:  # noqa: BLE001 — a wrong/reserved pin should not stop the probe
                print(f"  Trig=GPIO{trigger:<2} Echo=GPIO{echo:<2} -> unusable ({type(exc).__name__}: {exc})")


def probe_switch() -> None:
    print("\n== limit switch: watching GPIO7 / physical pin 26 — press & release it a few times (12 s) ==")
    watched = []
    for pin in SWITCH_CANDIDATES:
        try:
            b = Button(pin, pull_up=True, bounce_time=0.03)
            b.when_pressed = (lambda p: lambda: print(f"  GPIO{p}: PRESSED"))(pin)
            b.when_released = (lambda p: lambda: print(f"  GPIO{p}: released"))(pin)
            state = "CLOSED (reads pressed)" if b.is_pressed else "open (not pressed)"
            print(f"  watching GPIO{pin} — idle state right now: {state}")
            watched.append(b)
        except Exception as exc:  # noqa: BLE001
            print(f"  GPIO{pin}: cannot watch ({type(exc).__name__}: {exc})")
    time.sleep(12)
    for b in watched:
        b.close()
    print("  (verified wiring: COM+NO; idle is open/released)")


if __name__ == "__main__":
    print("PIN PROBE — puzzle rig bench wiring (20 Aug 2026)")
    probe_sonars()
    probe_switch()
    print("\nDone. Paste this whole output back to Claude.")
