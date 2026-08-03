import unittest
from dataclasses import FrozenInstanceError, fields, is_dataclass

from throw_a_strike.application import (
    AcknowledgeResultCommand,
    ApplicationCapabilities,
    ApplicationCommandKind,
    ApplicationCommandResult,
    ApplicationController,
    ApplicationControllerPublishError,
    CancelCommand,
    ConfigureCommand,
    ContinueTransitionCommand,
    DisplayCapabilities,
    FakeMainPresentationPort,
    FakeSecondaryPresentationPort,
    InvalidApplicationCommandError,
    InvalidApplicationControllerValueError,
    InvalidSessionConfigurationError,
    InvalidSessionTransitionError,
    PortCapabilities,
    PresentationPublishError,
    PresentationPublisher,
    PublishCurrentCommand,
    ReplayCommand,
    ScoreboardPlacement,
    SessionPhase,
    StartCommand,
    StorageCapabilities,
    SubmitThrowCommand,
)
from throw_a_strike.domain.bowling import IllegalRollError
from throw_a_strike.domain.config import MatchConfig, Mode, Theme
from throw_a_strike.domain.cumulative import IllegalCumulativeRollError
from throw_a_strike.domain.schedule import (
    PartySetupDefinition,
    build_party_schedule,
    build_remix_schedule,
)


def capabilities(secondary=False, dimensions=False):
    return ApplicationCapabilities(
        DisplayCapabilities(True, 128 if dimensions else None, 160 if dimensions else None),
        DisplayCapabilities(
            secondary, 320 if secondary and dimensions else None,
            200 if secondary and dimensions else None,
        ),
        PortCapabilities(True),
        PortCapabilities(True),
        PortCapabilities(False),
        StorageCapabilities(False, False),
    )


def config(mode=Mode.TEN_PIN, players=1, frames=None, seed=42):
    return MatchConfig(
        mode, Theme.REGULAR, players,
        10 if mode is Mode.TEN_PIN else (frames or 3), seed,
    )


def schedule_for(value):
    if value.mode is Mode.REMIX:
        return build_remix_schedule(value)
    if value.mode is Mode.PARTY:
        catalog = (
            PartySetupDefinition("classic", "triangle", ("pin",), (), (), 40),
            PartySetupDefinition("orbit", "ring", ("orb",), ("pulse",), (), 60),
        )
        return build_party_schedule(value, catalog)
    return None


def controller(secondary=False, dimensions=False):
    caps = capabilities(secondary, dimensions)
    main = FakeMainPresentationPort(DisplayCapabilities(True, None, None))
    second = FakeSecondaryPresentationPort(DisplayCapabilities(True, None, None))
    publisher = PresentationPublisher(main, second)
    return ApplicationController(caps, publisher), main, second


class MutablePort:
    def __init__(self, capability, failure=None, events=None):
        self.capability = capability
        self.failure = failure
        self.presented = []
        self.events = events

    @property
    def capabilities(self):
        return self.capability

    def present(self, model):
        if self.events is not None:
            self.events.append(self)
        if self.failure is not None:
            raise self.failure
        self.presented.append(model)


class CommandValueTests(unittest.TestCase):
    def test_command_enum_is_exact(self):
        self.assertEqual(
            [(item.name, item.value) for item in ApplicationCommandKind],
            [
                ("CONFIGURE", "configure"), ("START", "start"),
                ("SUBMIT_THROW", "submit_throw"),
                ("ACKNOWLEDGE_RESULT", "acknowledge_result"),
                ("CONTINUE_TRANSITION", "continue_transition"),
                ("REPLAY", "replay"), ("CANCEL", "cancel"),
                ("PUBLISH_CURRENT", "publish_current"),
            ],
        )

    def test_commands_are_frozen_and_empty_commands_have_no_fields(self):
        empty_types = (
            StartCommand, AcknowledgeResultCommand, ContinueTransitionCommand,
            ReplayCommand, CancelCommand, PublishCurrentCommand,
        )
        for command_type in empty_types:
            value = command_type()
            self.assertTrue(is_dataclass(value))
            self.assertEqual(fields(value), ())
            with self.assertRaises(FrozenInstanceError):
                value.extra = 1

    def test_configure_accepts_exact_configs_and_schedules(self):
        for mode in Mode:
            value = config(mode)
            command = ConfigureCommand(value, schedule_for(value))
            self.assertIs(command.config, value)
        with self.assertRaises(InvalidApplicationControllerValueError):
            ConfigureCommand(object())
        with self.assertRaises(InvalidApplicationControllerValueError):
            ConfigureCommand(config(), object())

    def test_submit_requires_exact_integer_without_legality_checks(self):
        self.assertEqual(SubmitThrowCommand(-100).value, -100)
        for value in (True, 1.0, "1"):
            with self.assertRaises(InvalidApplicationControllerValueError):
                SubmitThrowCommand(value)


