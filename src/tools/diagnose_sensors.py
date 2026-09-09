"""Sonar + display hardware diagnostic with a plain-language VERDICT.

Answers one question: is the fault fixable in code (wrong pin assignment ->
exact config change printed) or is it wiring (which leg to check printed)?

    sudo systemctl stop puzzle-dashboard.service   # pins must be free first
    python src/tools/diagnose_sensors.py           # sonar scan + verdict
    python src/tools/diagnose_sensors.py --json    # raw per-sensor JSON only
    python src/tools/diagnose_sensors.py --display # TM1637 ACK pin probe

Safety rules kept from the original tool: only Trig pins are ever driven as
outputs; Echo pins remain pulled-down inputs (so a mis-plugged divider is
never driven). The cross-pair scan therefore covers a sensor plugged into
MIXED header positions, but cannot see Trig/Echo swapped at one position —
that case appears as "no response" and is listed in the wiring checklist.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import lgpio
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sensors.ultrasonic import HCSR04Reader


def edge_test(trigger, echo, count=20):
    handle = lgpio.gpiochip_open(0)
    events = []
    callback = None
    outcomes = Counter()
    distances = []
    try:
        lgpio.gpio_claim_output(handle, trigger, 0)
        lgpio.gpio_claim_alert(handle, echo, lgpio.BOTH_EDGES, lgpio.SET_PULL_DOWN)
        callback = lgpio.callback(handle, echo, lgpio.BOTH_EDGES,
                                 lambda chip, pin, level, tick: events.append((level, tick)))
        time.sleep(0.1)
        for _ in range(count):
            events.clear()
            if lgpio.gpio_read(handle, echo):
                outcomes['echo_high_before_trigger'] += 1
                time.sleep(0.1)
                continue
            lgpio.gpio_write(handle, trigger, 1)
            time.sleep(0.00002)
            lgpio.gpio_write(handle, trigger, 0)
            time.sleep(0.12)  # Includes callback delivery time; never ping concurrently.
            captured = list(events)
            rise = next((tick for level, tick in captured if level == 1), None)
            fall = next((tick for level, tick in captured if level == 0 and rise is not None and tick > rise), None)
            if rise is None:
                outcomes['no_rising_edge'] += 1
            elif fall is None:
                outcomes['no_falling_edge'] += 1
            else:
                distance = (fall - rise) / 1e9 * 17150
                outcomes['valid' if 2 <= distance <= 400 else 'out_of_range'] += 1
                distances.append(round(distance, 2))
        return {'outcomes': dict(outcomes), 'distances_cm': distances,
                'echo_final_level': lgpio.gpio_read(handle, echo)}
    finally:
        if callback is not None:
            callback.cancel()
        lgpio.gpiochip_close(handle)


def scan_all_pairs(pins, count=10):
    """Configured pairs first, then cross pairs (Trig of one x Echo of the other)."""
    combos = [
        ('position 1 (configured)', pins['sensor1_trigger'], pins['sensor1_echo']),
        ('position 2 (configured)', pins['sensor2_trigger'], pins['sensor2_echo']),
        ('cross A (S1 Trig + S2 Echo)', pins['sensor1_trigger'], pins['sensor2_echo']),
        ('cross B (S2 Trig + S1 Echo)', pins['sensor2_trigger'], pins['sensor1_echo']),
    ]
    results = []
    for label, trigger, echo in combos:
        result = edge_test(trigger, echo, count)
        result.update(label=label, trigger_bcm=trigger, echo_bcm=echo)
        results.append(result)
        time.sleep(0.2)
    return results


def _responds(result, count=10):
    return result['outcomes'].get('valid', 0) >= max(3, count // 3)


def _stuck_high(result, count=10):
    return result['outcomes'].get('echo_high_before_trigger', 0) >= count // 2


def build_verdict(results, pins, count=10):
    """Turn the four scan results into plain-language findings."""
    pos1, pos2, cross_a, cross_b = results
    lines = []

    for result in results:
        if _stuck_high(result, count):
            lines.append(
                f"WIRING FAULT: Echo GPIO{result['echo_bcm']} idles HIGH before any trigger. "
                "A healthy HC-SR04 Echo idles LOW. Check that Echo goes through its 1k+2k "
                "divider (wiring.md section 3) and that the divider's 2k leg reaches GND."
            )

    working = [r for r in results if _responds(r, count)]

    if _responds(pos1, count) and _responds(pos2, count):
        lines.append("BOTH sensor positions respond with real distances - no fault. "
                     "If the dashboard still says NO ECHO, restart it (pins were busy).")
    elif _responds(pos1, count) or _responds(pos2, count):
        good = 'position 1' if _responds(pos1, count) else 'position 2'
        other = 'Sensor 2' if good == 'position 1' else 'Sensor 1'
        lines.append(f"OK: the connected sensor is at {good} and works. NOTHING to fix in code. "
                     f"{other} showing NO ECHO on the dashboard is expected until a second "
                     "sensor is physically connected.")
    elif _responds(cross_a, count):
        lines.append(
            "CODE-FIXABLE: the connected sensor spans MIXED positions - its Trig sits on "
            f"GPIO{pins['sensor1_trigger']}'s header and its Echo on GPIO{pins['sensor2_echo']}'s divider. "
            "Either re-plug the Echo lead to position 1, or fix it in config.yaml:\n"
            f"    sensor1_trigger: {pins['sensor1_trigger']}\n"
            f"    sensor1_echo: {pins['sensor2_echo']}   # was {pins['sensor1_echo']}"
        )
    elif _responds(cross_b, count):
        lines.append(
            "CODE-FIXABLE: the connected sensor spans MIXED positions - its Trig sits on "
            f"GPIO{pins['sensor2_trigger']}'s header and its Echo on GPIO{pins['sensor1_echo']}'s divider. "
            "Either re-plug the Echo lead to position 2, or fix it in config.yaml:\n"
            f"    sensor2_trigger: {pins['sensor2_trigger']}\n"
            f"    sensor2_echo: {pins['sensor1_echo']}   # was {pins['sensor2_echo']}"
        )
    if not working and not any(_stuck_high(r, count) for r in results):
        lines.append(
            "NOT code-fixable: no Trig x Echo combination produced any echo, and all Echo "
            "lines idle LOW (electrically quiet). The fault is physical - check in this order:\n"
            "  1. Sensor VCC leg firmly on a 5V pin (physical 2 or 4) - most common cause\n"
            "  2. Sensor GND leg to any GND pin / shared rail continuity\n"
            "  3. Trig and Echo swapped AT THE SENSOR position - this scan cannot drive Echo\n"
            "     pins to test that: swap the two signal jumpers at the Pi header and re-run\n"
            "  4. Divider mid-node soldering/breadboard contact\n"
            "  5. The sensor module itself (try the known-good second sensor on the same pins)"
        )
    return lines


def display_probe(config):
    """Confirm the TM1637's CLK/DIO pins via its ACK bit and light all digits."""
    print("TM1637 pin probe. Best practice is VCC on a 3.3V pin (physical 1/17); running")
    print("VCC at 5V is out of spec for the Pi's GPIO but was accepted for this rig on")
    print("09 Sep 2026 (see config.yaml -> display). Type 'yes' to continue:")
    if input("> ").strip().lower() != 'yes':
        print("Aborted.")
        return
    from display.seven_segment import TM1637, encode
    settings = config.get('display', {})
    candidates = [
        (settings.get('clk', 23), settings.get('dio', 24), 'configured (BCM - physical pins 16/18)'),
        (11, 8, "if the wires were counted as PHYSICAL positions 23/24 (= GPIO11/GPIO8, the SPI pins)"),
    ]
    seen = set()
    for clk, dio, label in candidates:
        if (clk, dio) in seen:
            continue
        seen.add((clk, dio))
        try:
            driver = TM1637(clk, dio, brightness=5)
            driver.show(encode('8888'))
            time.sleep(1.5)
            driver.show(encode('    '))
            driver.close()
            print(f"ACK OK on CLK=GPIO{clk} DIO=GPIO{dio} ({label}).")
            print("All four digits should have shown 8888. To go live, set in config.yaml:")
            print(f"    display: enabled: true / interface_confirmed: true / clk: {clk} / dio: {dio}")
            return
        except Exception as exc:  # noqa: BLE001 - report and try the next candidate
            print(f"no ACK on CLK=GPIO{clk} DIO=GPIO{dio} ({label}): {exc}")
    print("No candidate pair acknowledged -> wiring: re-seat CLK/DIO/GND, confirm VCC is on")
    print("3.3V, and check which header positions the CLK/DIO wires actually sit on.")


