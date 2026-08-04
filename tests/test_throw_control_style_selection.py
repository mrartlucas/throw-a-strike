import unittest
from dataclasses import FrozenInstanceError
from throw_a_strike.application import InputEvent,InputEventKind,ThrowControlStyleSelector,ThrowControlStyleSelectionPhase
from throw_a_strike.domain import ControlStyle

def button(name,t=1,seq=0): return InputEvent(InputEventKind.CONTROL,seq,t,control_id=name)
class SelectorTests(unittest.TestCase):
    def test_defaults_and_timeout(self):
        selector=ThrowControlStyleSelector(2); self.assertEqual(selector.snapshot.selected_style,ControlStyle.QUICK)
        self.assertEqual(selector.apply((),16.999).phase,ThrowControlStyleSelectionPhase.SELECTING)
        result=selector.apply((button("btn_right",17),),17); self.assertTrue(result.timed_out); self.assertEqual(result.confirmed_at,17); self.assertEqual(result.selected_style,ControlStyle.QUICK)
    def test_order_and_confirmation(self):
        result=ThrowControlStyleSelector(0).apply((button("btn_right",2),button("btn_left",2,1),button("btn_a",2,2)),2)
        self.assertTrue(result.confirmed); self.assertEqual(result.selected_style,ControlStyle.QUICK); self.assertEqual(result.confirmed_at,2)
    def test_ignored_and_frozen(self):
        selector=ThrowControlStyleSelector(0); result=selector.apply((button("btn_b"),button("btn_up",seq=1)),1)
        self.assertFalse(result.confirmed)
        with self.assertRaises(FrozenInstanceError): result.timed_out=True