class ControllerFlowTests(unittest.TestCase):
    def test_construction_and_snapshot_do_not_publish_or_expose_services(self):
        value, main, second = controller()
        self.assertIs(value.snapshot().phase, SessionPhase.CONFIGURING)
        self.assertEqual((main.presented, second.presented), ((), ()))
        public = [name for name in dir(value) if not name.startswith("_")]
        self.assertEqual(public, ["execute", "snapshot"])

    def test_constructor_requires_exact_values(self):
        publisher = PresentationPublisher(
            FakeMainPresentationPort(DisplayCapabilities(True, None, None))
        )
        class CapabilitiesSubclass(ApplicationCapabilities):
            pass
        class PublisherSubclass(PresentationPublisher):
            pass
        for caps, pub in (
            (object(), publisher),
            (CapabilitiesSubclass(*capabilities().__dict__.values()), publisher),
            (capabilities(), object()),
            (capabilities(), PublisherSubclass(
                FakeMainPresentationPort(DisplayCapabilities(True, None, None))
            )),
        ):
            with self.assertRaises(InvalidApplicationControllerValueError):
                ApplicationController(caps, pub)

    def test_publish_current_is_repeatable_and_nonmutating(self):
        value, main, _ = controller()
        first = value.execute(PublishCurrentCommand())
        second = value.execute(PublishCurrentCommand())
        self.assertIs(first.command_kind, ApplicationCommandKind.PUBLISH_CURRENT)
        self.assertIs(first.snapshot.phase, SessionPhase.CONFIGURING)
        self.assertIs(first.presentation.scoreboard_placement, ScoreboardPlacement.NONE)
        self.assertEqual(len(main.presented), 2)
        self.assertIs(main.presented[0], first.presentation.main)
        self.assertIs(main.presented[1], second.presentation.main)

    def test_configure_start_submit_and_acknowledge_each_publish_once(self):
        value, main, _ = controller()
        ready = value.execute(ConfigureCommand(config(players=2)))
        started = value.execute(StartCommand())
        shown = value.execute(SubmitThrowCommand(4))
        acknowledged = value.execute(AcknowledgeResultCommand())
        self.assertEqual(
            [result.snapshot.phase for result in (ready, started, shown, acknowledged)],
            [SessionPhase.READY, SessionPhase.AWAITING_THROW,
             SessionPhase.SHOWING_RESULT, SessionPhase.AWAITING_THROW],
        )
        self.assertEqual(shown.snapshot.last_throw.scored_value, 4)
        self.assertIsNone(acknowledged.presentation.main.result)
        self.assertEqual(len(main.presented), 4)

    def test_player_transition_waits_for_explicit_continue(self):
        value, main, _ = controller()
        value.execute(ConfigureCommand(config(players=2)))
        value.execute(StartCommand())
        value.execute(SubmitThrowCommand(10))
        transitioned = value.execute(AcknowledgeResultCommand())
        self.assertIs(transitioned.snapshot.phase, SessionPhase.PLAYER_TRANSITION)
        self.assertIs(value.snapshot().phase, SessionPhase.PLAYER_TRANSITION)
        continued = value.execute(ContinueTransitionCommand())
        self.assertIs(continued.snapshot.phase, SessionPhase.AWAITING_THROW)
        self.assertEqual(len(main.presented), 5)

    def test_cancel_and_rejected_commands_do_not_add_publications(self):
        value, main, _ = controller()
        cancelled = value.execute(CancelCommand())
        self.assertIs(cancelled.snapshot.phase, SessionPhase.CANCELLED)
        with self.assertRaises(InvalidSessionTransitionError):
            value.execute(CancelCommand())
        with self.assertRaises(InvalidSessionTransitionError):
            value.execute(ReplayCommand())
        self.assertEqual(len(main.presented), 1)

    def test_all_modes_preserve_exact_schedule(self):
        for mode in Mode:
            with self.subTest(mode=mode):
                value, _, _ = controller()
                match_config = config(mode)
                schedule = schedule_for(match_config)
                ready = value.execute(ConfigureCommand(match_config, schedule))
                started = value.execute(StartCommand())
                self.assertIs(ready.snapshot.schedule, schedule)
                self.assertIs(started.snapshot.schedule, schedule)
                if mode is Mode.REMIX:
                    self.assertIsNotNone(started.snapshot.current_remix_object)
                if mode is Mode.PARTY:
                    self.assertIs(
                        started.snapshot.current_party_frame, schedule.frames[0]
                    )

    def test_secondary_capability_publishes_main_then_secondary(self):
        events = []
        cap = DisplayCapabilities(True, None, None)
        main = MutablePort(cap, events=events)
        second = MutablePort(cap, events=events)
        value = ApplicationController(
            capabilities(True), PresentationPublisher(main, second)
        )
        result = value.execute(ConfigureCommand(config()))
        value.execute(StartCommand())
        self.assertEqual(events, [main, main, second])
        self.assertIs(result.presentation.scoreboard_placement, ScoreboardPlacement.NONE)
        republished = value.execute(PublishCurrentCommand())
        self.assertIs(main.presented[-1], republished.presentation.main)

    def test_result_is_frozen_and_retains_exact_publication_objects(self):
        value, main, _ = controller()
        result = value.execute(PublishCurrentCommand())
        self.assertIsInstance(result, ApplicationCommandResult)
        self.assertIs(main.presented[0], result.presentation.main)
        with self.assertRaises(FrozenInstanceError):
            result.snapshot = value.snapshot()
        for values in (
            (object(), result.snapshot, result.presentation, result.receipt),
            (result.command_kind, object(), result.presentation, result.receipt),
            (result.command_kind, result.snapshot, object(), result.receipt),
            (result.command_kind, result.snapshot, result.presentation, object()),
        ):
            with self.assertRaises(InvalidApplicationControllerValueError):
                ApplicationCommandResult(*values)

    def test_invalid_objects_and_command_subclasses_are_rejected(self):
        class Derived(StartCommand):
            pass
        value, main, _ = controller()
        for command in (object(), Derived()):
            with self.assertRaises(InvalidApplicationCommandError):
                value.execute(command)
        self.assertEqual(main.presented, ())

    def test_session_and_domain_errors_propagate_without_publication(self):
        value, main, _ = controller()
        with self.assertRaises(InvalidSessionTransitionError):
            value.execute(StartCommand())
        remix = config(Mode.REMIX)
        with self.assertRaises(InvalidSessionConfigurationError):
            value.execute(ConfigureCommand(remix))
        self.assertEqual(main.presented, ())

        value.execute(ConfigureCommand(config()))
        value.execute(StartCommand())
        count = len(main.presented)
        with self.assertRaises(IllegalRollError):
            value.execute(SubmitThrowCommand(11))
        self.assertEqual(len(main.presented), count)

        cumulative, cumulative_main, _ = controller()
        cumulative.execute(ConfigureCommand(config(Mode.HUNDRED_PIN)))
        cumulative.execute(StartCommand())
        count = len(cumulative_main.presented)
        with self.assertRaises(IllegalCumulativeRollError):
            cumulative.execute(SubmitThrowCommand(101))
        self.assertEqual(len(cumulative_main.presented), count)