def main():
    parser = argparse.ArgumentParser(description='Puzzle-rig hardware diagnostic with verdict.')
    parser.add_argument('--json', action='store_true', help='raw per-configured-sensor JSON only')
    parser.add_argument('--display', action='store_true', help='TM1637 CLK/DIO ACK probe')
    args = parser.parse_args()

    config = yaml.safe_load((Path(__file__).resolve().parents[1] / 'config.yaml').read_text())
    if args.display:
        display_probe(config)
        return
    pins, settings = config['pins'], config['sensor_test']

    if args.json:
        for number in (1, 2):
            trigger, echo = pins[f'sensor{number}_trigger'], pins[f'sensor{number}_echo']
            edge_result = edge_test(trigger, echo)
            reader = HCSR04Reader(trigger, echo, settings['echo_timeout_s'], settings['max_distance_cm'])
            values = []
            try:
                for _ in range(20):
                    values.append(reader.read_cm())
                    time.sleep(0.12)
            finally:
                reader.close()
            print(json.dumps({'sensor': number, 'trigger_bcm': trigger, 'echo_bcm': echo,
                              'existing_reader_valid': sum(v is not None for v in values),
                              'existing_reader_cm': values, 'edge_timestamp_test': edge_result}), flush=True)
        return

    print("Scanning all Trig x Echo pairs (hold a hand ~30 cm in front of the connected sensor)...")
    try:
        results = scan_all_pairs(pins)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not claim GPIO ({exc}).")
        print("Most likely the dashboard is running - stop it first:")
        print("    sudo systemctl stop puzzle-dashboard.service")
        return
    for result in results:
        distances = result['distances_cm'][:6]
        print(f"  {result['label']:32s} Trig=GPIO{result['trigger_bcm']:<2} Echo=GPIO{result['echo_bcm']:<2} "
              f"-> {result['outcomes']} {distances}")
    print("\n=== VERDICT ===")
    for line in build_verdict(results, pins):
        print("*", line, "\n")


if __name__ == '__main__':
    main()
