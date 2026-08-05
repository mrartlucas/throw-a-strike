import unittest
class RuntimeImportTests(unittest.TestCase):
    def test_new_and_diagnostic_runtime_exports(self):
        from throw_a_strike.runtime import EmulatorTenPinRuntime, EmulatorTenPinPhase, run_emulator_ten_pin, EmulatorControlTestRuntime, EmulatorControlTestPhase, run_emulator_control_test
        self.assertTrue(callable(run_emulator_ten_pin)); self.assertTrue(callable(run_emulator_control_test))
        self.assertEqual(EmulatorTenPinPhase.GAME_OVER.value, "game_over"); self.assertEqual(EmulatorControlTestPhase.ROUND_COMPLETE.value, "round_complete")