class PublicationFailureTests(unittest.TestCase):
    def test_preflight_failure_wraps_exact_advanced_state_and_chains(self):
        port = MutablePort(DisplayCapabilities(False, None, None))
        value = ApplicationController(capabilities(), PresentationPublisher(port))
        with self.assertRaises(ApplicationControllerPublishError) as caught:
            value.execute(ConfigureCommand(config()))
        error = caught.exception
        self.assertIs(error.command_kind, ApplicationCommandKind.CONFIGURE)
        self.assertIs(error.snapshot.phase, SessionPhase.READY)
        self.assertIs(value.snapshot().phase, SessionPhase.READY)
        self.assertIs(error.__cause__, error.cause)
        self.assertFalse(error.main_published)
        self.assertFalse(error.secondary_published)
        self.assertEqual(port.presented, [])

    def test_main_operation_failure_does_not_retry_or_roll_back(self):
        port = MutablePort(DisplayCapabilities(True, None, None), RuntimeError("main"))
        value = ApplicationController(capabilities(), PresentationPublisher(port))
        with self.assertRaises(ApplicationControllerPublishError) as caught:
            value.execute(ConfigureCommand(config()))
        self.assertIsInstance(caught.exception.cause, PresentationPublishError)
        self.assertFalse(caught.exception.main_published)
        self.assertIs(value.snapshot().phase, SessionPhase.READY)

    def test_secondary_failure_records_main_progress_without_fallback(self):
        events = []
        cap = DisplayCapabilities(True, None, None)
        main = MutablePort(cap, events=events)
        second = MutablePort(cap, RuntimeError("secondary"), events)
        value = ApplicationController(
            capabilities(True), PresentationPublisher(main, second)
        )
        value.execute(ConfigureCommand(config()))
        with self.assertRaises(ApplicationControllerPublishError) as caught:
            value.execute(StartCommand())
        self.assertTrue(caught.exception.main_published)
        self.assertFalse(caught.exception.secondary_published)
        self.assertEqual(events, [main, main, second])
        self.assertIs(value.snapshot().phase, SessionPhase.AWAITING_THROW)

    def test_publish_current_recovers_without_repeating_mutation(self):
        port = MutablePort(DisplayCapabilities(False, None, None))
        value = ApplicationController(capabilities(), PresentationPublisher(port))
        with self.assertRaises(ApplicationControllerPublishError):
            value.execute(ConfigureCommand(config()))
        port.capability = DisplayCapabilities(True, None, None)
        recovered = value.execute(PublishCurrentCommand())
        self.assertIs(recovered.command_kind, ApplicationCommandKind.PUBLISH_CURRENT)
        self.assertIs(recovered.snapshot.phase, SessionPhase.READY)
        self.assertEqual(len(port.presented), 1)


if __name__ == "__main__":
    unittest.main()
