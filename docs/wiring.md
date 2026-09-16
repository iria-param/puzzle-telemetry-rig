# Wiring Reference — Puzzle Telemetry Rig (Phase 1)

Doc ID: PFT/AIRL/WIR/2026-001 · Updated 16 Sep 2026 · Revision 4

This is the current wiring reference. Code uses BCM GPIO numbers; connections below use physical header pin numbers. Sensor 1 and the limit switch now use the even-numbered column.

## 1. Complete connections

| Device terminal | Pi physical pin | BCM / supply | Connection |
|---|---:|---|---|
| HC-SR04 VCC | 4 | 5 V | Direct |
| HC-SR04 GND | 34 | GND | Shared with divider ground |
| HC-SR04 TRIG | 38 | GPIO20 | Direct |
| HC-SR04 ECHO | 40 | GPIO21 | Through divider in §3 |
| Limit switch NO | 26 | GPIO7 | Internal pull-up enabled |
| Limit switch COM | 20 | GND | NC remains disconnected |
| TM1637 VCC | 1 | 3.3 V | Tested module is powered at 3.3 V |
| TM1637 GND | 6 | GND | Direct |
| TM1637 CLK | 16 | GPIO23 | Direct |
| TM1637 DIO | 18 | GPIO24 | Direct |
| Two-pin LED socket + | 1 | 3.3 V | Through 330 Ω resistor |
| Two-pin LED socket − | 6 | GND | Direct; LED always on |
| USB webcam | USB-A | USB | Camera index 0 |
| Sensor 2 | Disconnected | GPIO6/GPIO27 reserved | Disabled in configuration |

The display and LED share the 3.3 V and GND rails. The simple LED socket is separate from the four-wire TM1637 and has no GPIO-controlled behavior.

## 2. Header orientation

Reference view from above the Pi header, oriented with pin 1 at upper left. When looking from underneath with the pin-1 end still at the top, left and right are mirrored. Identify the socket contact that actually mates with Pi pin 1 before numbering solder pads. Printed perfboard row numbers are not Pi pin numbers.

```text
ODD physical pins                  EVEN physical pins
 1  3.3 V: display + LED resistor     2  unused 5 V
 3  unused                           4  5 V: sensor VCC
 5  unused                           6  GND: display + LED
 7  unused                           8  unused
 9  unused                          10  unused
11  unused                          12  unused
13  GPIO27: Sensor 2 reserved        14  unused
15  unused                          16  GPIO23: display CLK
17  unused                          18  GPIO24: display DIO
19  unused                          20  GND: switch COM
21  unused                          22  unused
23  unused                          24  unused
25  unused                          26  GPIO7: switch NO
27  unused                          28  unused
29  unused                          30  unused
31  GPIO6: Sensor 2 reserved         32  unused
33  unused                          34  GND: sensor + divider
35  unused                          36  unused
37  unused                          38  GPIO20: sensor TRIG
39  unused                          40  GPIO21: divided ECHO
```

“Unused” means not connected by this project; it does not imply every pin is a general-purpose signal pin. Physical pin 27 is not Sensor 2's GPIO27; physical pin 13 is GPIO27.

## 3. HC-SR04 Echo divider

```text
Sensor ECHO ---[2.2 kΩ]---●---- physical 40 / GPIO21
                         |
                      [3.3 kΩ]
                         |
                         +---- physical 34 / GND
```

At the junction, join the end of the 2.2 kΩ resistor, the end of the 3.3 kΩ resistor, and the wire to GPIO21. At a nominal 5 V Echo, the divider produces 5 × 3.3 / (2.2 + 3.3) = 3.0 V. Never connect the 5 V Echo output directly to a GPIO.

This replaces earlier diagram values. A 2.2 kΩ series resistor with 4.7 kΩ to ground produces about 3.4 V at 5 V and is not the specified divider. Measure resistor values; the illustrative generated photos are not resistor color-code references.

Power off before soldering or rewiring. With the Pi and modules disconnected, verify each intended connection and check for accidental bridges between supply, ground, and signal pads. Existing photographed tracks are not electrically verified by this document.

## 4. Limit switch

```text
NO  -------------------- physical 26 / GPIO7
COM -------------------- physical 20 / GND
NC  -------------------- disconnected
```

Software uses an internal pull-up and 0.05 s debounce. Released = HIGH/open; pressed = LOW/connected to GND. One press triggers one session action; holding the switch does not repeat it. Release is recorded but does not start or stop timing.

Physical pin 26 is also SPI0 CE1 (GPIO7). Do not assign it to an active SPI device while it is used as the switch input.

## 5. TM1637 and LED

The four-digit module uses the four display connections in §1. Keep this tested module at 3.3 V; its CLK/DIO interface must remain safe for Pi GPIO.

```text
physical 1 / 3.3 V ---[330 Ω]--- LED +
physical 6 / GND --------------- LED −
```

The LED's long leg is normally the anode (+); verify the component's markings if its legs have been cut. This indicator stays on while the 3.3 V rail is powered. The two-pin socket cannot substitute for the TM1637's four connections.

## 6. Live verification and diagnostics

Use the running dashboard first; it owns the GPIO pins. Do not start a second GPIO test process alongside it.

- Confirm diagnostics show Sensor 1 TRIG GPIO20 / ECHO GPIO21.
- Press and release the switch: recent events should show both transitions.
- With an incomplete puzzle, start timing and make two unsuccessful stop attempts, separated by at least three seconds. Each should show NOT DONE briefly and then the advancing timer.
- A new check increments session feedback_revision even if its result matches the previous check. Browser preview and physical display use the same renderer.
- Verify Sensor 1 against a flat target 20–50 cm away. An out_of_range result is not a passing distance test.
- Display acknowledged confirms a protocol response, not visual correctness of every LED segment.

For an isolated hardware test, stop puzzle-dashboard.service first, and restart it when finished. The legacy probe also visits reserved Sensor 2; use the dashboard for the single-sensor acceptance test.

## 7. Validation status — 16 Sep 2026

| Item | Status |
|---|---|
| Limit switch on GPIO7 | Press/release events observed |
| Repeated display feedback | User confirmed working after fix |
| TM1637 power/interface | Previously measured at 3.3 V; live ACK observed |
| Camera | Live API reported connected |
| HC-SR04 on GPIO20/21 | Configuration deployed; out_of_range, known-distance test pending |
| Simple LED socket | Connection specified; separate electrical test not recorded |
| Software checks | 22 unit tests passed; deployed source hashes matched |

Full test record: [bench-test-2026-09-16.md](bench-test-2026-09-16.md).

## 8. Deferred hardware and older diagrams

Sensor 2 remains disconnected. The e-paper display remains deferred. Its previous migration plan is obsolete: GPIO23/24 are used by the TM1637, and GPIO7 is the switch. Re-plan pin usage and SPI ownership before adding it.

The original architecture and flow PDFs are retained as historical snapshots. Use this revision and src/config.yaml for current connections.
