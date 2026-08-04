import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from throw_a_strike.application import (
    InvalidPortValueError, PortCapabilities, ThrowControlStyleSelector,
    build_throw_control_presentation,
)
from throw_a_strike.domain import (
    BowlingThrowNumber, BowlingThrowResultKind, PlayerColor, ControlStyle, CurveLevel, ThrowControlCommand, ThrowControlCommandKind,
    ThrowControlMachine, ThrowControlOutcomeKind, ThrowControlPhase,
)
from throw_a_strike.platform import (
    DartsnutButtonId, DartsnutSdkFacade, DartsnutSdkOperation,
    FakeDartsnutSdk, RawDartHit,
)
from throw_a_strike.runtime import (
    ACCEPTED_HOLD_SECONDS, FOUL_HOLD_SECONDS, WRONG_COLOR_HOLD_SECONDS, EmulatorControlTestPhase, EmulatorControlTestRuntime,
    EmulatorControlTestStep, run_emulator_control_test,
)


class Clock:
    def __init__(self, *values): self.values=list(values); self.reads=0
    @property
    def capabilities(self): return PortCapabilities(True)
    def monotonic_seconds(self): self.reads+=1; return float(self.values.pop(0))


def arrive_ball(runtime, clock):
    """Advance an established roll to its exact immutable deadline."""
    if runtime.phase is not EmulatorControlTestPhase.BALL_ROLL:
        raise AssertionError("runtime must be rolling")
    duration = runtime.ball_trajectory.duration_seconds
    clock.values[:] = [value + duration for value in clock.values]
    clock.values.insert(0, runtime.ball_started_at + duration)
    return runtime.step()


def expire_accepted_hold(runtime, clock):
    """Advance an accepted hold to its exact logical deadline."""
    if runtime.phase is not EmulatorControlTestPhase.ACCEPTED_HOLD:
        raise AssertionError("runtime must be in accepted hold")
    deadline = runtime.accepted_timestamp + ACCEPTED_HOLD_SECONDS
    if clock.values and clock.values[0] >= deadline:
        clock.values[0] = deadline
    else:
        clock.values.insert(0, deadline)
    return runtime.step()


def confirmed_selection(style=ControlStyle.QUICK):
    selector = ThrowControlStyleSelector(0)
    controls = []
    if style is ControlStyle.ADVANCED:
        from throw_a_strike.application import InputEvent, InputEventKind
        controls.append(InputEvent(InputEventKind.CONTROL, 0, 1, control_id="btn_right"))
        controls.append(InputEvent(InputEventKind.CONTROL, 1, 1, control_id="btn_a"))
    else:
        from throw_a_strike.application import InputEvent, InputEventKind
        controls.append(InputEvent(InputEventKind.CONTROL, 0, 1, control_id="btn_a"))
    return selector.apply(tuple(controls), 1)


class RetainedDartSdk(FakeDartsnutSdk):
    """Models an emulator dart retained as active after its event was blocked."""
    def __init__(self, retained=RawDartHit(0,77,84)):
        super().__init__(); self.retained=retained


