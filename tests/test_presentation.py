import unittest
from dataclasses import FrozenInstanceError, fields, replace

from throw_a_strike.application import (
    ApplicationCapabilities,
    DisplayCapabilities,
    FrameScoreViewModel,
    GameSession,
    InvalidPresentationValueError,
    PortCapabilities,
    PresentationPrompt,
    PlayerScoreViewModel,
    ScoreboardViewModel,
    SecondaryScoreboardViewModel,
    SessionPhase,
    SessionSnapshot,
    StandingViewModel,
    ThrowResultViewModel,
    WinnerViewModel,
    ScoreboardPlacement,
    StorageCapabilities,
    build_presentation,
)
from throw_a_strike.domain.config import LOCKED_BRANDING, MatchConfig, Mode, Theme
from throw_a_strike.domain.match import PlayerColor
from throw_a_strike.domain.schedule import (
    PartySetupDefinition,
    build_party_schedule,
    build_remix_schedule,
)


def capabilities(secondary=False, dimensions=False):
    display = DisplayCapabilities(secondary, 320 if dimensions else None, 200 if dimensions else None)
    return ApplicationCapabilities(
        DisplayCapabilities(True, None, None), display,
        PortCapabilities(True), PortCapabilities(True), PortCapabilities(False),
        StorageCapabilities(False, False),
    )


def party_schedule(config):
    return build_party_schedule(config, (
        PartySetupDefinition("classic", "triangle", ("pin",), (), ("bonus",), 100),
    ))


def configured_session(mode, theme=Theme.REGULAR, players=1, frames=3):
    count = 10 if mode is Mode.TEN_PIN else frames
    config = MatchConfig(mode, theme, players, count, 42)
    schedule = build_remix_schedule(config) if mode is Mode.REMIX else party_schedule(config) if mode is Mode.PARTY else None
    session = GameSession()
    session.configure(config, schedule)
    return session, schedule


