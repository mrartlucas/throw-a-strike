"""Black-box tests for the display-neutral throw-control presentation API."""

import dataclasses
import unittest

import throw_a_strike.application as application
import throw_a_strike.application.throw_control_presentation as presentation_module
from throw_a_strike.application import (
    InvalidThrowControlPresentationValueError,
    ThrowControlCurveIcon,
    ThrowControlPresentation,
    ThrowControlPrompt,
    ThrowControlStepResult,
    build_throw_control_presentation,
    build_throw_control_step_presentation,
)
from throw_a_strike.domain import (
    ControlStyle,
    CurveLevel,
    LaneArrow,
    PowerFeedback,
    ThrowControlCommand,
    ThrowControlCommandKind,
    ThrowControlMachine,
    ThrowControlOutcomeKind,
    ThrowControlPhase,
    ThrowControlSnapshot,
    THROW_FOUL_SECONDS,
    THROW_WARNING_SECONDS,
)


def advanced_snapshot(
    phase=ThrowControlPhase.SET_AIM,
    curve=CurveLevel.STRAIGHT,
    power=70,
    locked=None,
    warning=False,
):
    machine = ThrowControlMachine(ControlStyle.ADVANCED)
    timestamp = 0.0
    if phase is ThrowControlPhase.SET_AIM:
        return machine.snapshot
    machine.apply(ThrowControlCommand(ThrowControlCommandKind.CONFIRM, timestamp))
    curve_index = list(CurveLevel).index(curve) - list(CurveLevel).index(CurveLevel.STRAIGHT)
    direction = ThrowControlCommandKind.RIGHT if curve_index > 0 else ThrowControlCommandKind.LEFT
    for _ in range(abs(curve_index)):
        machine.apply(ThrowControlCommand(direction, timestamp))
    if phase is ThrowControlPhase.SET_CURVE:
        return machine.snapshot
    if phase is ThrowControlPhase.EARLY_DART_RECOVERY:
        machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT, timestamp, 0, 1, 2))
        return machine.snapshot
    machine.apply(ThrowControlCommand(ThrowControlCommandKind.CONFIRM, timestamp))
    if phase is ThrowControlPhase.SET_POWER:
        if power != 40:
            machine.apply(ThrowControlCommand(ThrowControlCommandKind.TICK, {50: .2, 60: .4, 70: .6, 80: .8, 90: 1.0, 100: 1.2}[power]))
        return machine.snapshot
    lock_time = {40: 0.0, 50: .2, 60: .4, 70: .6, 80: .8, 90: 1.0, 100: 1.2}[power]
    machine.apply(ThrowControlCommand(ThrowControlCommandKind.CONFIRM, lock_time))
    if warning:
        machine.apply(ThrowControlCommand(
            ThrowControlCommandKind.TICK,
            lock_time + THROW_WARNING_SECONDS,
        ))
    if phase is ThrowControlPhase.THROW_READY:
        return machine.snapshot
    if phase is ThrowControlPhase.COMPLETE:
        machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT, lock_time + 1, 0, 1, 2))
    elif phase is ThrowControlPhase.FOUL:
        machine.apply(ThrowControlCommand(
            ThrowControlCommandKind.TICK,
            lock_time + THROW_FOUL_SECONDS,
        ))
    return machine.snapshot


def manual(**changes):
    values = dict(
        control_style=ControlStyle.ADVANCED,
        phase=ThrowControlPhase.SET_AIM,
        primary_prompt=ThrowControlPrompt.SET_AIM,
        secondary_prompt=None,
        curve_level=CurveLevel.STRAIGHT,
        curve_icon=ThrowControlCurveIcon.STRAIGHT,
        power_percent=70,
        power_feedback=PowerFeedback.PERFECT,
        power_locked=False,
        warning_active=False,
        terminal=False,
        outcome_kind=None,
    )
    values.update(changes)
    return ThrowControlPresentation(**values)