class RuntimeFlowTests(unittest.TestCase):
    def test_every_blue_dart_can_complete_throw_one(self):
        for dart_index in (0,4,8):
            with self.subTest(dart_index=dart_index):
                sdk=FakeDartsnutSdk()
                clock=Clock(1,2); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                sdk.queue_dart_hits((RawDartHit(dart_index,20+dart_index,40+dart_index),))
                self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.BALL_ROLL)
                self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
                self.assertEqual(runtime.round_snapshot.first_result.dart_index,dart_index)

    def test_every_fresh_blue_dart_can_complete_throw_two(self):
        for dart_index in (0,4,8):
            with self.subTest(dart_index=dart_index):
                sdk=FakeDartsnutSdk()
                clock=Clock(1,2,3.5,4); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                sdk.queue_dart_hits((RawDartHit(4,20,40),)); runtime.step(); arrive_ball(runtime,clock); expire_accepted_hold(runtime,clock)
                sdk.queue_dart_hits((RawDartHit(dart_index,60,70),))
                self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.BALL_ROLL)
                self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
                self.assertEqual(runtime.round_snapshot.second_result.dart_index,dart_index)

    def test_throw_one_foul_leaves_every_blue_dart_legal_for_throw_two(self):
        for dart_index in (0,4,8):
            with self.subTest(dart_index=dart_index):
                sdk=FakeDartsnutSdk()
                clock=Clock(1,31,32.5,33); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                runtime.step(); runtime.step()
                sdk.queue_dart_hits((RawDartHit(dart_index,60,70),))
                self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.BALL_ROLL)
                self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
                self.assertEqual(runtime.round_snapshot.second_result.dart_index,dart_index)

    def test_every_other_player_color_is_wrong_without_consuming_throw(self):
        for dart_index in (1,5,9,2,6,10,3,7,11):
            with self.subTest(dart_index=dart_index):
                sdk=FakeDartsnutSdk()
                runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,2,2),0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                sdk.queue_dart_hits((RawDartHit(dart_index,7,9),))
                self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.WRONG_COLOR_HOLD)
                self.assertIsNone(runtime.round_snapshot.first_result)

    def test_stale_active_dart_moves_complete_exact_two_throw_round(self):
        sdk=FakeDartsnutSdk(); sdk.set_active_darts((RawDartHit(0,62,43),))
        clock=Clock(0,1,2,3.5,4,5.5); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.SELECT_STYLE)
        self.assertIsNone(runtime.round_snapshot.first_result)
        sdk.queue_button_events((DartsnutButtonId.A,)); ready=runtime.step()
        self.assertEqual((ready.phase,ready.presentation.phase,runtime.active_player_number,
                          runtime.active_player_color),
                         (EmulatorControlTestPhase.ATTEMPT,ThrowControlPhase.THROW_READY,1,PlayerColor.BLUE))
        self.assertIsNone(ready.accepted_setup)
        sdk.set_active_darts((RawDartHit(0,90,70),)); accepted=runtime.step()
        self.assertEqual(accepted.phase,EmulatorControlTestPhase.BALL_ROLL)
        accepted=arrive_ball(runtime,clock)
        self.assertEqual((accepted.accepted_setup.dart_index,accepted.accepted_setup.aim_x,
                          accepted.accepted_setup.aim_y),(0,90,70))
        self.assertEqual(runtime.round_snapshot.first_result.kind,BowlingThrowResultKind.MISS)
        second=expire_accepted_hold(runtime,clock)
        self.assertEqual((second.phase,runtime.active_player_number,runtime.active_player_color,
                          second.presentation.phase),(EmulatorControlTestPhase.ATTEMPT,1,PlayerColor.BLUE,ThrowControlPhase.THROW_READY))
        sdk.set_active_darts((RawDartHit(0,90,70),RawDartHit(4,35,81))); runtime.step(); arrive_ball(runtime,clock)
        self.assertEqual((runtime.round_snapshot.second_result.dart_index,
                          runtime.round_snapshot.second_result.aim_x,
                          runtime.round_snapshot.second_result.aim_y),(4,35,81))
        self.assertEqual(expire_accepted_hold(runtime,clock).phase,EmulatorControlTestPhase.ROUND_COMPLETE)
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_stale_active_dart_foul_advances_then_raw_four_completes(self):
        sdk=FakeDartsnutSdk(); sdk.set_active_darts((RawDartHit(0,62,43),))
        clock=Clock(0,1,31,32.5,33,34.5); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        runtime.step(); sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.FOUL_HOLD)
        self.assertEqual(runtime.round_snapshot.first_result.kind,BowlingThrowResultKind.FOUL)
        self.assertIsNone(runtime.coordinator.snapshot.outcome.setup)
        second=runtime.step()
        self.assertEqual((second.phase,runtime.active_player_number,runtime.active_player_color,
                          second.presentation.phase),(EmulatorControlTestPhase.ATTEMPT,1,PlayerColor.BLUE,ThrowControlPhase.THROW_READY))
        sdk.set_active_darts((RawDartHit(0,62,43),RawDartHit(4,35,81)))
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.BALL_ROLL)
        self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        self.assertEqual(expire_accepted_hold(runtime,clock).phase,EmulatorControlTestPhase.ROUND_COMPLETE)
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_blue_two_throw_round_uses_raw_zero_then_four_and_diagnostic_miss(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,3.5,4,5.5); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); first=runtime.step()
        self.assertEqual((runtime.round_snapshot.throw_number,runtime.active_player_number,
                          runtime.active_player_color),
                         (BowlingThrowNumber.THROW_ONE,1,PlayerColor.BLUE))
        sdk.queue_dart_hits((RawDartHit(0,21,45),)); runtime.step(); arrive_ball(runtime,clock)
        self.assertEqual(runtime.round_snapshot.first_result.kind,BowlingThrowResultKind.MISS)
        self.assertEqual((runtime.round_snapshot.first_result.dart_index,
                          runtime.round_snapshot.first_result.aim_x,
                          runtime.round_snapshot.first_result.aim_y),(0,21,45))
        second=expire_accepted_hold(runtime,clock)
        self.assertEqual((second.phase,runtime.active_player_number,
                          runtime.active_player_color),
                         (EmulatorControlTestPhase.ATTEMPT,1,PlayerColor.BLUE))
        sdk.queue_dart_hits((RawDartHit(4,88,99),)); runtime.step(); arrive_ball(runtime,clock)
        complete=expire_accepted_hold(runtime,clock)
        self.assertEqual(complete.phase,EmulatorControlTestPhase.ROUND_COMPLETE)
        self.assertTrue(runtime.round_snapshot.complete)
        self.assertEqual(runtime.round_snapshot.second_result.kind,BowlingThrowResultKind.MISS)
        self.assertEqual(runtime.round_snapshot.standing_pins,tuple(range(1,11)))

    def test_wrong_dart_holds_one_second_and_does_not_consume_throw(self):
        self.assertEqual(WRONG_COLOR_HOLD_SECONDS,1.0)
        sdk=FakeDartsnutSdk(); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,2,2.5,2.99,3),0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        coordinator=id(runtime.coordinator)
        sdk.queue_dart_hits((RawDartHit(1,7,9),)); wrong=runtime.step()
        self.assertEqual(wrong.phase,EmulatorControlTestPhase.WRONG_COLOR_HOLD)
        self.assertIsNone(runtime.round_snapshot.first_result)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.WRONG_COLOR_HOLD)
        returned=runtime.step()
        self.assertEqual(returned.phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertEqual(id(runtime.coordinator),coordinator)
        self.assertEqual(runtime.active_player_number,1)

    def test_wrong_dart_at_or_after_deadline_is_one_foul_not_wrong_hold(self):
        for timestamp in (30,31):
            with self.subTest(timestamp=timestamp):
                sdk=FakeDartsnutSdk()
                runtime=EmulatorControlTestRuntime(
                    DartsnutSdkFacade(sdk),Clock(0,timestamp,timestamp,timestamp+.5),0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                sdk.queue_dart_hits((RawDartHit(1,7,9),)); foul=runtime.step()
                self.assertEqual(foul.phase,EmulatorControlTestPhase.FOUL_HOLD)
                self.assertEqual(foul.presentation.phase,ThrowControlPhase.FOUL)
                first=runtime.round_snapshot.first_result
                self.assertEqual(first.kind,BowlingThrowResultKind.FOUL)
                self.assertIsNone(first.dart_index)
                self.assertIsNone(runtime.coordinator.snapshot.outcome.setup)
                self.assertEqual(runtime.round_snapshot.throw_number,BowlingThrowNumber.THROW_TWO)
                held=runtime.step()
                self.assertEqual(held.phase,EmulatorControlTestPhase.FOUL_HOLD)
                self.assertIs(runtime.round_snapshot.first_result,first)
                self.assertIsNone(runtime.round_snapshot.second_result)
                self.assertEqual(sdk.reset_blocking_count,0)

    def test_two_fouls_consume_both_throws_and_complete_round(self):
        sdk=FakeDartsnutSdk(); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,31,32.5,62.5,64),0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.FOUL_HOLD)
        self.assertEqual(runtime.round_snapshot.first_result.kind,BowlingThrowResultKind.FOUL)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertEqual(runtime.round_snapshot.throw_number,BowlingThrowNumber.THROW_TWO)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.FOUL_HOLD)
        self.assertEqual(runtime.round_snapshot.second_result.kind,BowlingThrowResultKind.FOUL)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ROUND_COMPLETE)
        self.assertTrue(runtime.round_snapshot.complete)
        self.assertEqual(runtime.round_snapshot.standing_pins,tuple(range(1,11)))
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_all_round_endings_hold_round_complete_without_io_or_history_changes(self):
        cases=(
            ("throw + throw",("throw","throw"),Clock(1,2,3.5,4,5.5)),
            ("foul + throw",("foul","throw"),Clock(1,31,32.5,33,34.5)),
            ("throw + foul",("throw","foul"),Clock(1,2,3.5,33.5,35)),
            ("foul + foul",("foul","foul"),Clock(1,31,32.5,62.5,64)),
        )
        for name,outcomes,clock in cases:
            with self.subTest(name=name):
                sdk=FakeDartsnutSdk()
                runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                for number,outcome in enumerate(outcomes):
                    if outcome == "throw":
                        sdk.queue_dart_hits((RawDartHit(4*number,20+number,40+number),))
                        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.BALL_ROLL)
                        self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
                        transition=expire_accepted_hold(runtime,clock)
                    else:
                        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.FOUL_HOLD)
                        transition=runtime.step()

                self.assertEqual(transition.phase,EmulatorControlTestPhase.ROUND_COMPLETE)
                self.assertIsNone(transition.accepted_setup)
                self.assertFalse(transition.terminal)
                frame=transition.framebuffer
                calls_before=tuple(sdk.calls); reads_before=clock.reads
                first=runtime.round_snapshot.first_result
                second=runtime.round_snapshot.second_result

                for _ in range(5):
                    held=runtime.step()
                    self.assertEqual(held.phase,EmulatorControlTestPhase.ROUND_COMPLETE)
                    self.assertIsNone(held.accepted_setup)
                    self.assertEqual(held.framebuffer,frame)
                    self.assertFalse(held.terminal)

                self.assertIs(runtime.round_snapshot.first_result,first)
                self.assertIs(runtime.round_snapshot.second_result,second)
                self.assertTrue(runtime.round_snapshot.complete)
                self.assertEqual(sum(result is not None for result in (first,second)),2)
                self.assertEqual(clock.reads,reads_before)
                self.assertEqual(sdk.calls[len(calls_before):],
                                 (DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION,)*5)
                self.assertEqual(sdk.reset_blocking_count,0)

    def test_constructor_and_active_selection_do_not_rearm(self):
        sdk=FakeDartsnutSdk(); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1),0)
        self.assertEqual(sdk.reset_blocking_count,0)
        runtime.step()
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_manual_styles_and_timeout_never_reset_before_frame(self):
        for buttons, clock, style in (((DartsnutButtonId.A,),Clock(1),ControlStyle.QUICK),
                                     ((DartsnutButtonId.RIGHT,DartsnutButtonId.A),Clock(1,2),ControlStyle.ADVANCED),
                                     (None,Clock(15),ControlStyle.QUICK)):
            with self.subTest(style=style,buttons=buttons):
                sdk=FakeDartsnutSdk(); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                if buttons:
                    for button in buttons:
                        sdk.queue_button_events((button,)); result=runtime.step()
                else: result=runtime.step()
                self.assertEqual(result.selection.selected_style,style)
                self.assertEqual(sdk.reset_blocking_count,0)
                self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE,sdk.calls)
                self.assertEqual(sdk.calls[-1],DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION)

    def test_confirmation_only_consumes_batch_and_retained_dart_does_not_replay(self):
        for buttons, expected in (((DartsnutButtonId.A,),ThrowControlPhase.THROW_READY),
                                  ((DartsnutButtonId.RIGHT,DartsnutButtonId.A),ThrowControlPhase.SET_CURVE)):
            with self.subTest(expected=expected):
                sdk=RetainedDartSdk()
                for button in buttons: sdk.queue_button_events((button,))
                runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,2,3,3),0)
                initial=None
                for _ in buttons: initial=runtime.step()
                self.assertEqual((initial.phase,initial.presentation.phase),
                                 (EmulatorControlTestPhase.ATTEMPT,expected))
                self.assertIsNone(initial.accepted_setup)
                self.assertIsNone(runtime.coordinator.snapshot.outcome)
                self.assertIsNone(runtime.accepted_timestamp)
                self.assertEqual(sdk.reset_blocking_count,0)
                active=runtime.step()
                self.assertEqual(active.phase,EmulatorControlTestPhase.ATTEMPT)
                self.assertIsNone(active.accepted_setup)

    def test_style_selection_batch_dart_is_consumed_not_replayed(self):
        sdk=RetainedDartSdk(); sdk.queue_dart_hits((RawDartHit(5,12,34),))
        sdk.queue_button_events((DartsnutButtonId.A,))
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1,2),0)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertIsNone(runtime.coordinator.snapshot.outcome)

    def test_confirmation_constructs_one_coordinator_and_does_not_replay(self):
        sdk=FakeDartsnutSdk(); sdk.queue_button_events((DartsnutButtonId.A,))
        with patch("throw_a_strike.runtime.emulator_control_test.ThrowControlCoordinator", wraps=__import__(
                "throw_a_strike.application",fromlist=["ThrowControlCoordinator"]).ThrowControlCoordinator) as factory:
            runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),Clock(1),0); runtime.step()
        self.assertEqual(factory.call_count,1)
        self.assertEqual(sdk.calls.count(DartsnutSdkOperation.BUTTON_EVENTS),1)

    def test_quick_manual_flow_preserves_dart_and_holds_without_polling(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,2.5); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,))
        initial=runtime.step()
        self.assertEqual(initial.phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertEqual(initial.presentation.phase,ThrowControlPhase.THROW_READY)
        self.assertEqual((initial.presentation.curve_label,initial.presentation.power_percent),("STR",70))
        self.assertIsNotNone(runtime.coordinator)
        sdk.queue_dart_hits((RawDartHit(0,21,45),))
        done=runtime.step(); setup=runtime.coordinator.snapshot.outcome.setup
        self.assertEqual((setup.dart_index,setup.aim_x,setup.aim_y),(0,21,45))
        self.assertEqual(clock.reads,2)  # input timestamp only; terminal skips coordinator tick
        self.assertEqual(done.phase,EmulatorControlTestPhase.BALL_ROLL)
        self.assertIsNone(runtime.round_snapshot.first_result)
        done=arrive_ball(runtime,clock)
        self.assertEqual(done.phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        self.assertIs(runtime.accepted_setup,setup)
        self.assertEqual(runtime.accepted_snapshot,runtime.coordinator.snapshot)
        sdk.queue_dart_hits((RawDartHit(4,5,6),)); before_reads=clock.reads
        before_input=sum(call in (DartsnutSdkOperation.DART_HITS,DartsnutSdkOperation.BUTTON_EVENTS) for call in sdk.calls)
        held=runtime.step()
        self.assertFalse(held.terminal); self.assertEqual(clock.reads,before_reads+1)
        self.assertEqual(sdk.queued_dart_batch_count,1)
        self.assertEqual(sum(call in (DartsnutSdkOperation.DART_HITS,DartsnutSdkOperation.BUTTON_EVENTS) for call in sdk.calls),before_input)
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_advanced_curve_power_80_perfect_and_completion(self):
        # right style, confirm style, right curve+tick, confirm curve+tick,
        # empty meter tick to 80, confirm power+tick, dart timestamp.
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,3,3,4,4,4.8,4.8,5,6)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); self.assertEqual(runtime.step().phase,EmulatorControlTestPhase.SELECT_STYLE)
        sdk.queue_button_events((DartsnutButtonId.A,)); initial=runtime.step()
        self.assertEqual(initial.presentation.phase,ThrowControlPhase.SET_CURVE)
        coordinator_id=id(runtime.coordinator)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); curved=runtime.step()
        self.assertEqual(curved.presentation.curve_level,CurveLevel.RIGHT_1)
        sdk.queue_button_events((DartsnutButtonId.A,)); power=runtime.step()
        self.assertEqual(power.presentation.phase,ThrowControlPhase.SET_POWER)
        moving=runtime.step(); self.assertEqual(moving.presentation.power_percent,80)
        sdk.queue_button_events((DartsnutButtonId.A,)); ready=runtime.step()
        self.assertEqual((ready.presentation.phase,ready.presentation.power_percent,
                          ready.presentation.power_feedback_label),(ThrowControlPhase.THROW_READY,80,"PERFECT"))
        sdk.queue_dart_hits((RawDartHit(0,88,99),)); done=runtime.step()
        setup=runtime.coordinator.snapshot.outcome.setup
        self.assertEqual((setup.curve_level,setup.power_percent,setup.dart_index,setup.aim_x,setup.aim_y),
                         (CurveLevel.RIGHT_1,80,0,88,99))
        self.assertEqual(id(runtime.coordinator),coordinator_id)
        self.assertEqual(done.phase,EmulatorControlTestPhase.BALL_ROLL)
        self.assertEqual(arrive_ball(runtime,clock).phase,EmulatorControlTestPhase.ACCEPTED_HOLD)

    def test_accepted_hold_republishes_then_retries_each_style(self):
        self.assertEqual(ACCEPTED_HOLD_SECONDS,1.5)
        for style in (ControlStyle.QUICK,ControlStyle.ADVANCED):
            with self.subTest(style=style):
                sdk=FakeDartsnutSdk()
                clock=(Clock(1,2,3.49,3.5) if style is ControlStyle.QUICK
                       else Clock(1,2,3,3,4,4,5,6.49,6.5))
                runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
                if style is ControlStyle.ADVANCED:
                    sdk.queue_button_events((DartsnutButtonId.RIGHT,)); runtime.step()
                sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                if style is ControlStyle.ADVANCED:
                    # A dart during curve selection is early, so exercise a completed
                    # advanced snapshot directly after locking curve and power.
                    sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                    sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
                sdk.queue_dart_hits((RawDartHit(0,88,99),)); done=runtime.step()
                self.assertEqual(done.phase,EmulatorControlTestPhase.BALL_ROLL)
                done=arrive_ball(runtime,clock)
                self.assertEqual(done.phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
                sdk.queue_dart_hits((RawDartHit(8,1,2),)); calls=len(sdk.calls)
                held=runtime.step()
                self.assertEqual(held.framebuffer,done.framebuffer)
                self.assertEqual(sdk.calls[calls:],(DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION,))
                self.assertEqual(sdk.queued_dart_batch_count,1)
                old=id(runtime.coordinator); frames=len(sdk.submitted_framebuffers)
                fresh=expire_accepted_hold(runtime,clock)
                expected=(ThrowControlPhase.THROW_READY if style is ControlStyle.QUICK
                          else ThrowControlPhase.SET_CURVE)
                self.assertEqual((fresh.phase,fresh.selection.selected_style,
                                  fresh.presentation.phase,fresh.presentation.curve_label,
                                  fresh.presentation.power_percent),
                                 (EmulatorControlTestPhase.ATTEMPT,style,expected,"STR",70))
                self.assertNotEqual(id(runtime.coordinator),old)
                self.assertIsNone(runtime.coordinator.snapshot.outcome)
                self.assertEqual(sdk.reset_blocking_count,0)
                self.assertEqual(len(sdk.submitted_framebuffers),frames+1)

    def test_accepted_retained_coordinate_does_not_replay_after_exact_hold(self):
        sdk=RetainedDartSdk(); clock=Clock(1,2,3.5,4)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_dart_hits((sdk.retained,)); accepted=runtime.step()
        self.assertEqual(accepted.phase,EmulatorControlTestPhase.BALL_ROLL)
        accepted=arrive_ball(runtime,clock)
        self.assertEqual(accepted.phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        self.assertEqual((accepted.accepted_setup.dart_index,accepted.accepted_setup.aim_x,
                          accepted.accepted_setup.aim_y),(0,77,84))
        fresh=expire_accepted_hold(runtime,clock)
        self.assertEqual(fresh.phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertEqual(sdk.reset_blocking_count,0)
        stable=runtime.step()
        self.assertEqual(stable.phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertIsNone(runtime.coordinator.snapshot.outcome)

    def test_exact_timeout_selects_quick_and_does_not_replay_selection(self):
        sdk=FakeDartsnutSdk(); clock=Clock(15,16); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        result=runtime.step()
        self.assertTrue(result.selection.timed_out)
        self.assertEqual(result.presentation.phase,ThrowControlPhase.THROW_READY)
        # The timeout step's empty selection batch was not polled again by the coordinator.
        self.assertEqual(sdk.calls.count(DartsnutSdkOperation.DART_HITS),1)

    def test_warning_then_foul_has_no_setup(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,21,31); runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        warning=runtime.step()
        self.assertTrue(warning.presentation.warning_active)
        self.assertEqual(warning.presentation.primary_prompt_label,"THROW READY")
        self.assertEqual(warning.presentation.secondary_prompt_label,"THROW NOW")
        foul=runtime.step()
        self.assertEqual(foul.presentation.phase,ThrowControlPhase.FOUL)
        self.assertEqual(foul.presentation.secondary_prompt_label,"0 PINS")
        self.assertEqual(runtime.coordinator.snapshot.outcome.kind,ThrowControlOutcomeKind.FOUL)
        self.assertIsNone(runtime.coordinator.snapshot.outcome.setup)

    def test_recovery_discards_queued_input_before_curve_rearm(self):
        sdk=FakeDartsnutSdk(); clock=Clock(*range(1,12))
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_dart_hits((RawDartHit(0,2,3),)); recovery=runtime.step()
        self.assertEqual((recovery.presentation.primary_prompt_label,
                          recovery.presentation.secondary_prompt_label),
                         ("TOO SOON","REMOVE DART"))

        sdk.set_active_darts((RawDartHit(0,2,3),))
        sdk.queue_button_events((DartsnutButtonId.A,))
        sdk.queue_dart_hits((RawDartHit(4,8,9),))
        reads=clock.reads; input_calls=len(sdk.calls)
        runtime.step()
        self.assertEqual(clock.reads,reads)
        self.assertEqual((sdk.queued_button_batch_count,
                          sdk.queued_dart_batch_count),(1,1))
        self.assertEqual(sdk.calls[input_calls:],(
            DartsnutSdkOperation.ACTIVE_DARTS,
            DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION))

        sdk.set_active_darts(())
        rearmed=runtime.step()
        self.assertEqual((rearmed.phase,rearmed.presentation.phase),
                         (EmulatorControlTestPhase.ATTEMPT,
                          ThrowControlPhase.SET_CURVE))
        self.assertEqual((sdk.queued_button_batch_count,
                          sdk.queued_dart_batch_count),(0,0))
        self.assertEqual(runtime.step().presentation.phase,
                         ThrowControlPhase.SET_CURVE)
        sdk.queue_button_events((DartsnutButtonId.A,))
        self.assertEqual(runtime.step().presentation.phase,
                         ThrowControlPhase.SET_POWER)

        # The baseline was synchronized to absence, so the same raw dart is fresh.
        sdk.set_active_darts((RawDartHit(0,2,3),))
        self.assertEqual(runtime.step().phase,
                         EmulatorControlTestPhase.RECOVERY_HOLD)
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_power_recovery_discards_stale_confirm_and_restarts_at_40(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,3,3,4,4,5,5,5,5)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.A,))
        self.assertEqual(runtime.step().presentation.phase,
                         ThrowControlPhase.SET_POWER)
        sdk.queue_dart_hits((RawDartHit(0,2,3),))
        self.assertEqual(runtime.step().phase,
                         EmulatorControlTestPhase.RECOVERY_HOLD)

        sdk.set_active_darts((RawDartHit(0,2,3),))
        sdk.queue_button_events((DartsnutButtonId.A,))
        runtime.step()
        self.assertEqual(sdk.queued_button_batch_count,1)
        sdk.set_active_darts(())
        rearmed=runtime.step()
        self.assertEqual((rearmed.presentation.phase,
                          rearmed.presentation.power_percent),
                         (ThrowControlPhase.SET_POWER,40))
        self.assertEqual(sdk.queued_button_batch_count,0)
        still_power=runtime.step()
        self.assertEqual((still_power.presentation.phase,
                          still_power.presentation.power_percent),
                         (ThrowControlPhase.SET_POWER,40))
        sdk.queue_button_events((DartsnutButtonId.A,))
        stopped=runtime.step()
        self.assertEqual(stopped.presentation.phase,
                         ThrowControlPhase.THROW_READY)
        self.assertEqual(sdk.reset_blocking_count,0)

    def test_submission_boolean_and_exact_frame_no_retry_or_hardware_calls(self):
        for accepted in (True,False):
            with self.subTest(accepted=accepted):
                sdk=FakeDartsnutSdk(); sdk.queue_framebuffer_result(accepted); clock=Clock(0)
                result=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0).step()
                self.assertIs(result.framebuffer_accepted,accepted)
                self.assertEqual(sdk.submitted_framebuffers,(result.framebuffer,))
                self.assertEqual(len(result.framebuffer),49152)
                self.assertNotIn(DartsnutSdkOperation.BRIGHTNESS,sdk.calls)
                self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE,sdk.calls)

    def test_foul_hold_republishes_then_retries_quick_without_consuming_input(self):
        self.assertEqual(FOUL_HOLD_SECONDS,1.5)
        sdk=FakeDartsnutSdk(); clock=Clock(1,21,31,32.49,32.5)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step(); runtime.step()
        foul=runtime.step()
        self.assertEqual(foul.phase,EmulatorControlTestPhase.FOUL_HOLD)
        self.assertEqual((foul.presentation.primary_prompt_label,foul.presentation.secondary_prompt_label),("FOUL","0 PINS"))
        sdk.queue_dart_hits((RawDartHit(4,5,6),)); calls=len(sdk.calls)
        held=runtime.step()
        self.assertEqual(held.framebuffer,foul.framebuffer)
        self.assertEqual(sdk.calls[calls:],(DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION,))
        self.assertEqual(sdk.queued_dart_batch_count,1)
        self.assertEqual(sdk.reset_blocking_count,0)
        old=id(runtime.coordinator); frame_count=len(sdk.submitted_framebuffers); fresh=runtime.step()
        self.assertEqual(fresh.phase,EmulatorControlTestPhase.ATTEMPT)
        self.assertNotEqual(id(runtime.coordinator),old)
        self.assertEqual(fresh.selection.selected_style,ControlStyle.QUICK)
        self.assertEqual((fresh.presentation.phase,fresh.presentation.curve_label,fresh.presentation.power_percent),
                         (ThrowControlPhase.THROW_READY,"STR",70))
        self.assertFalse(fresh.presentation.warning_active)
        self.assertEqual(sdk.reset_blocking_count,0)
        self.assertEqual(len(sdk.submitted_framebuffers),frame_count+1)

    def test_foul_retry_preserves_advanced_style_and_starts_clean(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,3,3,4,4,4.15,4.15,5,25,35,36.5)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.RIGHT,)); runtime.step()
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()  # lock curve
        runtime.step()  # moving power
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()  # lock power
        runtime.step()  # warning
        foul=runtime.step()
        self.assertEqual(foul.phase,EmulatorControlTestPhase.FOUL_HOLD)
        fresh=runtime.step()
        self.assertEqual((fresh.selection.selected_style,fresh.presentation.phase,
                          fresh.presentation.curve_label,fresh.presentation.power_percent),
                         (ControlStyle.ADVANCED,ThrowControlPhase.SET_CURVE,"STR",70))
        self.assertIsNone(runtime.coordinator.snapshot.outcome)


