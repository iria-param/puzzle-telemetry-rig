"""Exercise real switch/session callbacks with a mocked camera and GPIO."""

import importlib.util
import sys
import threading
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
from display.seven_segment import SessionDisplayRenderer


class DisplayFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('feedback_dashboard', SRC / 'tools/live_dashboard.py')
        cls.dashboard = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'gpiozero': Mock()}):
            spec.loader.exec_module(cls.dashboard)

    def test_two_identical_failed_stops_each_reach_display(self):
        pending = []

        class DeferredThread:
            def __init__(self, target, args=(), name=None, **kwargs):
                self.target, self.args, self.name = target, args, name

            def start(self):
                if self.name != 'session-watchdog':
                    pending.append((self.target, self.args))

        camera, verifier, logger, approach = Mock(), Mock(), Mock(), Mock()
        camera.latest_jpeg.return_value = (b'frame', 1)
        verifier.check.return_value = {'state': 'incomplete'}
        approach.snapshot.return_value = None
        renderer = SessionDisplayRenderer()
        dashboard = self.dashboard
        with patch.object(dashboard.threading, 'Thread', DeferredThread):
            with patch.object(dashboard.time, 'monotonic') as clock:
                clock.return_value = 100
                session = dashboard.StopwatchSession(camera, verifier, logger, approach, 300)
                monitor = dashboard.HardwareMonitor.__new__(dashboard.HardwareMonitor)
                monitor._lock = threading.Lock()
                monitor._events = deque(maxlen=5)
                monitor._on_switch_press = session.on_switch_press

                def press_and_finish():
                    monitor._handle_switch_press()
                    target, args = pending.pop(0)
                    target(*args)
                    monitor._record_switch_event('RELEASED')

                press_and_finish()
                self.assertEqual(session.status()['state'], 'running')
                self.assertEqual(session.status()['feedback_revision'], 1)
                self.assertEqual(renderer.render(session.status(), 100)['mode'], 'timer')

                for check_time, revision in [(110, 2), (120, 3)]:
                    clock.return_value = check_time
                    press_and_finish()
                    status = session.status()
                    self.assertEqual(status['feedback_revision'], revision)
                    self.assertEqual(status['state'], 'running')
                    self.assertEqual(renderer.render(status, check_time)['text'], 'NOT ')
                    self.assertEqual(renderer.render(status, check_time + .7)['text'], 'DONE')
                    clock.return_value = check_time + 3
                    status = session.status()
                    self.assertEqual(status['elapsed_s'], check_time + 3 - 100)
                    self.assertEqual(renderer.render(status, check_time + 3)['mode'], 'timer')

                self.assertTrue(monitor._events[-2].endswith('PRESSED'))
                self.assertTrue(monitor._events[-1].endswith('RELEASED'))
                self.assertEqual(verifier.check.call_count, 3)
                logger.append.assert_not_called()


if __name__ == '__main__':
    unittest.main()
