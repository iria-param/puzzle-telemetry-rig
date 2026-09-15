"""Standalone TM1637 four-digit display test.

This tool touches only the configured CLK and DIO pins. It does not start the
camera, ultrasonic sensor, limit switch, dashboard, or session logic.

Safe wiring (Pi physical header numbers):
    Display VCC -> pin 1  (3.3 V)
    Display GND -> pin 6  (GND)
    Display CLK -> pin 16 (BCM GPIO23)
    Display DIO -> pin 18 (BCM GPIO24)
"""

import argparse
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from display.seven_segment import TM1637, encode


def main() -> int:
    parser = argparse.ArgumentParser(description="Test only the TM1637 display")
    parser.add_argument(
        "--i-confirm-3v3",
        action="store_true",
        help="required confirmation that display VCC measures approximately 3.3 V",
    )
    parser.add_argument("--clk", type=int, default=23, help="BCM CLK pin (default: 23)")
    parser.add_argument("--dio", type=int, default=24, help="BCM DIO pin (default: 24)")
    args = parser.parse_args()

    if not args.i_confirm_3v3:
        print("REFUSED: measure display VCC-to-GND first.")
        print("Reconnect only when it reads about 3.3 V, then add --i-confirm-3v3.")
        return 2

    print(f"Testing TM1637 on BCM CLK={args.clk}, DIO={args.dio}")
    display = TM1637(args.clk, args.dio, brightness=7)
    try:
        tests = [
            ("all segments", [0xFF, 0xFF, 0xFF, 0xFF], 3.0),
            ("digits 1234", encode("1234"), 3.0),
            ("word DONE", encode("DONE"), 3.0),
        ]
        for name, segments, duration in tests:
            print(name)
            display.show(segments)
            time.sleep(duration)

        print("counting 0000 through 0009")
        for number in range(10):
            display.show(encode(f"{number:04d}"))
            time.sleep(0.5)

        print("PASS: commands were transmitted. Confirm the patterns were visible.")
        return 0
    except OSError as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        try:
            display.show([0, 0, 0, 0])
        finally:
            display.close()


if __name__ == "__main__":
    raise SystemExit(main())
