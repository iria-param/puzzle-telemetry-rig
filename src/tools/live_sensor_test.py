"""Live, headless dashboard for the HC-SR04 sensors and limit switch.

Run on the Pi:
    cd ~/phase_1 && source ~/puzzle-venv/bin/activate
    python src/tools/live_sensor_test.py

Use Ctrl+C to stop. The sensors are read one at a time to prevent ultrasonic
cross-talk. A ``NO ECHO`` status means no valid return was received within the
configured range; place a flat object 20-50 cm in front of the sensor to test.
The switch is ``PRESSED`` when it closes the configured GPIO to GND.
"""

import argparse
import os
import sys
import time
from collections import deque
from pathlib import Path

import yaml
from gpiozero import Button

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sensors.ultrasonic import HCSR04Reader


def load_config() -> dict:
    with (Path(__file__).parents[1] / "config.yaml").open() as config_file:
        return yaml.safe_load(config_file)


def format_reading(distance_cm: float | None) -> str:
    return "NO ECHO" if distance_cm is None else f"{distance_cm:6.1f} cm"


def switch_status(switch: Button) -> str:
    return "PRESSED (closed to GND)" if switch.is_pressed else "RELEASED (open)"


def render(
    readings: dict[str, float | None],
    pins: dict,
    switch: Button,
    events: deque[str],
    clear_screen: bool,
) -> None:
    if clear_screen:
        print("\033[2J\033[H", end="")
    print("Puzzle Telemetry Rig - live hardware test")
    print("Ctrl+C to stop. Sensor readings alternate to avoid cross-talk.\n")
    print(
        f"Sensor 1  trigger GPIO{pins['sensor1_trigger']:>2}  "
        f"echo GPIO{pins['sensor1_echo']:>2}  {format_reading(readings['Sensor 1'])}"
    )
    print(
        f"Sensor 2  trigger GPIO{pins['sensor2_trigger']:>2}  "
        f"echo GPIO{pins['sensor2_echo']:>2}  {format_reading(readings['Sensor 2'])}"
    )
    print(f"\nLimit switch  GPIO{pins['limit_switch']:>2}  {switch_status(switch)}")
    if events:
        print("Recent switch events:")
        for event in events:
            print(f"  {event}")
    print(f"\nUpdated {time.strftime('%H:%M:%S')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Display live HC-SR04 and limit-switch readings.")
    parser.add_argument("--once", action="store_true", help="Read each sensor and the switch once, then exit.")
    parser.add_argument("--no-clear", action="store_true", help="Append updates instead of redrawing the terminal.")
    args = parser.parse_args()

    config = load_config()
    pins = config["pins"]
    test_config = config["sensor_test"]
    readers = {
        "Sensor 1": HCSR04Reader(
            pins["sensor1_trigger"],
            pins["sensor1_echo"],
            test_config["echo_timeout_s"],
            test_config["max_distance_cm"],
        ),
        "Sensor 2": HCSR04Reader(
            pins["sensor2_trigger"],
            pins["sensor2_echo"],
            test_config["echo_timeout_s"],
            test_config["max_distance_cm"],
        ),
    }
    readings = {name: None for name in readers}
    switch = Button(
        pins["limit_switch"],
        pull_up=True,
        bounce_time=test_config["switch_bounce_s"],
    )
    events: deque[str] = deque(maxlen=4)

    def record_switch_event(label: str) -> None:
        events.append(f"{time.strftime('%H:%M:%S')}  {label}")

    switch.when_pressed = lambda: record_switch_event("PRESSED")
    switch.when_released = lambda: record_switch_event("RELEASED")

    try:
        while True:
            for name, reader in readers.items():
                readings[name] = reader.read_cm()
                render(readings, pins, switch, events, clear_screen=not args.no_clear)
                if args.once:
                    continue
                time.sleep(test_config["sample_interval_s"])
            if args.once:
                return
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        for reader in readers.values():
            reader.close()
        switch.close()


if __name__ == "__main__":
    main()