class PresentationTests(unittest.TestCase):
    def test_all_mode_and_theme_labels(self):
        expected = {Mode.TEN_PIN: "10-Pin", Mode.HUNDRED_PIN: "100-Pin", Mode.REMIX: "Remix", Mode.PARTY: "Party"}
        for mode, label in expected.items():
            with self.subTest(mode=mode):
                session, _ = configured_session(mode)
                self.assertEqual(build_presentation(session.snapshot(), capabilities()).main.mode_label, label)
        for theme, label in ((Theme.REGULAR, "Regular"), (Theme.BLACKLIGHT, "Blacklight")):
            session, _ = configured_session(Mode.TEN_PIN, theme)
            self.assertEqual(build_presentation(session.snapshot(), capabilities()).main.theme_label, label)

    def test_all_phase_prompt_mappings(self):
        snapshots = []
        snapshots.append(GameSession().snapshot())
        ready, _ = configured_session(Mode.TEN_PIN, players=2)
        snapshots.append(ready.snapshot())
        snapshots.append(ready.start())
        snapshots.append(ready.submit_throw(10))
        snapshots.append(ready.acknowledge_result())
        frame, _ = configured_session(Mode.TEN_PIN)
        frame.start(); frame.submit_throw(10); snapshots.append(frame.acknowledge_result())
        cancelled, _ = configured_session(Mode.TEN_PIN)
        cancelled.start(); cancelled.submit_throw(3); snapshots.append(cancelled.cancel())
        over, _ = configured_session(Mode.HUNDRED_PIN, frames=3)
        over.start()
        for _ in range(6):
            over.submit_throw(0)
            state = over.acknowledge_result()
            if state.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
                over.continue_transition()
        snapshots.append(over.snapshot())
        expected = {
            SessionPhase.CONFIGURING: PresentationPrompt.CONFIGURE_MATCH,
            SessionPhase.READY: PresentationPrompt.READY_TO_START,
            SessionPhase.AWAITING_THROW: PresentationPrompt.AWAIT_THROW,
            SessionPhase.SHOWING_RESULT: PresentationPrompt.SHOW_RESULT,
            SessionPhase.PLAYER_TRANSITION: PresentationPrompt.PLAYER_TRANSITION,
            SessionPhase.FRAME_TRANSITION: PresentationPrompt.FRAME_TRANSITION,
            SessionPhase.GAME_OVER: PresentationPrompt.GAME_OVER,
            SessionPhase.CANCELLED: PresentationPrompt.CANCELLED,
        }
        self.assertEqual({state.phase for state in snapshots}, set(SessionPhase))
        for state in snapshots:
            self.assertIs(build_presentation(state, capabilities()).main.prompt, expected[state.phase])

    def test_result_visibility_transitions_game_over_and_cancel(self):
        session, _ = configured_session(Mode.TEN_PIN, players=2)
        session.start(); shown = session.submit_throw(10)
        self.assertEqual(build_presentation(shown, capabilities()).main.result.scored_value, 10)
        transition = build_presentation(session.acknowledge_result(), capabilities()).main.scoreboard
        self.assertEqual(transition.focus_player_number, 2)
        session.continue_transition()
        self.assertIsNone(build_presentation(session.snapshot(), capabilities()).main.result)
        cancelled = session.cancel()
        cancelled_view = build_presentation(cancelled, capabilities())
        self.assertIsNotNone(cancelled_view.main.result)
        self.assertEqual((cancelled_view.main.scoreboard.focus_frame_number, cancelled_view.main.scoreboard.focus_player_number), (None, None))

    def test_remix_and_party_metadata_is_retained_not_regenerated(self):
        for mode in (Mode.REMIX, Mode.PARTY):
            session, schedule = configured_session(mode)
            active = session.start()
            active_view = build_presentation(active, capabilities()).main
            shown = build_presentation(session.submit_throw(0), capabilities()).main
            if mode is Mode.REMIX:
                self.assertIs(active_view.current_remix_object, schedule.frames[0].objects[0])
                self.assertIs(shown.result.remix_object, active.current_remix_object)
            else:
                self.assertIs(active_view.current_party_frame, schedule.frames[0])
                self.assertIs(shown.result.party_frame, active.current_party_frame)

    def test_cumulative_running_totals_across_frames(self):
        session, _ = configured_session(Mode.HUNDRED_PIN, frames=3)
        session.start()
        for value in (25, 25):
            session.submit_throw(value); session.acknowledge_result()
        session.continue_transition()
        session.submit_throw(0)
        frames = build_presentation(session.snapshot(), capabilities()).main.scoreboard.players[0].frames
        self.assertEqual((frames[0].cumulative_score, frames[1].cumulative_score, frames[2].cumulative_score), (50, 50, None))

    def test_regulation_marks_scores_and_frame_transition_focus(self):
        session, _ = configured_session(Mode.TEN_PIN)
        session.start()
        for value in (10, 5, 5, 9, 0):
            session.submit_throw(value)
            state = session.acknowledge_result()
            if state.phase is SessionPhase.FRAME_TRANSITION:
                transition = build_presentation(state, capabilities()).main.scoreboard
                self.assertEqual(transition.focus_player_number, 1)
                self.assertIs(transition.focus_player_color, PlayerColor.BLUE)
                session.continue_transition()
        frames = build_presentation(session.snapshot(), capabilities()).main.scoreboard.players[0].frames
        self.assertEqual(len(frames), 10)
        self.assertEqual((frames[0].roll_labels, frames[1].roll_labels, frames[2].roll_labels), (("X",), ("5", "/"), ("9", "-")))
        self.assertEqual((frames[0].score, frames[1].score, frames[2].score), (20, 19, 9))
        self.assertEqual((frames[0].cumulative_score, frames[1].cumulative_score, frames[2].cumulative_score), (20, 39, 48))
        self.assertIsNone(frames[3].score)

    def test_game_over_focus_is_empty_and_cumulative_tied_winners_are_preserved(self):
        session, _ = configured_session(Mode.HUNDRED_PIN, players=2, frames=3)
        session.start()
        for _ in range(12):
            session.submit_throw(0)
            state = session.acknowledge_result()
            if state.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
                session.continue_transition()
        board = build_presentation(session.snapshot(), capabilities()).main.scoreboard
        self.assertEqual((board.focus_frame_number, board.focus_player_number, board.focus_player_color, board.focus_throw_number), (None, None, None, None))
        self.assertEqual(tuple(winner.player_number for winner in board.winners), (1, 2))

    def test_final_tied_regulation_winners_are_preserved(self):
        session, _ = configured_session(Mode.TEN_PIN, players=2)
        session.start()
        for _ in range(40):
            session.submit_throw(0)
            state = session.acknowledge_result()
            if state.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
                session.continue_transition()
        board = build_presentation(session.snapshot(), capabilities()).main.scoreboard
        self.assertEqual(tuple((winner.player_number, winner.total_score) for winner in board.winners), ((1, 0), (2, 0)))

    def test_provisional_standing_order_and_competition_ranks_are_preserved(self):
        session, _ = configured_session(Mode.HUNDRED_PIN, players=3, frames=3)
        session.start()
        board = build_presentation(session.snapshot(), capabilities()).main.scoreboard
        self.assertEqual(tuple((row.rank, row.player_number) for row in board.standings), ((1, 1), (1, 2), (1, 3)))
        self.assertTrue(all(row.provisional for row in board.standings))

    def test_every_public_model_is_frozen(self):
        session, _ = configured_session(Mode.TEN_PIN)
        bundle = build_presentation(session.start(), capabilities())
        models = [bundle, bundle.main, bundle.main.scoreboard, *bundle.main.scoreboard.players,
                  *bundle.main.scoreboard.players[0].frames, *bundle.main.scoreboard.standings]
        for model in models:
            with self.subTest(model=type(model).__name__), self.assertRaises(FrozenInstanceError):
                setattr(model, fields(model)[0].name, None)

    def test_collection_fields_reject_mutable_values(self):
        frame = FrameScoreViewModel(1, (), (), None, None, None, False)
        for mutable in ([], {}, set()):
            with self.subTest(field="roll_values", mutable=type(mutable)), self.assertRaises(InvalidPresentationValueError):
                FrameScoreViewModel(1, mutable, (), None, None, None, False)
            with self.subTest(field="frames", mutable=type(mutable)), self.assertRaises(InvalidPresentationValueError):
                PlayerScoreViewModel(1, PlayerColor.BLUE, mutable, 0, False)
        session, _ = configured_session(Mode.TEN_PIN)
        board = build_presentation(session.start(), capabilities()).main.scoreboard
        for name in ("players", "standings", "winners"):
            for mutable in ([], {}, set()):
                with self.subTest(field=name, mutable=type(mutable)), self.assertRaises(InvalidPresentationValueError):
                    replace(board, **{name: mutable})

    def test_scalar_and_cross_field_validation(self):
        frame = FrameScoreViewModel(1, (), (), None, None, None, False)
        for value in (True, 0, "1"):
            with self.subTest(value=value), self.assertRaises(InvalidPresentationValueError):
                PlayerScoreViewModel(value, PlayerColor.BLUE, (frame,), 0, False)
        with self.assertRaises(InvalidPresentationValueError):
            StandingViewModel(1, 1, PlayerColor.BLUE, 0, 1)
        with self.assertRaises(InvalidPresentationValueError):
            WinnerViewModel(1, "Blue", 0)

    def test_retained_bundle_does_not_change(self):
        session, _ = configured_session(Mode.TEN_PIN)
        retained = build_presentation(session.start(), capabilities())
        session.submit_throw(10); session.acknowledge_result(); session.continue_transition()
        self.assertEqual(retained.main.scoreboard.players[0].total_score, 0)
        self.assertEqual(retained.main.scoreboard.players[0].frames[0].roll_values, ())

    def test_malformed_session_snapshots_are_rejected(self):
        session, _ = configured_session(Mode.TEN_PIN)
        active = session.start()
        malformed = (
            replace(active, phase="awaiting_throw"),
            replace(active, config=object()),
            replace(active, config=None),
            replace(active, current_player_number=None),
            replace(active, current_remix_object=object()),
            replace(active, phase=SessionPhase.READY),
        )
        for snapshot in malformed:
            with self.subTest(snapshot=snapshot), self.assertRaises(InvalidPresentationValueError):
                build_presentation(snapshot, capabilities())
    def test_enum_values_are_locked(self):
        self.assertEqual(tuple(item.value for item in PresentationPrompt), (
            "configure_match", "ready_to_start", "await_throw", "show_result",
            "player_transition", "frame_transition", "game_over", "cancelled",
        ))
        self.assertEqual(tuple(item.value for item in ScoreboardPlacement), ("none", "main", "secondary"))

    def test_configuring_and_ready(self):
        session = GameSession()
        initial = build_presentation(session.snapshot(), capabilities())
        self.assertIs(initial.main.branding, None)
        self.assertIs(initial.main.prompt, PresentationPrompt.CONFIGURE_MATCH)
        self.assertIs(initial.scoreboard_placement, ScoreboardPlacement.NONE)
        ready = session.configure(MatchConfig(Mode.TEN_PIN, Theme.BLACKLIGHT, 1, 10, 1))
        view = build_presentation(ready, capabilities())
        self.assertEqual(view.main.branding, LOCKED_BRANDING)
        self.assertEqual((view.main.mode_label, view.main.theme_label), ("10-Pin", "Blacklight"))
        self.assertIs(view.main.prompt, PresentationPrompt.READY_TO_START)
        self.assertFalse(view.main.input_enabled)

    def test_active_regulation_scoreboard_and_result(self):
        session = GameSession()
        session.configure(MatchConfig(Mode.TEN_PIN, Theme.REGULAR, 2, 10, 1))
        active = build_presentation(session.start(), capabilities())
        self.assertTrue(active.main.input_enabled)
        self.assertEqual(active.main.current_player_number, 1)
        board = active.main.scoreboard
        self.assertEqual(len(board.players), 2)
        self.assertEqual(len(board.players[0].frames), 10)
        self.assertIsNone(board.players[0].frames[0].score)
        shown = build_presentation(session.submit_throw(10), capabilities())
        self.assertEqual(shown.main.result.scored_value, 10)
        self.assertEqual(shown.main.result.available_before, 10)
        self.assertEqual(shown.main.result.available_after, 0)
        self.assertIsNone(shown.main.current_player_number)
        transition = build_presentation(session.acknowledge_result(), capabilities())
        self.assertEqual(transition.main.scoreboard.focus_player_number, 2)

    def test_cumulative_zero_roll_and_future_frames(self):
        session = GameSession()
        session.configure(MatchConfig(Mode.HUNDRED_PIN, Theme.REGULAR, 1, 3, 1))
        session.start()
        session.submit_throw(0)
        board = build_presentation(session.snapshot(), capabilities()).main.scoreboard
        frames = board.players[0].frames
        self.assertEqual(frames[0].roll_values, (0,))
        self.assertEqual(frames[0].roll_labels, ("0",))
        self.assertEqual(frames[0].cumulative_score, 0)
        self.assertIsNone(frames[1].cumulative_score)
        self.assertEqual(frames[0].maximum_score, 100)

    def test_secondary_and_fallback_are_exclusive_and_ignore_dimensions(self):
        session = GameSession()
        session.configure(MatchConfig(Mode.TEN_PIN, Theme.REGULAR, 1, 10, 1))
        snapshot = session.start()
        fallback = build_presentation(snapshot, capabilities())
        secondary = build_presentation(snapshot, capabilities(True))
        sized = build_presentation(snapshot, capabilities(True, True))
        self.assertIs(fallback.scoreboard_placement, ScoreboardPlacement.MAIN)
        self.assertIsNotNone(fallback.main.scoreboard)
        self.assertIsNone(fallback.secondary)
        self.assertIs(secondary.scoreboard_placement, ScoreboardPlacement.SECONDARY)
        self.assertIsNone(secondary.main.scoreboard)
        self.assertEqual(secondary.secondary.scoreboard, sized.secondary.scoreboard)

    def test_models_are_frozen_and_collections_are_tuples(self):
        frame = FrameScoreViewModel(1, (), (), None, None, None, False)
        with self.assertRaises(FrozenInstanceError):
            frame.score = 1
        self.assertIsInstance(frame.roll_values, tuple)

    def test_exact_input_types_and_frame_validation(self):
        with self.assertRaises(InvalidPresentationValueError):
            build_presentation(object(), capabilities())
        with self.assertRaises(InvalidPresentationValueError):
            build_presentation(GameSession().snapshot(), object())
        with self.assertRaises(InvalidPresentationValueError):
            FrameScoreViewModel(True, (), (), None, None, None, False)
        with self.assertRaises(InvalidPresentationValueError):
            FrameScoreViewModel(1, (1,), (), None, None, None, False)


if __name__ == "__main__":
    unittest.main()
