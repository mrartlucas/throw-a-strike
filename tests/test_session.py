import unittest
from dataclasses import FrozenInstanceError

from throw_a_strike.application import (
    GameSession,
    InvalidSessionConfigurationError,
    InvalidSessionTransitionError,
    SessionPhase,
)
from throw_a_strike.domain.bowling import IllegalRollError
from throw_a_strike.domain.config import MatchConfig, Mode, Theme
from throw_a_strike.domain.cumulative import IllegalCumulativeRollError
from throw_a_strike.domain.cumulative_match import CumulativeMatchSnapshot
from throw_a_strike.domain.match import MatchSnapshot, PlayerColor
from throw_a_strike.domain.schedule import (
    PartySetupDefinition,
    build_party_schedule,
    build_remix_schedule,
)


def make_config(mode=Mode.TEN_PIN, players=2, frames=None, seed=42):
    return MatchConfig(
        mode, Theme.REGULAR, players,
        10 if frames is None and mode is Mode.TEN_PIN else (frames or 3), seed,
    )


def party_schedule(config):
    catalog = (
        PartySetupDefinition("classic", "triangle", ("pin",), (), ("bonus",), 100),
        PartySetupDefinition("orbit", "ring", ("orb",), ("pulse",), (), 75),
    )
    return build_party_schedule(config, catalog)


class ConfigurationAndStartTests(unittest.TestCase):
    def test_initial_snapshot_is_empty_and_configuring(self):
        state = GameSession().snapshot()
        self.assertEqual(state.phase, SessionPhase.CONFIGURING)
        self.assertIsNone(state.config)
        self.assertIsNone(state.schedule)
        self.assertIsNone(state.match)
        self.assertIsNone(state.last_throw)
        self.assertIsNone(state.current_player_number)

    def test_each_valid_configuration_enters_ready(self):
        for mode in Mode:
            config = make_config(mode)
            schedule = (build_remix_schedule(config) if mode is Mode.REMIX else
                        party_schedule(config) if mode is Mode.PARTY else None)
            with self.subTest(mode=mode):
                state = GameSession().configure(config, schedule)
                self.assertEqual(state.phase, SessionPhase.READY)
                self.assertEqual(state.config, config)

    def test_schedule_contract_rejects_missing_extra_wrong_and_mismatched(self):
        remix = make_config(Mode.REMIX)
        party = make_config(Mode.PARTY)
        cases = (
            (make_config(), build_remix_schedule(remix)),
            (make_config(Mode.HUNDRED_PIN), build_remix_schedule(remix)),
            (remix, None),
            (party, None),
            (remix, party_schedule(party)),
            (party, build_remix_schedule(remix)),
            (make_config(Mode.REMIX, seed=99), build_remix_schedule(remix)),
            (remix, object()),
            (object(), None),
        )
        for config, schedule in cases:
            session = GameSession()
            before = session.snapshot()
            with self.subTest(config=config, schedule=schedule), self.assertRaises(
                InvalidSessionConfigurationError
            ):
                session.configure(config, schedule)  # type: ignore[arg-type]
            self.assertEqual(session.snapshot(), before)

    def test_reconfigure_ready_and_reject_after_start_atomically(self):
        session = GameSession()
        session.configure(make_config(players=1))
        config = make_config(players=2)
        self.assertEqual(session.configure(config).config, config)
        session.start()
        before = session.snapshot()
        with self.assertRaises(InvalidSessionTransitionError):
            session.configure(make_config(players=3))
        self.assertEqual(session.snapshot(), before)

    def test_start_requires_ready_and_exposes_first_throw(self):
        session = GameSession()
        with self.assertRaises(InvalidSessionTransitionError):
            session.start()
        state = session.configure(make_config(players=1))
        self.assertIsNone(state.match)
        state = session.start()
        self.assertEqual(state.phase, SessionPhase.AWAITING_THROW)
        self.assertIsInstance(state.match, MatchSnapshot)
        self.assertEqual(
            (state.current_frame_number, state.current_player_number,
             state.current_player_color, state.current_throw_number, state.current_available),
            (1, 1, PlayerColor.BLUE, 1, 10),
        )
        self.assertFalse(hasattr(session, "match"))
        self.assertFalse(hasattr(session, "games"))

    def test_cumulative_match_maximums_follow_mode(self):
        for mode in (Mode.HUNDRED_PIN, Mode.REMIX, Mode.PARTY):
            config = make_config(mode)
            schedule = (build_remix_schedule(config) if mode is Mode.REMIX else
                        party_schedule(config) if mode is Mode.PARTY else None)
            session = GameSession(); session.configure(config, schedule); state = session.start()
            self.assertIsInstance(state.match, CumulativeMatchSnapshot)
            expected = (100,) * 3 if schedule is None else schedule.frame_max_scores
            self.assertEqual(state.match.frame_max_scores, expected)