class PublicApiTests(unittest.TestCase):
    def test_module_exports_exact_six_symbols_and_application_exports_them(self):
        expected = (
            "InvalidThrowControlPresentationValueError", "ThrowControlPrompt",
            "ThrowControlCurveIcon", "ThrowControlLaneArrowIcon", "ThrowControlPresentation",
            "build_throw_control_presentation", "build_throw_control_step_presentation",
        )
        self.assertEqual(presentation_module.__all__, expected)
        for name in expected:
            self.assertIs(getattr(application, name), getattr(presentation_module, name))
        self.assertFalse(any(name.startswith("_") for name in presentation_module.__all__))

    def test_error_and_frozen_model(self):
        self.assertTrue(issubclass(InvalidThrowControlPresentationValueError, ValueError))
        value = manual()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            value.power_percent = 80

    def test_enum_values_and_order_are_exact(self):
        self.assertEqual([item.value for item in ThrowControlPrompt], [
            "set_aim", "set_curve", "set_power", "throw_ready", "too_soon", "remove_dart",
            "throw_now", "foul", "zero_pins",
        ])
        self.assertEqual([item.value for item in ThrowControlCurveIcon], [
            "left_arrow", "straight_arrow", "right_arrow",
        ])

    def test_prompt_labels_are_locked_and_have_no_invented_completion(self):
        self.assertEqual([item.label for item in ThrowControlPrompt], [
            "SET AIM", "SET CURVE", "SET POWER", "THROW READY", "TOO SOON", "REMOVE DART",
            "THROW NOW", "FOUL", "0 PINS",
        ])
        labels = " ".join(item.label for item in ThrowControlPrompt)
        self.assertNotIn("SHOT READY", labels)
        self.assertNotIn("NO THROW", labels)
        self.assertNotIn("COMPLETE", labels)


class SemanticMappingTests(unittest.TestCase):
    def test_every_curve_maps_to_semantic_icon_and_preserves_values(self):
        expected = [ThrowControlCurveIcon.LEFT] * 3 + [ThrowControlCurveIcon.STRAIGHT] + [ThrowControlCurveIcon.RIGHT] * 3
        for curve, icon in zip(CurveLevel, expected):
            with self.subTest(curve=curve):
                value = build_throw_control_presentation(advanced_snapshot(phase=ThrowControlPhase.SET_CURVE, curve=curve))
                self.assertIs(value.curve_icon, icon)
                self.assertEqual(value.curve_label, curve.label)
                self.assertEqual(value.curve_strength, curve.strength)
                self.assertFalse(any(glyph in value.curve_icon.value for glyph in "←→↑"))

    def test_every_power_and_feedback_label(self):
        feedback = {40: PowerFeedback.WEAK, 50: PowerFeedback.WEAK, 60: PowerFeedback.GOOD,
                    70: PowerFeedback.PERFECT, 80: PowerFeedback.GOOD,
                    90: PowerFeedback.POWER, 100: PowerFeedback.OVERDRIVE}
        for power, expected in feedback.items():
            value = manual(power_percent=power, power_feedback=expected)
            self.assertEqual(value.power_feedback_label, expected.name)
        self.assertEqual(manual(power_percent=70, power_feedback=PowerFeedback.PERFECT).power_feedback_label, "PERFECT")

    def test_invalid_power_and_feedback_are_rejected(self):
        for power in (False, 39, 41, 110, 70.0):
            with self.subTest(power=power), self.assertRaises(InvalidThrowControlPresentationValueError):
                manual(power_percent=power)
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            manual(power_feedback=PowerFeedback.WEAK)

    def test_phase_prompt_terminal_and_outcome_mapping(self):
        cases = (
            (ThrowControlPhase.SET_AIM, ThrowControlPrompt.SET_AIM, None, False, None),
            (ThrowControlPhase.SET_CURVE, ThrowControlPrompt.SET_CURVE, None, False, None),
            (ThrowControlPhase.SET_POWER, ThrowControlPrompt.SET_POWER, None, False, None),
            (ThrowControlPhase.THROW_READY, ThrowControlPrompt.THROW_READY, None, False, None),
            (ThrowControlPhase.EARLY_DART_RECOVERY, ThrowControlPrompt.SET_CURVE, None, False, None),
            (ThrowControlPhase.COMPLETE, None, None, True, ThrowControlOutcomeKind.THROW),
            (ThrowControlPhase.FOUL, ThrowControlPrompt.FOUL, ThrowControlPrompt.ZERO_PINS, True, ThrowControlOutcomeKind.FOUL),
        )
        for phase, primary, secondary, terminal, outcome in cases:
            snapshot = advanced_snapshot(phase=phase)
            value = build_throw_control_presentation(snapshot)
            self.assertEqual((value.primary_prompt, value.secondary_prompt), (primary, secondary))
            self.assertIs(value.terminal, terminal)
            self.assertIs(value.outcome_kind, outcome)

    def test_warning_keeps_ready_and_adds_throw_now(self):
        value = build_throw_control_presentation(advanced_snapshot(phase=ThrowControlPhase.THROW_READY, warning=True))
        self.assertIs(value.primary_prompt, ThrowControlPrompt.THROW_READY)
        self.assertIs(value.secondary_prompt, ThrowControlPrompt.THROW_NOW)

    def test_derived_labels(self):
        self.assertEqual(manual().control_style_label, "Advanced Play")
        quick = build_throw_control_presentation(ThrowControlMachine(ControlStyle.QUICK).snapshot)
        self.assertEqual(quick.control_style_label, "Quick Play")
        self.assertEqual(quick.primary_prompt_label, "THROW READY")
        self.assertIsNone(quick.secondary_prompt_label)


