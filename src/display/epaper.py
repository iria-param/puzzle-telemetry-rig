"""MH-ET Live 2.9" e-paper wrapper (SSD1680 panel, Waveshare epd2in9_V2 driver).

Falls back to console output when the driver or panel is missing, so the
state machine is testable with buttons alone — wire the display later.

Wiring (docs/wiring.md §5) matches the Waveshare defaults baked into
epdconfig.py: RST=17, DC=25, CS=8, BUSY=24, SPI0. If test T5 only works
with the legacy driver (older IL3820 batch, wiring.md §7), change the
import below from epd2in9_V2 to epd2in9.

Note: a full e-paper refresh takes ~2 s — that is normal, not a hang.
"""

import logging

log = logging.getLogger(__name__)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class ConsoleDisplay:
    """Stand-in when no e-paper is attached: prints instead of drawing."""

    def show(self, big: str, small: str = ""):
        print(f"[DISPLAY]  {big}   {small}")

    def sleep(self):
        pass


class EPaper:
    def __init__(self):
        from waveshare_epd import epd2in9_V2  # noqa: PLC0415 — import here so absence → fallback
        from PIL import ImageFont

        self.epd = epd2in9_V2.EPD()
        self.epd.init()
        self.epd.Clear(0xFF)
        self._font_big = ImageFont.truetype(FONT, 52)
        self._font_small = ImageFont.truetype(FONT, 18)

    def show(self, big: str, small: str = ""):
        """Draw centred text, landscape (296 x 128). Full refresh (~2 s)."""
        from PIL import Image, ImageDraw

        img = Image.new("1", (self.epd.height, self.epd.width), 255)  # 296 x 128
        d = ImageDraw.Draw(img)
        d.text((148, 50), big, font=self._font_big, anchor="mm", fill=0)
        if small:
            d.text((148, 106), small, font=self._font_small, anchor="mm", fill=0)
        self.epd.display(self.epd.getbuffer(img))

    def sleep(self):
        """Put the panel into deep sleep (do this before long idle periods)."""
        self.epd.sleep()


def make_display():
    """Return a working EPaper, or ConsoleDisplay if anything fails."""
    try:
        disp = EPaper()
        log.info("e-paper initialised (epd2in9_V2)")
        return disp
    except Exception as exc:  # noqa: BLE001 — any failure means: run without panel
        log.warning("e-paper unavailable (%s) — using console fallback", exc)
        return ConsoleDisplay()