class ThrowAndTransitionTests(unittest.TestCase):
    def started(self, mode=Mode.TEN_PIN, players=2):
        config = make_config(mode, players=players)
        schedule = build_remix_schedule(config) if mode is Mode.REMIX else None
        session = GameSession(); session.configure(config, schedule); session.start()
        return session

    def test_regulation_result_records_rack_and_blocks_current_window(self):
        session = self.started()
        state = session.submit_throw(4)
        self.assertEqual(state.phase, SessionPhase.SHOWING_RESULT)
        self.assertEqual(
            (state.last_throw.scored_value, state.last_throw.available_before,
             state.last_throw.available_after), (4, 10, 6)
        )
        self.assertTrue(all(value is None for value in (
            state.current_frame_number, state.current_player_number,
            state.current_throw_number, state.current_available,
            state.current_remix_object, state.current_party_frame)))
        with self.assertRaises(InvalidSessionTransitionError): session.submit_throw(1)
        state = session.acknowledge_result()
        self.assertEqual(state.phase, SessionPhase.AWAITING_THROW)
        self.assertEqual((state.current_throw_number, state.current_available), (2, 6))

    def test_cumulative_result_records_capacity(self):
        state = self.started(Mode.HUNDRED_PIN).submit_throw(30)
        self.assertEqual((state.last_throw.available_before, state.last_throw.available_after),
                         (100, 70))
        self.assertEqual(state.last_throw.scored_value, 30)

    def test_domain_roll_errors_propagate_without_mutation(self):
        for mode, value, error in (
            (Mode.TEN_PIN, 11, IllegalRollError),
            (Mode.HUNDRED_PIN, 101, IllegalCumulativeRollError),
        ):
            session = self.started(mode)
            before = session.snapshot()
            with self.subTest(mode=mode), self.assertRaises(error): session.submit_throw(value)
            self.assertEqual(session.snapshot(), before)

    def test_player_and_frame_transitions_gate_throws(self):
        session = self.started(players=2)
        session.submit_throw(10)
        state = session.acknowledge_result()
        self.assertEqual(state.phase, SessionPhase.PLAYER_TRANSITION)
        with self.assertRaises(InvalidSessionTransitionError): session.submit_throw(1)
        state = session.continue_transition()
        self.assertEqual(state.current_player_number, 2)
        session.submit_throw(10)
        state = session.acknowledge_result()
        self.assertEqual(state.phase, SessionPhase.FRAME_TRANSITION)
        state = session.continue_transition()
        self.assertEqual((state.current_frame_number, state.current_player_number), (2, 1))

    def test_invalid_acknowledgments_are_atomic(self):
        session = self.started()
        before = session.snapshot()
        for method in (session.acknowledge_result, session.continue_transition, session.replay):
            with self.assertRaises(InvalidSessionTransitionError): method()
            self.assertEqual(session.snapshot(), before)


class ScheduleFairnessTests(unittest.TestCase):
    def test_remix_uses_global_frame_and_throw_for_every_player(self):
        config = make_config(Mode.REMIX, players=2)
        schedule = build_remix_schedule(config)
        session = GameSession(); session.configure(config, schedule); state = session.start()
        self.assertIs(state.current_remix_object, schedule.frames[0].objects[0])
        seen = []
        for _ in range(2):
            for throw in range(2):
                seen.append(session.snapshot().current_remix_object)
                result = session.submit_throw(0)
                self.assertIs(result.last_throw.remix_object, seen[-1])
                state = session.acknowledge_result()
                if state.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
                    session.continue_transition()
        self.assertEqual(seen, [*schedule.frames[0].objects, *schedule.frames[0].objects])
        self.assertIs(session.snapshot().current_remix_object, schedule.frames[1].objects[0])

    def test_party_frame_is_shared_across_throws_players_and_frames(self):
        config = make_config(Mode.PARTY, players=2)
        schedule = party_schedule(config)
        session = GameSession(); session.configure(config, schedule); session.start()
        for _ in range(4):
            self.assertIs(session.snapshot().current_party_frame, schedule.frames[0])
            result = session.submit_throw(0)
            self.assertIs(result.last_throw.party_frame, schedule.frames[0])
            state = session.acknowledge_result()
            if state.phase in (SessionPhase.PLAYER_TRANSITION, SessionPhase.FRAME_TRANSITION):
                session.continue_transition()
        self.assertIs(session.snapshot().current_party_frame, schedule.frames[1])


