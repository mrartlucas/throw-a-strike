import unittest
from unittest.mock import patch
from throw_a_strike.adapters import SystemMonotonicClockPort
from throw_a_strike.application import ClockPort, InvalidPortValueError, PortCapabilities

class SystemClockTests(unittest.TestCase):
    def test_protocol_and_capability(self):
        clock=SystemMonotonicClockPort(); self.assertIsInstance(clock,ClockPort); self.assertEqual(clock.capabilities,PortCapabilities(True))
    def test_normalizes(self):
        with patch("throw_a_strike.adapters.system_clock.time.monotonic",return_value=3): self.assertEqual(SystemMonotonicClockPort().monotonic_seconds(),3.0)
    def test_invalid_values(self):
        for value in (True,-1,float("nan"),float("inf")):
            with self.subTest(value=value), patch("throw_a_strike.adapters.system_clock.time.monotonic",return_value=value):
                with self.assertRaises(InvalidPortValueError): SystemMonotonicClockPort().monotonic_seconds()
    def test_exception_propagates(self):
        with patch("throw_a_strike.adapters.system_clock.time.monotonic",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): SystemMonotonicClockPort().monotonic_seconds()
