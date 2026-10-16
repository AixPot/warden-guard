import io, unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from warden_guard.runtime import main

class SignalTests(unittest.TestCase):
    def test_interrupted_once_has_safe_status_and_exit(self):
        with patch('warden_guard.runtime.once',side_effect=InterruptedError()),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['once']),1)
        self.assertEqual(out.getvalue().count('\n'),1)
    def test_interrupted_scheduled_round_stops_scheduler(self):
        with patch('warden_guard.runtime.time.sleep'),patch('warden_guard.runtime.once',side_effect=[InterruptedError(), SystemExit()]) as once,redirect_stdout(io.StringIO()):
            self.assertEqual(main(['schedule']),1)
        self.assertEqual(once.call_count,1)
