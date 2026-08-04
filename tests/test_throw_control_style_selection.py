import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from throw_a_strike.application import (
    InputEvent, InputEventKind, InvalidThrowControlStyleSelectionValueError,
    ThrowControlStyleSelectionPhase, ThrowControlStyleSelectionSnapshot,
    ThrowControlStyleSelector,
)
from throw_a_strike.domain import ControlStyle


def button(name="btn_a", timestamp=1.0, sequence=0):
    return InputEvent(InputEventKind.CONTROL, sequence, timestamp, control_id=name)


class SelectorTests(unittest.TestCase):
    def test_starts_quick_and_14999_does_not_timeout(self):
        selector = ThrowControlStyleSelector(0)
        self.assertEqual(selector.snapshot.selected_style, ControlStyle.QUICK)
        self.assertEqual(selector.apply((), 14.999).phase, ThrowControlStyleSelectionPhase.SELECTING)

    def test_exact_deadline_wins_before_command(self):
        result = ThrowControlStyleSelector(0).apply((button("btn_right", 15),), 15)
        self.assertTrue(result.timed_out)
        self.assertEqual(result.confirmed_at, 15)
        self.assertEqual(result.selected_style, ControlStyle.QUICK)

    def test_manual_confirmation_strictly_before_deadline(self):
        result = ThrowControlStyleSelector(0).apply((button(timestamp=14.999),), 14.999)
        self.assertTrue(result.confirmed)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.confirmed_at, 14.999)

    def test_a_at_deadline_cannot_confirm_manually(self):
        result = ThrowControlStyleSelector(0).apply((button(timestamp=15),), 15)
        self.assertTrue(result.timed_out)

    def test_command_time_must_be_within_start_and_now(self):
        for selector, event, now in (
            (ThrowControlStyleSelector(2), button(timestamp=1), 2),
            (ThrowControlStyleSelector(0), button(timestamp=2), 1),
        ):
            with self.subTest(event=event):
                with self.assertRaises(InvalidThrowControlStyleSelectionValueError):
                    selector.apply((event,), now)

    def test_invalid_container_rejected_even_when_now_times_out(self):
        with self.assertRaises(InvalidThrowControlStyleSelectionValueError):
            ThrowControlStyleSelector(0).apply([], 15)

    def test_interpreter_called_once_and_order_preserved(self):
        events = (button("btn_right", 2), button("btn_left", 2, 1), button("btn_a", 2, 2))
        with patch("throw_a_strike.application.throw_control_style_selection.interpret_throw_control_events",
                   wraps=__import__("throw_a_strike.application.throw_control_style_selection", fromlist=["interpret_throw_control_events"]).interpret_throw_control_events) as interpret:
            result = ThrowControlStyleSelector(0).apply(events, 2)
        interpret.assert_called_once_with(events)
        self.assertEqual(result.selected_style, ControlStyle.QUICK)

    def test_advanced_manual_confirmation(self):
        result = ThrowControlStyleSelector(0).apply(
            (button("btn_right", 2), button("btn_a", 2, 1)), 2)
        self.assertEqual(result.selected_style, ControlStyle.ADVANCED)

    def test_snapshot_rejects_late_manual_confirmation(self):
        with self.assertRaises(InvalidThrowControlStyleSelectionValueError):
            ThrowControlStyleSelectionSnapshot(ThrowControlStyleSelectionPhase.CONFIRMED,
                ControlStyle.QUICK, 0, 15, False)

    def test_confirmed_selector_ignores_all_later_values(self):
        selector = ThrowControlStyleSelector(0)
        expected = selector.apply((button(timestamp=1),), 1)
        self.assertIs(selector.apply([], -1), expected)

    def test_snapshot_is_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            ThrowControlStyleSelector(0).snapshot.timed_out = True