class CompletionReplayCancellationTests(unittest.TestCase):
    def complete_cumulative(self, mode=Mode.HUNDRED_PIN):
        config = make_config(mode, players=1)
        schedule = (build_remix_schedule(config) if mode is Mode.REMIX else
                    party_schedule(config) if mode is Mode.PARTY else None)
        session = GameSession(); session.configure(config, schedule); session.start()
        for index in range(6):
            state = session.submit_throw(0)
            self.assertEqual(state.phase, SessionPhase.SHOWING_RESULT)
            state = session.acknowledge_result()
            if index < 5 and state.phase is SessionPhase.FRAME_TRANSITION:
                session.continue_transition()
        return session, config, schedule

    def test_game_over_final_state_and_replay(self):
        session, config, schedule = self.complete_cumulative(Mode.REMIX)
        final = session.snapshot()
        self.assertEqual(final.phase, SessionPhase.GAME_OVER)
        self.assertTrue(final.match.complete)
        self.assertTrue(final.match.winners)
        self.assertIsNone(final.current_player_number)
        with self.assertRaises(InvalidSessionTransitionError): session.submit_throw(0)
        replay = session.replay()
        self.assertEqual(replay.phase, SessionPhase.AWAITING_THROW)
        self.assertEqual(replay.config, config)
        self.assertIs(replay.schedule, schedule)
        self.assertIsNone(replay.last_throw)
        self.assertEqual(replay.match.players[0].total_score, 0)
        self.assertIs(replay.current_remix_object, schedule.frames[0].objects[0])

    def test_party_replay_reuses_first_frame(self):
        session, _, schedule = self.complete_cumulative(Mode.PARTY)
        self.assertIs(session.replay().current_party_frame, schedule.frames[0])

    def test_cancel_retains_state_and_blocks_every_mutation(self):
        session = GameSession(); session.configure(make_config(players=1)); session.start()
        shown = session.submit_throw(1)
        cancelled = session.cancel()
        self.assertEqual(cancelled.phase, SessionPhase.CANCELLED)
        self.assertEqual(cancelled.match, shown.match)
        self.assertEqual(cancelled.last_throw, shown.last_throw)
        self.assertIsNone(cancelled.current_player_number)
        operations = (
            lambda: session.configure(make_config()), session.start,
            lambda: session.submit_throw(0), session.acknowledge_result,
            session.continue_transition, session.replay, session.cancel,
        )
        for operation in operations:
            before = session.snapshot()
            with self.assertRaises(InvalidSessionTransitionError): operation()
            self.assertEqual(session.snapshot(), before)

    def test_cancel_from_empty_and_ready(self):
        self.assertEqual(GameSession().cancel().phase, SessionPhase.CANCELLED)
        session = GameSession(); session.configure(make_config())
        self.assertEqual(session.cancel().phase, SessionPhase.CANCELLED)

    def test_snapshots_are_frozen_retained_and_tuple_based(self):
        session = GameSession(); ready = session.configure(make_config(players=1)); session.start()
        with self.assertRaises(FrozenInstanceError): ready.phase = SessionPhase.CANCELLED
        thrown = session.submit_throw(0)
        with self.assertRaises(FrozenInstanceError): thrown.last_throw.scored_value = 1
        session.acknowledge_result()
        self.assertEqual(ready.phase, SessionPhase.READY)
        self.assertIsInstance(thrown.match.players, tuple)
        self.assertIsInstance(thrown.match.standings, tuple)


if __name__ == "__main__":
    unittest.main()
