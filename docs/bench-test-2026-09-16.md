# Bench handoff — 16 Sep 2026

## Changes

- HC-SR04 Sensor 1: TRIG BCM20 (physical 38); ECHO BCM21 (physical 40).
- Limit switch: NO BCM7 (physical 26), COM GND (physical 20). Dashboard label and probe follow this mapping.
- TM1637: repeated checks with identical results now replay the display notice. Previously the renderer compared state/message only, so a check that finished between display polls could produce no new notice.
- `StopwatchSession` now publishes a `feedback_revision` after each completed start/stop check. The renderer includes it when deciding whether to restart the feedback animation.
- GPIO assignments and complete electrical connections: [wiring.md](wiring.md).

## Validation

- 22 unit tests passed locally, including regressions for repeated incomplete stops and repeated rejected starts.
- Callback integration test uses the real switch-handler/session methods with mocked GPIO/camera and deferred verification workers. Two incomplete stop checks each produce a notice; elapsed time continues and no completion row is written.
- Updated runtime files were syntax-checked on the Pi. SHA-256 hashes matched the local files after deployment.
- Pi dashboard service remained active; the status API exposed `feedback_revision`, switch events, a connected camera, and an acknowledged display.
- User confirmed the physical display works after testing the fix.

## Remaining checks

- Sensor 1 still reported `out_of_range` at handoff. Confirm stable readings against a flat target at a measured distance; valid distance measurement on the new pins is not yet verified.
- The always-on LED connection is documented but was not separately electrically verified in this test.
- This change did not repeat the power-cut/reboot test or recalibrate puzzle recognition thresholds.

## Preservation

Session CSVs, camera references, and diagnostic captures remain excluded from Git. Existing architecture/system-flow PDFs are preserved as historical snapshots. No session state or collected data was intentionally cleared by this handoff.