class StyleFlowTests(unittest.TestCase):
    def test_quick_initial_warning_complete_and_foul(self):
        machine = ThrowControlMachine(ControlStyle.QUICK)
        initial = build_throw_control_presentation(machine.snapshot)
        self.assertEqual((initial.primary_prompt, initial.curve_label, initial.curve_icon),
                         (ThrowControlPrompt.THROW_READY, "STR", ThrowControlCurveIcon.STRAIGHT))
        self.assertEqual((initial.power_percent, initial.power_locked, initial.power_feedback),
                         (70, True, PowerFeedback.PERFECT))
        machine.apply(ThrowControlCommand(
            ThrowControlCommandKind.TICK,
            THROW_WARNING_SECONDS,
        ))
        self.assertIs(build_throw_control_presentation(machine.snapshot).secondary_prompt, ThrowControlPrompt.THROW_NOW)
        complete_machine = ThrowControlMachine(ControlStyle.QUICK)
        complete_machine.apply(ThrowControlCommand(ThrowControlCommandKind.DART_HIT, 1, 0, 1, 2))
        complete = build_throw_control_presentation(complete_machine.snapshot)
        self.assertEqual((complete.primary_prompt, complete.secondary_prompt), (None, None))

        foul_machine = ThrowControlMachine(ControlStyle.QUICK)
        foul_machine.apply(ThrowControlCommand(
            ThrowControlCommandKind.TICK,
            THROW_FOUL_SECONDS,
        ))
        foul = build_throw_control_presentation(foul_machine.snapshot)
        self.assertEqual((foul.primary_prompt_label, foul.secondary_prompt_label), ("FOUL", "0 PINS"))

    def test_advanced_selection_ready_recovery_complete_and_foul(self):
        initial = build_throw_control_presentation(advanced_snapshot())
        self.assertEqual((initial.primary_prompt_label, initial.power_locked), ("SET AIM", False))
        moving = build_throw_control_presentation(advanced_snapshot(phase=ThrowControlPhase.SET_POWER, curve=CurveLevel.RIGHT_2, power=90))
        self.assertEqual((moving.curve_level, moving.power_percent, moving.power_feedback, moving.power_locked),
                         (CurveLevel.RIGHT_2, 90, PowerFeedback.POWER, False))
        ready = build_throw_control_presentation(advanced_snapshot(phase=ThrowControlPhase.THROW_READY, curve=CurveLevel.LEFT_1, power=80))
        self.assertEqual((ready.power_feedback, ready.power_locked), (PowerFeedback.GOOD, True))
        recovery = build_throw_control_presentation(advanced_snapshot(phase=ThrowControlPhase.EARLY_DART_RECOVERY, curve=CurveLevel.RIGHT_1))
        self.assertEqual((recovery.curve_level, recovery.primary_prompt_label, recovery.secondary_prompt_label, recovery.power_locked),
                         (CurveLevel.RIGHT_1, "SET CURVE", None, False))
        for phase in (ThrowControlPhase.COMPLETE, ThrowControlPhase.FOUL):
            value = build_throw_control_presentation(advanced_snapshot(phase=phase, curve=CurveLevel.LEFT_2, power=100))
            self.assertEqual((value.curve_level, value.power_percent, value.power_feedback, value.power_locked),
                             (CurveLevel.LEFT_2, 100, PowerFeedback.OVERDRIVE, True))


