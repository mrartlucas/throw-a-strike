import unittest
from dataclasses import FrozenInstanceError

import throw_a_strike.application as application
from throw_a_strike.application import (
    InputEvent,
    InputEventKind,
    InvalidThrowControlCoordinatorValueError,
    PortCapabilities,
    ThrowControlCoordinator,
    ThrowControlCoordinatorStage,
    ThrowControlCoordinatorStepError,
    ThrowControlCoordinatorTerminalError,
    ThrowControlStepResult,
)
from throw_a_strike.domain import (
    ControlStyle,
    CurveLevel,
    PowerFeedback,
    ThrowControlCommand,
    ThrowControlCommandKind,
    ThrowControlPhase,
)


class InputStub:
    def __init__(self, batches=(), available=True):
        self.capabilities = PortCapabilities(available)
        self.batches = list(batches)
        self.calls = 0

    def poll(self):
        self.calls += 1
        value = self.batches.pop(0) if self.batches else ()
        if isinstance(value, Exception):
            raise value
        return value


class ClockStub:
    def __init__(self, values=(), available=True, trace=None):
        self.capabilities = PortCapabilities(available)
        self.values = list(values)
        self.calls = 0
        self.trace = trace

    def monotonic_seconds(self):
        self.calls += 1
        if self.trace is not None:
            self.trace.append("clock")
        value = self.values.pop(0) if self.values else 0.0
        if isinstance(value, Exception):
            raise value
        return value


def control(identifier, timestamp=0.0, sequence=0):
    return InputEvent(InputEventKind.CONTROL, sequence, timestamp, control_id=identifier)


def dart(timestamp=4.0, sequence=0, index=7, x=23.0, y=91.0):
    return InputEvent(InputEventKind.DART_HIT, sequence, timestamp, index, x, y)


