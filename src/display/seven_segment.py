"""Optional TM1637 display; no GPIO is opened until explicitly enabled.

Use only after confirming the controller, BCM wiring, and 3.3 V-safe signals.
The renderer is hardware-independent and uses the dashboard session clock.
"""

import threading
import time


SEGMENTS = dict(zip('0123456789', (0x3f, 0x06, 0x5b, 0x4f, 0x66, 0x6d, 0x7d, 0x07, 0x7f, 0x6f)))
SEGMENTS.update({' ': 0, '-': 0x40, 'A': 0x77, 'C': 0x39, 'D': 0x5e,
                 'E': 0x79, 'F': 0x71, 'H': 0x76, 'I': 0x06, 'L': 0x38,
                 'N': 0x54, 'O': 0x3f, 'P': 0x73, 'R': 0x50, 'S': 0x6d,
                 'T': 0x78, 'U': 0x3e, 'V': 0x3e, 'Y': 0x6e, 'Z': 0x5b})


def encode(text, colon=False):
    values = [SEGMENTS.get(char.upper(), 0) for char in text.ljust(4)[:4]]
    if colon:
        values[1] |= 0x80
    return values


class SessionDisplayRenderer:
    def __init__(self, scroll_step_s=0.3, result_hold_s=20, notice_s=2.4):
        self.scroll_step_s = max(0.1, scroll_step_s)
        self.result_hold_s = max(0, result_hold_s)
        self.notice_s = max(0, notice_s)
        self._key = None
        self._changed = 0

    def render(self, session, now):
        state = session['state']
        # Two checks can finish with identical state/message between display
        # polls. A new result must replay its notice even in that case.
        key = (state, session.get('started_at'), session.get('stopped_at'),
               session.get('message'), session.get('feedback_revision', 0))
        if key != self._key:
            self._key, self._changed = key, now
        age = max(0, now - self._changed)
        verification = session.get('verification') or {}
        message = session.get('message', '')
        text, colon, mode = '    ', False, 'message'
        if state in {'running', 'verifying_stop', 'saving_complete'}:
            # A failed stop must never freeze the physical timer.
            seconds = min(5999, max(0, int(session.get('elapsed_s') or 0)))
            text, colon, mode = f'{seconds // 60:02d}{seconds % 60:02d}', True, 'timer'
            # Brief notice after a rejected stop press: the counter keeps running
            # underneath; the display flashes why, then returns to the time.
            lowered = message.lower()
            if state == 'running' and age < self.notice_s:
                if 'incomplete' in lowered:
                    text, colon, mode = ('NOT ' if int(age / 0.6) % 2 == 0 else 'DONE'), False, 'notice'
                elif any(word in lowered for word in ('fail', 'error', 'not ready', 'cannot')):
                    text, colon, mode = 'ERR ', False, 'notice'
        elif state == 'complete' and verification.get('state') == 'error':
            text = 'ERR '
        elif state == 'complete' and age < self.result_hold_s:
            seconds = min(5999, max(0, int(session.get('elapsed_s') or 0)))
            if int(age) % 4 == 0:
                text = 'DONE'
            else:
                text, colon, mode = f'{seconds // 60:02d}{seconds % 60:02d}', True, 'final_time'
        elif state in {'validating_start', 'saving_abandoned'}:
            text = 'CHEC' if state == 'validating_start' else 'SAVE'
        else:
            prompt = 'START PUZZLE'
            if state == 'ready' and age < 5:
                if 'timed out' in message:
                    prompt = 'TIME OUT'
                elif 'could not be saved' in message:
                    prompt = 'SAVE Err'
                elif verification.get('state') == 'complete':
                    prompt = 'RESET PUZZLE'
                elif verification and verification.get('state') != 'incomplete':
                    prompt = 'CHEC Err'
            padded = '    ' + prompt + '    '
            index = int(age / self.scroll_step_s) % (len(padded) - 3)
            text = padded[index:index + 4]
        # Display policy: uppercase only (D, N, R, T have no uppercase 7-segment
        # shape and keep their standard glyphs; the text itself is uppercase).
        text = text.upper()
        return {'text': text, 'colon': colon, 'mode': mode, 'segments': encode(text, colon)}


