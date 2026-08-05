import unittest
class MainImportTests(unittest.TestCase):
    def test_main_imports_ten_pin_runner(self):
        import main
        self.assertEqual(main.run_emulator_ten_pin.__name__, "run_emulator_ten_pin")