class StepConsistencyTests(unittest.TestCase):
    def test_ball_roll_requires_complete_presentation_and_hides_setup(self):
        confirmed=confirmed_selection()
        machine=ThrowControlMachine(ControlStyle.QUICK)
        complete=build_throw_control_presentation(machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=0,x=64,y=23)))
        step=EmulatorControlTestStep(
            EmulatorControlTestPhase.BALL_ROLL,confirmed,complete,bytes(49152),True)
        self.assertIsNone(step.accepted_setup)
        with self.assertRaises(InvalidPortValueError):
            EmulatorControlTestStep(
                EmulatorControlTestPhase.BALL_ROLL,confirmed,complete,bytes(49152),True,
                machine.snapshot.outcome.setup)

    def test_rejects_every_impossible_phase_combination(self):
        selecting=ThrowControlStyleSelector(0).snapshot
        confirmed=confirmed_selection()
        ready=build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        recovery_machine=ThrowControlMachine(ControlStyle.ADVANCED)
        recovery=build_throw_control_presentation(recovery_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=0,x=0,y=0)))
        complete_machine=ThrowControlMachine(ControlStyle.QUICK)
        complete=build_throw_control_presentation(complete_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.DART_HIT,1,dart_index=0,x=0,y=0)))
        foul_machine=ThrowControlMachine(ControlStyle.QUICK)
        foul=build_throw_control_presentation(foul_machine.apply(
            ThrowControlCommand(ThrowControlCommandKind.TICK,30)))
        frame=bytes(49152)
        invalid=((EmulatorControlTestPhase.SELECT_STYLE,confirmed,None),
                 (EmulatorControlTestPhase.SELECT_STYLE,selecting,ready),
                 (EmulatorControlTestPhase.ATTEMPT,selecting,ready),
                 (EmulatorControlTestPhase.ATTEMPT,confirmed,recovery),
                 (EmulatorControlTestPhase.ATTEMPT,confirmed,complete),
                 (EmulatorControlTestPhase.RECOVERY_HOLD,confirmed,ready),
                 (EmulatorControlTestPhase.RECOVERY_HOLD,confirmed,complete),
                 (EmulatorControlTestPhase.FOUL_HOLD,confirmed,ready),
                 (EmulatorControlTestPhase.FOUL_HOLD,confirmed,complete),
                 (EmulatorControlTestPhase.BALL_ROLL,confirmed,ready),
                 (EmulatorControlTestPhase.BALL_ROLL,confirmed,foul),
                 (EmulatorControlTestPhase.TERMINAL,confirmed,ready),
                 (EmulatorControlTestPhase.TERMINAL,confirmed,recovery),
                 (EmulatorControlTestPhase.TERMINAL,confirmed,foul))
        for phase,selection,presentation in invalid:
            with self.subTest(phase=phase,presentation=presentation):
                with self.assertRaises(InvalidPortValueError):
                    EmulatorControlTestStep(phase,selection,presentation,frame,True)


