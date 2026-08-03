import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.application import (
    ApplicationCapabilities,
    DisplayCapabilities,
    FrameScoreViewModel,
    GameSession,
    InvalidPresentationValueError,
    PortCapabilities,
    PresentationPrompt,
    ScoreboardPlacement,
    StorageCapabilities,
    build_presentation,
)
from throw_a_strike.domain.config import LOCKED_BRANDING, MatchConfig, Mode, Theme


def capabilities(secondary=False, dimensions=False):
    display = DisplayCapabilities(secondary, 320 if dimensions else None, 200 if dimensions else None)
    return ApplicationCapabilities(
        DisplayCapabilities(True, None, None), display,
        PortCapabilities(True), PortCapabilities(True), PortCapabilities(False),
        StorageCapabilities(False, False),
    )


class PresentationTests(unittest.TestCase):
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