class TM1637:
    """LSB-first TM1637 transactions with ACK checks and released HIGH lines.

Module pull-ups must be on a 3.3 V-safe interface (or behind a level shifter).
"""
    def __init__(self, clk, dio, brightness=2):
        import lgpio
        self.io = lgpio
        self.clk, self.dio = clk, dio
        self.brightness = min(7, max(0, int(brightness)))
        self.handle = lgpio.gpiochip_open(0)
        try:
            for pin in (clk, dio):
                lgpio.gpio_claim_output(self.handle, pin, 1, lgpio.SET_OPEN_DRAIN)
        except Exception:
            lgpio.gpiochip_close(self.handle)
            raise

    def _set(self, pin, level):
        self.io.gpio_write(self.handle, pin, level)
        time.sleep(0.0001)

    def _transaction(self, values):
        self._set(self.clk, 1)
        self._set(self.dio, 1)
        self._set(self.dio, 0)
        try:
            for value in values:
                for bit in range(8):
                    self._set(self.clk, 0)
                    self._set(self.dio, (value >> bit) & 1)
                    self._set(self.clk, 1)
                self._set(self.clk, 0)
                self._set(self.dio, 1)
                self._set(self.clk, 1)
                acknowledged = self.io.gpio_read(self.handle, self.dio) == 0
                self._set(self.clk, 0)
                if not acknowledged:
                    raise OSError('TM1637 did not acknowledge; check model, power and wiring')
        finally:
            self._set(self.clk, 0)
            self._set(self.dio, 0)
            self._set(self.clk, 1)
            self._set(self.dio, 1)

    def show(self, segments):
        self._transaction([0x40])
        self._transaction([0xc0, *segments])
        self._transaction([0x88 | self.brightness])

    def close(self):
        self.io.gpiochip_close(self.handle)


class SessionDisplay:
    def __init__(self, settings, session_status, result_hold_s=20):
        self.settings = settings
        self.session_status = session_status
        self.renderer = SessionDisplayRenderer(settings.get('scroll_step_s', 0.3), result_hold_s,
                                               settings.get('notice_s', 2.4))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._status = {'state': 'disabled', 'message': 'Physical output disabled pending wiring/voltage confirmation'}

    def start(self):
        self._thread = threading.Thread(target=self._run, name='session-display', daemon=True)
        self._thread.start()

    def _run(self):
        driver, retry_at = None, 0
        settings = self.settings
        enabled = settings.get('enabled', False)
        safe = settings.get('interface_confirmed', False)
        while not self._stop.is_set():
            now = time.monotonic()
            frame = self.renderer.render(self.session_status(), now)
            status = {'state': 'disabled', 'message': 'Physical output disabled pending wiring/voltage confirmation'}
            if enabled and not safe:
                status = {'state': 'blocked', 'message': 'Confirm controller, BCM pins and 3.3 V-safe signals first'}
            elif enabled:
                try:
                    if driver is None and now >= retry_at:
                        driver = TM1637(settings['clk'], settings['dio'], settings.get('brightness', 2))
                    if driver is not None:
                        driver.show(frame['segments'])
                        status = {'state': 'connected', 'message': 'Display acknowledged'}
                    else:
                        status = {'state': 'error', 'message': 'Display unavailable; retrying'}
                except Exception as exc:
                    status = {'state': 'error', 'message': str(exc)}
                    if driver is not None:
                        driver.close()
                        driver = None
                    retry_at = now + 5
            with self._lock:
                self._status = {**status, **frame}
            self._stop.wait(0.1)
        if driver is not None:
            try:
                driver.show([0, 0, 0, 0])
            except Exception:
                pass
            finally:
                driver.close()

    def status(self):
        with self._lock:
            return self._status.copy()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
