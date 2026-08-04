import unittest
from dataclasses import FrozenInstanceError

import throw_a_strike.application.throw_control_input as interpreter_module
from throw_a_strike.application import (
    InputEvent,
    InputEventKind,
    InvalidThrowControlInputError,
    interpret_throw_control_event,
    interpret_throw_control_events,
)
from throw_a_strike.domain import (
    InvalidThrowControlError,
    ThrowControlCommand,
    ThrowControlCommandKind,
)


def control(control_id="btn_a", sequence=0, timestamp=1.25):
    return InputEvent(InputEventKind.CONTROL, sequence, timestamp,
                      control_id=control_id)


def dart(sequence=0, timestamp=2.5, dart_index=3, x=17.0, y=91.0):
    return InputEvent(InputEventKind.DART_HIT, sequence, timestamp,
                      dart_index=dart_index, x=x, y=y)


class PublicApiTests(unittest.TestCase):
    def test_public_symbols_are_exported_from_application(self):
        self.assertTrue(issubclass(InvalidThrowControlInputError, ValueError))
        self.assertTrue(callable(interpret_throw_control_event))
        self.assertTrue(callable(interpret_throw_control_events))

    def test_module_exports_exactly_the_three_public_symbols(self):
        self.assertEqual(
            interpreter_module.__all__,
            ("InvalidThrowControlInputError", "interpret_throw_control_event",
             "interpret_throw_control_events"),
        )
        self.assertNotIn("_CONTROL_KINDS", interpreter_module.__all__)
        self.assertNotIn("_integral_coordinate", interpreter_module.__all__)


class SingleControlTests(unittest.TestCase):
    def test_exact_controls_map_to_exact_semantic_kinds(self):
        mappings = {
            "btn_left": ThrowControlCommandKind.LEFT,
            "btn_right": ThrowControlCommandKind.RIGHT,
            "btn_a": ThrowControlCommandKind.CONFIRM,
            "btn_b": ThrowControlCommandKind.BACK,
        }
        for control_id, kind in mappings.items():
            with self.subTest(control_id=control_id):
                command = interpret_throw_control_event(control(control_id))
                self.assertIs(command.kind, kind)

    def test_mapped_control_preserves_timestamp_and_has_no_dart_fields(self):
        command = interpret_throw_control_event(control(timestamp=123.75))
        self.assertEqual(command.timestamp, 123.75)
        self.assertEqual((command.dart_index, command.x, command.y),
                         (None, None, None))

    def test_four_named_controls_are_ignored(self):
        for control_id in ("btn_up", "btn_down", "btn_home", "btn_reserved"):
            with self.subTest(control_id=control_id):
                self.assertIsNone(interpret_throw_control_event(control(control_id)))

    def test_unknown_near_match_and_case_variant_controls_are_ignored(self):
        values = ("unknown", "left", "right", "a", "b", "BTN_LEFT",
                  "Btn_Left", "btn-left", "btn_confirm")
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(interpret_throw_control_event(control(value)))

    def test_source_control_event_is_unchanged_and_frozen(self):
        event = control("btn_right", sequence=8, timestamp=7.5)
        before = repr(event)
        interpret_throw_control_event(event)
        self.assertEqual(repr(event), before)
        with self.assertRaises(FrozenInstanceError):
            event.control_id = "btn_left"


class DartTests(unittest.TestCase):
    def test_dart_maps_and_preserves_timestamp_index_and_axis_order(self):
        command = interpret_throw_control_event(
            dart(sequence=99, timestamp=4.125, dart_index=7, x=19, y=103)
        )
        self.assertIs(command.kind, ThrowControlCommandKind.DART_HIT)
        self.assertEqual((command.timestamp, command.dart_index, command.x, command.y),
                         (4.125, 7, 19, 103))
        self.assertIs(type(command.x), int)
        self.assertIs(type(command.y), int)

    def test_dart_index_boundaries_are_accepted(self):
        for index in (0, 11):
            with self.subTest(index=index):
                self.assertEqual(interpret_throw_control_event(
                    dart(dart_index=index)).dart_index, index)

    def test_coordinate_boundaries_and_integer_floats_are_recovered(self):
        command = interpret_throw_control_event(dart(x=0.0, y=127.0))
        self.assertEqual((command.x, command.y), (0, 127))
        self.assertIs(type(command.x), int)
        self.assertIs(type(command.y), int)

    def test_negative_zero_recovers_to_zero_without_affecting_y(self):
        command = interpret_throw_control_event(dart(x=-0.0, y=42.0))
        self.assertEqual((command.x, command.y), (0, 42))

    def test_fractional_coordinates_are_rejected_without_rounding(self):
        for x, y in ((17.0000001, 1), (16.9999999, 1), (1, 6.5)):
            with self.subTest(x=x, y=y), self.assertRaises(
                InvalidThrowControlInputError
            ):
                interpret_throw_control_event(dart(x=x, y=y))

    def test_out_of_range_coordinates_are_wrapped_without_clamping(self):
        for x, y in ((-1, 1), (1, -1), (128, 1), (1, 128)):
            with self.subTest(x=x, y=y):
                with self.assertRaises(InvalidThrowControlInputError) as caught:
                    interpret_throw_control_event(dart(x=x, y=y))
                self.assertIsInstance(caught.exception.__cause__,
                                      InvalidThrowControlError)

    def test_out_of_range_dart_index_is_wrapped_and_chained(self):
        with self.assertRaises(InvalidThrowControlInputError) as caught:
            interpret_throw_control_event(dart(dart_index=12))
        self.assertIsInstance(caught.exception.__cause__, InvalidThrowControlError)

    def test_source_dart_is_not_mutated(self):
        event = dart(x=-0.0, y=127.0)
        before = repr(event)
        interpret_throw_control_event(event)
        self.assertEqual(repr(event), before)

    def test_base_exception_from_command_construction_is_not_swallowed(self):
        class Sentinel(BaseException):
            pass

        original = interpreter_module._ThrowControlCommand

        def fail(*args, **kwargs):
            raise Sentinel

        interpreter_module._ThrowControlCommand = fail
        try:
            with self.assertRaises(Sentinel):
                interpret_throw_control_event(dart())
        finally:
            interpreter_module._ThrowControlCommand = original