class BallRollRuntimeTests(unittest.TestCase):
    def test_roll_reads_clock_once_submits_once_and_consumes_no_queued_input(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,2.4)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_dart_hits((RawDartHit(0,64,23),)); started=runtime.step()
        self.assertEqual(started.phase,EmulatorControlTestPhase.BALL_ROLL)
        sdk.queue_dart_hits((RawDartHit(4,40,40),)); sdk.queue_button_events((DartsnutButtonId.B,))
        calls=len(sdk.calls); frames=len(sdk.submitted_framebuffers); reads=clock.reads
        rolling=runtime.step()
        self.assertEqual(rolling.phase,EmulatorControlTestPhase.BALL_ROLL)
        self.assertEqual(clock.reads,reads+1)
        self.assertEqual(len(sdk.submitted_framebuffers),frames+1)
        self.assertEqual(sdk.calls[calls:],(DartsnutSdkOperation.FRAMEBUFFER_SUBMISSION,))
        self.assertEqual((sdk.queued_dart_batch_count,sdk.queued_button_batch_count),(1,1))
        self.assertEqual(sdk.reset_blocking_count,0)
        self.assertIsNone(runtime.round_snapshot.first_result)

    def test_sparse_arrival_records_one_result_and_exact_logical_deadline(self):
        sdk=FakeDartsnutSdk(); clock=Clock(1,2,20,20)
        runtime=EmulatorControlTestRuntime(DartsnutSdkFacade(sdk),clock,0)
        sdk.queue_button_events((DartsnutButtonId.A,)); runtime.step()
        sdk.queue_dart_hits((RawDartHit(0,120,0),)); runtime.step()
        trajectory=runtime.ball_trajectory
        arrived=runtime.step(); result=runtime.round_snapshot.first_result
        self.assertEqual(arrived.phase,EmulatorControlTestPhase.ACCEPTED_HOLD)
        self.assertEqual(runtime.accepted_timestamp,runtime.ball_started_at+trajectory.duration_seconds)
        self.assertEqual((result.aim_x,result.aim_y),(120,0))
        runtime.step()
        self.assertIs(runtime.round_snapshot.first_result,result)