class CoordinatorTests(unittest.TestCase):
    def make(self, style=ControlStyle.QUICK, batches=(), clocks=(0.0,), started=0.0):
        input_port = InputStub(batches)
        clock = ClockStub(clocks)
        return ThrowControlCoordinator(style, input_port, clock, started), input_port, clock

    def test_public_api_and_stage_order(self):
        names = (
            "InvalidThrowControlCoordinatorValueError", "ThrowControlCoordinatorStage",
            "ThrowControlStepResult", "ThrowControlCoordinatorStepError",
            "ThrowControlCoordinatorTerminalError", "ThrowControlCoordinator",
        )
        module = __import__(
            "throw_a_strike.application.throw_control_coordinator", fromlist=["*"]
        )
        self.assertEqual(module.__all__, names)
        self.assertTrue(all(getattr(application, name) is getattr(module, name) for name in names))
        self.assertEqual([stage.value for stage in ThrowControlCoordinatorStage], [
            "poll_input", "interpret_input", "apply_input", "read_clock", "apply_tick"
        ])
        self.assertTrue(issubclass(ThrowControlCoordinatorStepError, RuntimeError))
        self.assertTrue(issubclass(ThrowControlCoordinatorTerminalError, RuntimeError))
        self.assertTrue(issubclass(InvalidThrowControlCoordinatorValueError, ValueError))

    def test_construction_phases_and_no_operations(self):
        quick, quick_input, quick_clock = self.make(started=12)
        advanced, advanced_input, advanced_clock = self.make(ControlStyle.ADVANCED, started=12)
        self.assertIs(quick.snapshot.phase, ThrowControlPhase.THROW_READY)
        self.assertIs(advanced.snapshot.phase, ThrowControlPhase.SET_CURVE)
        self.assertEqual((quick_input.calls, quick_clock.calls), (0, 0))
        self.assertEqual((advanced_input.calls, advanced_clock.calls), (0, 0))
        self.assertFalse(hasattr(quick, "machine"))
        for name in ("reset", "restart", "run", "loop", "rearm"):
            self.assertFalse(hasattr(quick, name))

    def test_constructor_validation_and_unavailable_capabilities(self):
        valid_input, valid_clock = InputStub(), ClockStub()
        bad_values = (
            ("quick", valid_input, valid_clock),
            (ControlStyle.QUICK, None, valid_clock),
            (ControlStyle.QUICK, valid_input, None),
            (ControlStyle.QUICK, InputStub, valid_clock),
            (ControlStyle.QUICK, valid_input, ClockStub),
        )
        for style, input_port, clock in bad_values:
            with self.subTest(style=style, input_port=input_port, clock=clock):
                with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                    ThrowControlCoordinator(style, input_port, clock, 0)
        ThrowControlCoordinator(ControlStyle.QUICK, InputStub(available=False), ClockStub(available=False), 0)

    def test_capability_and_start_errors_are_normalized(self):
        class BadInput:
            @property
            def capabilities(self):
                raise RuntimeError("capability")
            def poll(self):
                return ()
        class WrongClock:
            capabilities = object()
            def monotonic_seconds(self):
                return 0
        for input_port, clock in ((BadInput(), ClockStub()), (InputStub(), WrongClock())):
            with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                ThrowControlCoordinator(ControlStyle.QUICK, input_port, clock, 0)
        for value in (-1, True, float("inf")):
            with self.assertRaises(InvalidThrowControlCoordinatorValueError) as caught:
                ThrowControlCoordinator(ControlStyle.QUICK, InputStub(), ClockStub(), value)
            self.assertIsNotNone(caught.exception.__cause__)

    def test_quick_dart_complete_preserves_raw_values_and_skips_clock(self):
        event = dart()
        coordinator, input_port, clock = self.make(batches=((event,),), clocks=(999,))
        result = coordinator.step()
        self.assertEqual(result.events, (event,))
        self.assertEqual(result.applied_command_count, 1)
        self.assertIs(result.commands[0].kind, ThrowControlCommandKind.DART_HIT)
        self.assertIsNone(result.tick_timestamp)
        self.assertTrue(result.terminal)
        setup = result.snapshot.outcome.setup
        self.assertEqual((setup.dart_index, setup.aim_x, setup.aim_y), (7, 23, 91))
        self.assertIs(setup.curve_level, CurveLevel.STRAIGHT)
        self.assertEqual(setup.power_percent, 70)
        self.assertEqual((input_port.calls, clock.calls), (1, 0))

    def test_advanced_flow_and_input_before_tick(self):
        batches = (
            (control("btn_right", sequence=9), control("btn_a", sequence=1)),
            (control("btn_a", 0.150),),
            (dart(2, index=3, x=11, y=99),),
        )
        coordinator, input_port, clock = self.make(
            ControlStyle.ADVANCED, batches, (0, 0.150, 50)
        )
        first = coordinator.step()
        self.assertEqual([c.kind for c in first.commands], [
            ThrowControlCommandKind.RIGHT, ThrowControlCommandKind.CONFIRM
        ])
        self.assertIs(first.snapshot.phase, ThrowControlPhase.SET_POWER)
        self.assertEqual(first.tick_timestamp, 0.0)
        second = coordinator.step()
        self.assertIs(second.snapshot.phase, ThrowControlPhase.THROW_READY)
        self.assertEqual(second.snapshot.locked_power_percent, 80)
        self.assertIs(second.snapshot.power_feedback, PowerFeedback.PERFECT)
        third = coordinator.step()
        setup = third.snapshot.outcome.setup
        self.assertEqual((setup.curve_level, setup.power_percent), (CurveLevel.RIGHT_1, 80))
        self.assertEqual((setup.dart_index, setup.aim_x, setup.aim_y), (3, 11, 99))
        self.assertIsNone(third.tick_timestamp)
        self.assertEqual((input_port.calls, clock.calls), (3, 2))

    def test_empty_and_ignored_batches_tick_without_returning_tick_command(self):
        coordinator, input_port, clock = self.make(
            batches=((), (control("btn_home", 1),)), clocks=(0, 1)
        )
        for expected in (0.0, 1.0):
            result = coordinator.step()
            self.assertEqual(result.commands, ())
            self.assertEqual(result.tick_timestamp, expected)
        self.assertEqual((input_port.calls, clock.calls), (2, 2))

    def test_duplicate_order_and_descending_time_failure(self):
        events = (control("btn_right", 2, 9), control("btn_right", 2, 1), control("btn_a", 1, 0))
        coordinator, _, clock = self.make(ControlStyle.ADVANCED, (events,), (3,))
        with self.assertRaises(ThrowControlCoordinatorStepError) as caught:
            coordinator.step()
        error = caught.exception
        self.assertIs(error.stage, ThrowControlCoordinatorStage.APPLY_INPUT)
        self.assertEqual(error.events, events)
        self.assertEqual([c.kind for c in error.commands], [
            ThrowControlCommandKind.RIGHT, ThrowControlCommandKind.RIGHT,
            ThrowControlCommandKind.CONFIRM,
        ])
        self.assertEqual(error.applied_command_count, 2)
        self.assertIs(error.snapshot.curve_level, CurveLevel.RIGHT_2)
        self.assertEqual(clock.calls, 0)
        self.assertIs(error.__cause__, error.cause)

    def test_warning_and_foul_timing(self):
        coordinator, _, _ = self.make(batches=((), ()), clocks=(20, 30))
        warning = coordinator.step()
        self.assertTrue(warning.snapshot.warning_active)
        foul = coordinator.step()
        self.assertIs(foul.snapshot.phase, ThrowControlPhase.FOUL)
        self.assertEqual(foul.tick_timestamp, 30.0)
        self.assertIsNone(foul.snapshot.outcome.setup)

    def test_terminal_guard_precedes_ports(self):
        coordinator, input_port, clock = self.make(batches=((dart(),), (dart(index=2),)), clocks=(1,))
        terminal = coordinator.step().snapshot
        with self.assertRaises(ThrowControlCoordinatorTerminalError) as caught:
            coordinator.step()
        self.assertEqual(caught.exception.snapshot, terminal)
        self.assertEqual((input_port.calls, clock.calls, len(input_port.batches)), (1, 0, 1))

    def test_poll_failure_progress_and_base_exception(self):
        cause = RuntimeError("poll")
        coordinator, _, clock = self.make(batches=(cause,))
        before = coordinator.snapshot
        with self.assertRaises(ThrowControlCoordinatorStepError) as caught:
            coordinator.step()
        error = caught.exception
        self.assertEqual((error.stage, error.events, error.commands, error.applied_command_count),
                         (ThrowControlCoordinatorStage.POLL_INPUT, (), (), 0))
        self.assertEqual(error.snapshot, before)
        self.assertIs(error.__cause__, cause)
        self.assertEqual(clock.calls, 0)

        class StopInput(InputStub):
            def poll(self):
                raise KeyboardInterrupt()
        coordinator = ThrowControlCoordinator(ControlStyle.QUICK, StopInput(), ClockStub(), 0)
        with self.assertRaises(KeyboardInterrupt):
            coordinator.step()

    def test_interpret_failures_retain_only_valid_public_tuple(self):
        valid_but_bad = (dart(x=1.5),)
        for polled, retained in (([dart()], ()), (valid_but_bad, valid_but_bad)):
            coordinator, _, clock = self.make(batches=(polled,))
            before = coordinator.snapshot
            with self.assertRaises(ThrowControlCoordinatorStepError) as caught:
                coordinator.step()
            error = caught.exception
            self.assertIs(error.stage, ThrowControlCoordinatorStage.INTERPRET_INPUT)
            self.assertEqual(error.events, retained)
            self.assertEqual(error.commands, ())
            self.assertEqual(error.snapshot, before)
            self.assertEqual(clock.calls, 0)

    def test_clock_and_tick_failures_preserve_input_progress(self):
        for clock_value, stage, attempted in (
            (RuntimeError("clock"), ThrowControlCoordinatorStage.READ_CLOCK, None),
            (True, ThrowControlCoordinatorStage.APPLY_TICK, None),
            (1.0, ThrowControlCoordinatorStage.APPLY_TICK, 1.0),
        ):
            event = control("btn_right", 2)
            coordinator, _, _ = self.make(ControlStyle.ADVANCED, ((event,),), (clock_value,))
            with self.assertRaises(ThrowControlCoordinatorStepError) as caught:
                coordinator.step()
            error = caught.exception
            self.assertIs(error.stage, stage)
            self.assertEqual(error.applied_command_count, 1)
            self.assertEqual(error.tick_timestamp, attempted)
            self.assertIs(error.snapshot.curve_level, CurveLevel.RIGHT_1)

    def test_result_contract_is_frozen_and_validated(self):
        coordinator, _, _ = self.make(batches=((dart(),),))
        result = coordinator.step()
        with self.assertRaises(FrozenInstanceError):
            result.tick_timestamp = 4
        self.assertIsInstance(ThrowControlStepResult(
            result.events, result.commands, 1, None, result.snapshot
        ), ThrowControlStepResult)
        invalid = (
            (list(result.events), result.commands, 1, None, result.snapshot),
            (result.events, list(result.commands), 1, None, result.snapshot),
            (result.events, result.commands, True, None, result.snapshot),
            (result.events, result.commands, 0, None, result.snapshot),
            (result.events, result.commands, 1, -1, result.snapshot),
        )
        for arguments in invalid:
            with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                ThrowControlStepResult(*arguments)

    def test_no_tick_result_requires_actual_input_progress(self):
        event = dart()
        coordinator, _, _ = self.make(batches=((event,),))
        completed = coordinator.step()
        self.assertIsNone(completed.tick_timestamp)
        self.assertTrue(completed.terminal)

        for events, commands in (((), ()), ((event,), ())):
            with self.subTest(events=events, commands=commands):
                with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                    ThrowControlStepResult(
                        events, commands, len(commands), None, completed.snapshot
                    )

        advanced, _, _ = self.make(
            ControlStyle.ADVANCED,
            (
                (control("btn_right"), control("btn_a")),
                (control("btn_a", 0.150),),
                (dart(2),),
            ),
            (0, 0.150),
        )
        advanced.step()
        advanced.step()
        advanced_completion = advanced.step()
        self.assertIsNone(advanced_completion.tick_timestamp)
        self.assertTrue(advanced_completion.terminal)

        foul, _, _ = self.make(batches=((),), clocks=(30,))
        foul_result = foul.step()
        self.assertEqual(foul_result.tick_timestamp, 30.0)
        self.assertTrue(foul_result.terminal)

    def test_apply_input_error_requires_an_actual_failing_command(self):
        coordinator, _, _ = self.make(ControlStyle.ADVANCED)
        snapshot = coordinator.snapshot
        event = control("btn_right")
        commands = (
            ThrowControlCommand(ThrowControlCommandKind.RIGHT, 0),
            ThrowControlCommand(ThrowControlCommandKind.RIGHT, 0),
            ThrowControlCommand(ThrowControlCommandKind.CONFIRM, 0),
        )
        cause = ValueError("apply")
        valid = ThrowControlCoordinatorStepError(
            ThrowControlCoordinatorStage.APPLY_INPUT,
            (event,), commands, 2, None, snapshot, cause,
        )
        self.assertEqual(valid.applied_command_count, 2)

        invalid_progress = (
            ((), (), 0),
            ((), commands, 0),
            ((event,), commands, len(commands)),
            ((event,), commands, len(commands) + 1),
            ((event,), commands, -1),
            ((event,), commands, True),
        )
        for events, attempted_commands, count in invalid_progress:
            with self.subTest(events=events, commands=attempted_commands, count=count):
                with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                    ThrowControlCoordinatorStepError(
                        ThrowControlCoordinatorStage.APPLY_INPUT,
                        events, attempted_commands, count, None, snapshot, cause,
                    )

    def test_error_value_contracts_and_read_only_properties(self):
        coordinator, _, _ = self.make()
        snapshot = coordinator.snapshot
        cause = ValueError("x")
        error = ThrowControlCoordinatorStepError(
            ThrowControlCoordinatorStage.POLL_INPUT, (), (), 0, None, snapshot, cause
        )
        self.assertIn("poll_input", str(error))
        with self.assertRaises(AttributeError):
            error.stage = ThrowControlCoordinatorStage.READ_CLOCK
        invalid = (
            ("poll_input", (), (), 0, None, snapshot, cause),
            (ThrowControlCoordinatorStage.POLL_INPUT, (object(),), (), 0, None, snapshot, cause),
            (ThrowControlCoordinatorStage.POLL_INPUT, (), (), True, None, snapshot, cause),
            (ThrowControlCoordinatorStage.POLL_INPUT, (), (), 0, None, snapshot, KeyboardInterrupt()),
            (ThrowControlCoordinatorStage.READ_CLOCK, (), (), 0, 1, snapshot, cause),
        )
        for arguments in invalid:
            with self.assertRaises(InvalidThrowControlCoordinatorValueError):
                ThrowControlCoordinatorStepError(*arguments)
        with self.assertRaises(InvalidThrowControlCoordinatorValueError):
            ThrowControlCoordinatorTerminalError(snapshot)


if __name__ == "__main__":
    unittest.main()
