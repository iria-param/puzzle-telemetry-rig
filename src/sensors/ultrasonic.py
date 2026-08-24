"""HC-SR04 helpers.

Each echo line must use the voltage divider described in ``docs/wiring.md``.
``HCSR04Reader`` measures on demand so callers can poll multiple sensors in
sequence and avoid ultrasonic cross-talk.
"""

import time

from gpiozero import DigitalInputDevice, DigitalOutputDevice


class HCSR04Reader:
    """Read one HC-SR04 sensor without continuously triggering it."""

    def __init__(self, trigger: int, echo: int, echo_timeout_s: float, max_distance_cm: float):
        self.trigger = DigitalOutputDevice(trigger, initial_value=False)
        self.echo = DigitalInputDevice(echo, pull_up=False)
        self.echo_timeout_s = echo_timeout_s
        self.max_distance_cm = max_distance_cm

    def read_cm(self) -> float | None:
        """Return the distance in cm, or ``None`` if no valid echo arrives."""
        self.trigger.on()
        time.sleep(0.00001)  # HC-SR04 trigger pulse: at least 10 microseconds
        self.trigger.off()

        if not self.echo.wait_for_active(timeout=self.echo_timeout_s):
            return None
        pulse_started = time.monotonic()
        if not self.echo.wait_for_inactive(timeout=self.echo_timeout_s):
            return None

        distance_cm = (time.monotonic() - pulse_started) * 17_150
        return distance_cm if distance_cm <= self.max_distance_cm else None

    def close(self) -> None:
        self.trigger.close()
        self.echo.close()