class ExactTypeTests(unittest.TestCase):
    def test_non_events_including_bool_and_int_are_rejected(self):
        for value in (None, object(), True, 1, "event"):
            with self.subTest(value=value), self.assertRaises(
                InvalidThrowControlInputError
            ):
                interpret_throw_control_event(value)

    def test_input_event_subclass_is_rejected(self):
        class EventSubclass(InputEvent):
            pass

        with self.assertRaises(InvalidThrowControlInputError):
            interpret_throw_control_event(
                EventSubclass(InputEventKind.CONTROL, 0, 0, control_id="btn_a")
            )

    def test_non_tuple_batches_are_rejected(self):
        for value in ([], iter(()), set(), frozenset()):
            with self.subTest(value=type(value)), self.assertRaises(
                InvalidThrowControlInputError
            ):
                interpret_throw_control_events(value)

    def test_invalid_tuple_item_is_rejected(self):
        for value in (object(), True, 1):
            with self.subTest(value=value), self.assertRaises(
                InvalidThrowControlInputError
            ):
                interpret_throw_control_events((control(), value))

    def test_subclass_item_is_rejected_before_interpretation(self):
        class EventSubclass(InputEvent):
            pass

        child = EventSubclass(InputEventKind.CONTROL, 1, 1, control_id="btn_b")
        with self.assertRaises(InvalidThrowControlInputError):
            interpret_throw_control_events((control(), child))


class BatchTests(unittest.TestCase):
    def test_empty_and_ignored_batches_return_exact_empty_tuple(self):
        for events in ((), (control("btn_up"), control("other"))):
            result = interpret_throw_control_events(events)
            self.assertEqual(result, ())
            self.assertIs(type(result), tuple)

    def test_one_event_returns_one_command_tuple(self):
        result = interpret_throw_control_events((control("btn_left"),))
        self.assertIs(type(result), tuple)
        self.assertEqual(tuple(command.kind for command in result),
                         (ThrowControlCommandKind.LEFT,))

    def test_mixed_batch_omits_ignored_and_preserves_supplied_order(self):
        events = (control("btn_right", 90, 5), control("btn_a", 1, 4),
                  control("btn_up", 2, 3), dart(70, 2, 8, 11, 99),
                  control("btn_b", 3, 1))
        result = interpret_throw_control_events(events)
        self.assertEqual(tuple(command.kind for command in result), (
            ThrowControlCommandKind.RIGHT, ThrowControlCommandKind.CONFIRM,
            ThrowControlCommandKind.DART_HIT, ThrowControlCommandKind.BACK))
        self.assertEqual(tuple(command.timestamp for command in result), (5, 4, 2, 1))

    def test_duplicate_controls_and_darts_with_equal_times_are_preserved(self):
        repeated_control = control("btn_a", sequence=4, timestamp=3)
        repeated_dart = dart(sequence=4, timestamp=3)
        result = interpret_throw_control_events(
            (repeated_control, repeated_control, repeated_dart, repeated_dart)
        )
        self.assertEqual(len(result), 4)
        self.assertEqual(tuple(command.kind for command in result), (
            ThrowControlCommandKind.CONFIRM, ThrowControlCommandKind.CONFIRM,
            ThrowControlCommandKind.DART_HIT, ThrowControlCommandKind.DART_HIT))
        self.assertEqual(tuple(command.timestamp for command in result), (3, 3, 3, 3))

    def test_sequence_gaps_duplicates_and_descents_do_not_change_order(self):
        events = (control("btn_b", 100), control("btn_left", 100),
                  control("btn_right", 2))
        result = interpret_throw_control_events(events)
        self.assertEqual(tuple(command.kind for command in result), (
            ThrowControlCommandKind.BACK, ThrowControlCommandKind.LEFT,
            ThrowControlCommandKind.RIGHT))
        self.assertFalse(hasattr(result[0], "sequence"))

    def test_source_tuple_and_events_remain_unchanged(self):
        events = (control("btn_a"), dart())
        before = repr(events)
        interpret_throw_control_events(events)
        self.assertEqual(repr(events), before)

    def test_invalid_later_event_raises_instead_of_returning_partial_result(self):
        events = (control("btn_a"), dart(x=128))
        with self.assertRaises(InvalidThrowControlInputError):
            interpret_throw_control_events(events)

    def test_calls_do_not_retain_mutable_history(self):
        first = interpret_throw_control_events((control("btn_a"),))
        second = interpret_throw_control_events((control("btn_b"),))
        self.assertEqual(first[0].kind, ThrowControlCommandKind.CONFIRM)
        self.assertEqual(second[0].kind, ThrowControlCommandKind.BACK)
        self.assertIsNot(first, second)

    def test_interpreter_never_generates_tick_or_rearmed(self):
        commands = interpret_throw_control_events(
            (control("btn_left"), control("btn_right"), control("btn_a"),
             control("btn_b"), dart())
        )
        kinds = {command.kind for command in commands}
        self.assertNotIn(ThrowControlCommandKind.TICK, kinds)
        self.assertNotIn(ThrowControlCommandKind.REARMED, kinds)


if __name__ == "__main__":
    unittest.main()
