"""START / STOP buttons.

Wiring (docs/wiring.md §4): each button between its GPIO and the GND rail.
Internal pull-ups → idle reads HIGH, pressed reads LOW. gpiozero handles
the inversion and debouncing.
"""

from gpiozero import Button


def make_buttons(start_pin: int = 5, stop_pin: int = 6, bounce_s: float = 0.05):
    """Return (start_button, stop_button)."""
    start = Button(start_pin, pull_up=True, bounce_time=bounce_s)
    stop = Button(stop_pin, pull_up=True, bounce_time=bounce_s)
    return start, stop