class BuilderAndValidationTests(unittest.TestCase):
    def test_snapshot_builder_exact_type_immutable_and_stateless(self):
        snapshot = advanced_snapshot()
        before = repr(snapshot)
        first = build_throw_control_presentation(snapshot)
        second = build_throw_control_presentation(snapshot)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(repr(snapshot), before)
        for value in (object(), None):
            with self.assertRaises(InvalidThrowControlPresentationValueError):
                build_throw_control_presentation(value)

        class SnapshotSubclass(ThrowControlSnapshot):
            pass
        subclass = SnapshotSubclass(*dataclasses.astuple(snapshot))
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            build_throw_control_presentation(subclass)

    def test_step_builder_uses_snapshot_only_and_requires_exact_type(self):
        snapshot = advanced_snapshot(phase=ThrowControlPhase.COMPLETE, power=80)
        result = ThrowControlStepResult((), (), 0, 1.0, snapshot)
        self.assertEqual(build_throw_control_step_presentation(result), build_throw_control_presentation(snapshot))
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            build_throw_control_step_presentation(object())

        class ResultSubclass(ThrowControlStepResult):
            pass
        subclass = ResultSubclass((), (), 0, 1.0, snapshot)
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            build_throw_control_step_presentation(subclass)

    def test_wrong_manual_combinations_are_rejected(self):
        invalid_changes = (
            {"primary_prompt": ThrowControlPrompt.SET_POWER},
            {"secondary_prompt": ThrowControlPrompt.THROW_NOW},
            {"warning_active": True},
            {"curve_icon": ThrowControlCurveIcon.LEFT},
            {"power_locked": True},
            {"terminal": True},
            {"outcome_kind": ThrowControlOutcomeKind.THROW},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(InvalidThrowControlPresentationValueError):
                manual(**changes)

    def test_terminal_prompt_and_outcome_consistency_is_enforced(self):
        complete = dict(phase=ThrowControlPhase.COMPLETE, primary_prompt=None,
                        power_locked=True, terminal=True, outcome_kind=ThrowControlOutcomeKind.THROW)
        manual(**complete)
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            manual(**(complete | {"primary_prompt": ThrowControlPrompt.THROW_READY}))
        foul = dict(phase=ThrowControlPhase.FOUL, primary_prompt=ThrowControlPrompt.FOUL,
                    secondary_prompt=ThrowControlPrompt.ZERO_PINS, power_locked=True,
                    terminal=True, outcome_kind=ThrowControlOutcomeKind.FOUL)
        manual(**foul)
        with self.assertRaises(InvalidThrowControlPresentationValueError):
            manual(**(foul | {"secondary_prompt": None}))

    def test_quick_contract_is_enforced(self):
        valid = dict(control_style=ControlStyle.QUICK, phase=ThrowControlPhase.THROW_READY,
                     primary_prompt=ThrowControlPrompt.THROW_READY, power_locked=True)
        manual(**valid)
        for changes in (
            {"phase": ThrowControlPhase.SET_CURVE, "primary_prompt": ThrowControlPrompt.SET_CURVE, "power_locked": False},
            {"curve_level": CurveLevel.LEFT_1, "curve_icon": ThrowControlCurveIcon.LEFT},
            {"power_percent": 80, "power_feedback": PowerFeedback.GOOD},
            {"power_locked": False},
        ):
            with self.assertRaises(InvalidThrowControlPresentationValueError):
                manual(**(valid | changes))

    def test_exact_public_field_types_are_enforced(self):
        changes = (
            {"control_style": "advanced"}, {"phase": "set_curve"},
            {"primary_prompt": "set_curve"}, {"secondary_prompt": "throw_now"},
            {"curve_level": "straight"}, {"curve_icon": "straight_arrow"},
            {"power_feedback": "good"}, {"power_locked": 0},
            {"warning_active": 0}, {"terminal": 0}, {"outcome_kind": "throw"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(InvalidThrowControlPresentationValueError):
                manual(**change)


if __name__ == "__main__":
    unittest.main()
