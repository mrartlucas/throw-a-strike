import unittest
from throw_a_strike.application import ThrowControlStyleSelector,build_throw_control_presentation
from throw_a_strike.domain import ControlStyle,ThrowControlMachine
from throw_a_strike.rendering import *

class RendererTests(unittest.TestCase):
    def test_constants_and_determinism(self):
        self.assertEqual((EMULATOR_MAIN_WIDTH,EMULATOR_MAIN_HEIGHT,EMULATOR_RGB888_BYTE_LENGTH),(128,128,49152))
        selection=ThrowControlStyleSelector(0).snapshot; a=render_style_selection_rgb888(selection)
        self.assertIs(type(a),bytes); self.assertEqual(len(a),49152); self.assertEqual(a,render_style_selection_rgb888(selection))
    def test_attempt_and_blink_differ(self):
        p=build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        shown=render_throw_control_rgb888(p,True); hidden=render_throw_control_rgb888(p,False)
        self.assertEqual(len(shown),49152); self.assertNotEqual(shown,hidden)
        self.assertEqual(shown[:88*128*3],hidden[:88*128*3])