class RaisingSdk(FakeDartsnutSdk):
    @property
    def running(self):
        raise RuntimeError("running failed")

class CleanupTests(unittest.TestCase):
    def assert_closed_after(self, sdk, call, error=None):
        if error:
            with self.assertRaises(error): call()
        else: call()
        self.assertEqual(sdk.close_count,1)

    def test_closes_after_runtime_construction_failure(self):
        sdk=FakeDartsnutSdk(); self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),object(),0,max_iterations=0),InvalidPortValueError)
    def test_closes_after_running_failure(self):
        sdk=RaisingSdk(); self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(),0),RuntimeError)
    def test_closes_after_step_failure(self):
        sdk=FakeDartsnutSdk(); self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(),0,max_iterations=1),IndexError)
    def test_closes_after_sleeper_failure(self):
        sdk=FakeDartsnutSdk(); self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(0),0,max_iterations=1,
                                              sleeper=lambda _: (_ for _ in ()).throw(ValueError("sleep"))),ValueError)
    def test_closes_after_completion(self):
        sdk=FakeDartsnutSdk(); self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(0),0,max_iterations=1,sleeper=lambda _:None))
    def test_closes_and_propagates_base_exception(self):
        sdk=FakeDartsnutSdk()
        def stop(_): raise KeyboardInterrupt
        self.assert_closed_after(sdk,
            lambda: run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(0),0,max_iterations=1,sleeper=stop),KeyboardInterrupt)

    def test_runner_never_resets_and_closes_once(self):
        sdk=RetainedDartSdk(); sdk.queue_button_events((DartsnutButtonId.A,))
        run_emulator_control_test(DartsnutSdkFacade(sdk),Clock(1),0,max_iterations=1,sleeper=lambda _:None)
        self.assertEqual(sdk.reset_blocking_count,0)
        self.assertNotIn(DartsnutSdkOperation.RESET_BLOCKING_STATE,sdk.calls)
        self.assertEqual(sdk.close_count,1)


class EntryManifestTests(unittest.TestCase):
    def test_main_import_is_safe_and_sdk_import_is_local(self):
        sys.modules.pop("main",None); sys.modules.pop("pydartsnut",None)
        module=importlib.import_module("main")
        self.assertNotIn("pydartsnut",sys.modules)
        source=Path("main.py").read_text()
        self.assertIn("    from pydartsnut import Dartsnut",source)
        for name in ("DartsnutSdkFacade","SystemMonotonicClockPort","run_emulator_control_test"):
            self.assertIn(name,source)
    def test_manifest_and_unchanged_project_dependencies(self):
        config=json.loads(Path("conf.json").read_text())
        self.assertEqual((config["id"],config["name"],config["author"],config["size"]),
                         ("throw-a-strike","Throw a Strike","Throw A Way Games",[128,128]))
