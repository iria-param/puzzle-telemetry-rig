import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from display.seven_segment import SessionDisplayRenderer, SessionDisplay, TM1637, encode


class DisplayTests(unittest.TestCase):
    def test_ready_scrolls_entire_prompt(self):
        renderer = SessionDisplayRenderer()
        frames = [renderer.render({'state': 'ready'}, i * .31)['text'] for i in range(20)]
        self.assertIn('STAR', frames)
        self.assertIn('PUZZ', frames)
        self.assertIn('ZZLE', frames)

    def test_failed_stop_and_pending_check_keep_elapsed_time(self):
        renderer = SessionDisplayRenderer()
        for state, elapsed, expected in [('running', 59.9, '0059'),
                                          ('verifying_stop', 60.2, '0100'),
                                          ('running', 61.9, '0101')]:
            frame = renderer.render({'state': state, 'elapsed_s': elapsed}, elapsed)
            self.assertEqual(frame['text'], expected)
            self.assertTrue(frame['colon'])

    def test_complete_uses_frozen_result_then_prompt(self):
        renderer = SessionDisplayRenderer(result_hold_s=20)
        session = {'state': 'complete', 'elapsed_s': 83.7}
        renderer.render(session, 0)
        self.assertEqual(renderer.render(session, 1)['text'], '0123')
        self.assertEqual(renderer.render(session, 17)['text'], '0123')
        self.assertEqual(renderer.render(session, 21)['mode'], 'message')

    def test_timeout_reset_and_error_messages(self):
        for session, expected in [
            ({'state': 'ready', 'message': 'Previous session timed out'}, 'TIME'),
            ({'state': 'ready', 'verification': {'state': 'complete'}}, 'RESE'),
            ({'state': 'ready', 'verification': {'state': 'error'}}, 'CHEC'),
        ]:
            renderer = SessionDisplayRenderer()
            frames = [renderer.render(session, i * .31)['text'] for i in range(15)]
            self.assertIn(expected, frames)
        renderer = SessionDisplayRenderer()
        self.assertEqual(renderer.render({'state': 'complete', 'verification': {'state': 'error'}}, 0)['text'], 'ERR ')

    def test_rejected_stop_flashes_not_done_then_resumes_timer(self):
        renderer = SessionDisplayRenderer()
        session = {'state': 'running', 'elapsed_s': 61,
                   'message': 'Puzzle is incomplete - timer continues.'}
        self.assertEqual(renderer.render(session, 10.0)['text'], 'NOT ')
        self.assertEqual(renderer.render(session, 10.7)['text'], 'DONE')
        frame = renderer.render(session, 13.0)
        self.assertEqual((frame['text'], frame['colon'], frame['mode']), ('0101', True, 'timer'))

    def test_start_message_never_triggers_the_notice(self):
        renderer = SessionDisplayRenderer()
        session = {'state': 'running', 'elapsed_s': 1,
                   'message': 'Timer running. Press again to check completion.'}
        frame = renderer.render(session, 0.0)
        self.assertEqual((frame['text'], frame['mode']), ('0001', 'timer'))

    def test_repeat_incomplete_notice_without_observing_checking_state(self):
        renderer = SessionDisplayRenderer()
        session = {'state': 'running', 'elapsed_s': 61,
                   'message': 'Puzzle is incomplete - timer continues.',
                   'feedback_revision': 1}
        self.assertEqual(renderer.render(session, 10)['mode'], 'notice')
        self.assertEqual(renderer.render(session, 13)['mode'], 'timer')
        # The second camera check finishes between display polls. Its state
        # and message are identical, but it is a new result from a new press.
        session.update(feedback_revision=2, elapsed_s=75)
        self.assertEqual(renderer.render(session, 24)['text'], 'NOT ')
        self.assertEqual(renderer.render(session, 24.7)['text'], 'DONE')
        self.assertEqual(renderer.render(session, 27)['text'], '0115')

    def test_repeat_failed_start_replays_reset_or_error_prompt(self):
        for result, expected in [('complete', 'RESE'), ('error', 'CHEC')]:
            renderer = SessionDisplayRenderer()
            session = {'state': 'ready', 'verification': {'state': result},
                       'feedback_revision': 1}
            renderer.render(session, 0)
            self.assertEqual(renderer.render(session, 6.3)['text'], 'STAR')
            session['feedback_revision'] = 2
            renderer.render(session, 10)
            self.assertEqual(renderer.render(session, 11.3)['text'], expected)

    def test_stop_check_error_flashes_err(self):
        renderer = SessionDisplayRenderer()
        session = {'state': 'running', 'elapsed_s': 30,
                   'message': 'verification failed: camera frame is not ready'}
        self.assertEqual(renderer.render(session, 5.0)['text'], 'ERR ')
        self.assertEqual(renderer.render(session, 8.0)['text'], '0030')

    def test_all_rendered_text_is_uppercase(self):
        sessions = [{'state': 'ready'}, {'state': 'running', 'elapsed_s': 10},
                    {'state': 'complete', 'elapsed_s': 5},
                    {'state': 'complete', 'verification': {'state': 'error'}},
                    {'state': 'validating_start'}, {'state': 'saving_abandoned'},
                    {'state': 'running', 'elapsed_s': 9,
                     'message': 'Puzzle is incomplete - timer continues.'}]
        for session in sessions:
            renderer = SessionDisplayRenderer()
            for step in range(12):
                text = renderer.render(session, step * 0.31)['text']
                self.assertEqual(text, text.upper(), f"lowercase leaked: {text!r} for {session}")

    def test_colon_encoding_and_overflow(self):
        self.assertEqual(encode('1234', True), [0x06, 0xdb, 0x4f, 0x66])
        self.assertEqual(SessionDisplayRenderer().render({'state': 'running', 'elapsed_s': 99999}, 0)['text'], '9959')

    def test_disabled_or_unconfirmed_never_opens_gpio(self):
        for settings, expected in [({'enabled': False}, 'disabled'),
                                   ({'enabled': True, 'interface_confirmed': False}, 'blocked')]:
            with patch('display.seven_segment.TM1637') as driver:
                display = SessionDisplay(settings, lambda: {'state': 'ready'})
                display.start()
                time.sleep(.15)
                display.stop()
                driver.assert_not_called()
                self.assertEqual(display.status()['state'], expected)

    def test_missing_display_does_not_crash_worker(self):
        with patch('display.seven_segment.TM1637', side_effect=OSError('no display')):
            display = SessionDisplay({'enabled': True, 'interface_confirmed': True,
                                      'clk': 23, 'dio': 24}, lambda: {'state': 'running', 'elapsed_s': 77})
            display.start()
            time.sleep(.15)
            self.assertTrue(display._thread.is_alive())
            display.stop()
            self.assertEqual(display.status()['state'], 'error')
            self.assertEqual(display.status()['text'], '0117')

    def test_wire_transaction_ack_failure_and_stop(self):
        # Exercise ACK handling without any physical GPIO.
        driver = TM1637.__new__(TM1637)
        driver.clk, driver.dio, driver.handle = 23, 24, 0
        from unittest.mock import Mock
        driver.io = Mock()
        driver.io.gpio_read.return_value = 1
        writes = []
        driver._set = lambda pin, level: writes.append((pin, level))
        with self.assertRaisesRegex(OSError, 'acknowledge'):
            driver._transaction([0x40])
        self.assertEqual(writes[-4:], [(23, 0), (24, 0), (23, 1), (24, 1)])
        driver.io.gpio_read.return_value = 0
        driver._transaction([0x40])


if __name__ == '__main__':
    unittest.main()
