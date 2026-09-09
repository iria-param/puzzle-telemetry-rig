import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# The verdict logic is pure; stub the hardware modules so it imports anywhere.
sys.modules.setdefault('lgpio', MagicMock())
sys.modules.setdefault('gpiozero', MagicMock())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tools.diagnose_sensors import build_verdict  # noqa: E402

PINS = {'sensor1_trigger': 22, 'sensor1_echo': 17,
        'sensor2_trigger': 6, 'sensor2_echo': 27}


def result(label, trigger, echo, valid=0, high=0, silent=0):
    outcomes = {}
    if valid:
        outcomes['valid'] = valid
    if high:
        outcomes['echo_high_before_trigger'] = high
    if silent:
        outcomes['no_rising_edge'] = silent
    return {'label': label, 'trigger_bcm': trigger, 'echo_bcm': echo,
            'outcomes': outcomes, 'distances_cm': [30.0] * valid, 'echo_final_level': 0}


def scan(p1=0, p2=0, xa=0, xb=0, high_on=None):
    rows = [result('position 1 (configured)', 22, 17, valid=p1, silent=10 - p1),
            result('position 2 (configured)', 6, 27, valid=p2, silent=10 - p2),
            result('cross A (S1 Trig + S2 Echo)', 22, 27, valid=xa, silent=10 - xa),
            result('cross B (S2 Trig + S1 Echo)', 6, 17, valid=xb, silent=10 - xb)]
    if high_on is not None:
        rows[high_on]['outcomes'] = {'echo_high_before_trigger': 10}
        rows[high_on]['distances_cm'] = []
    return rows


class VerdictTests(unittest.TestCase):
    def text(self, results):
        return '\n'.join(build_verdict(results, PINS))

    def test_one_healthy_sensor_is_not_a_fault(self):
        text = self.text(scan(p1=10))
        self.assertIn('position 1 and works', text)
        self.assertIn('NOTHING to fix in code', text)
        self.assertIn('expected', text)

    def test_cross_pair_is_code_fixable_with_exact_config(self):
        text = self.text(scan(xa=9))
        self.assertIn('CODE-FIXABLE', text)
        self.assertIn('sensor1_echo: 27', text)

    def test_cross_pair_b(self):
        text = self.text(scan(xb=8))
        self.assertIn('CODE-FIXABLE', text)
        self.assertIn('sensor2_echo: 17', text)

    def test_total_silence_is_wiring(self):
        text = self.text(scan())
        self.assertIn('NOT code-fixable', text)
        self.assertIn('VCC leg', text)
        self.assertIn('swap the two signal jumpers', text)

    def test_echo_stuck_high_points_at_divider(self):
        text = self.text(scan(p2=10, high_on=0))
        self.assertIn('WIRING FAULT', text)
        self.assertIn('GPIO17 idles HIGH', text)
        self.assertIn('divider', text)

    def test_both_working_reports_no_fault(self):
        text = self.text(scan(p1=10, p2=10))
        self.assertIn('no fault', text)


if __name__ == '__main__':
    unittest.main()
