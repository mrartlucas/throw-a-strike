# Throw a Strike — Implementation Plan

## Locked product requirements

### Brand

- Presenter/umbrella brand: **Throw A Way Games**. Never combine the umbrella brand into one word.
- Game title: **Throw a Strike**.
- Title treatment: “Throw A Way Games presents” followed by “Throw a Strike.”

### Multiplayer and presentation

- Support 1–4 players: Player 1 Blue, Player 2 Red, Player 3 Green, Player 4 Yellow.
- Follow the verified multiplayer flow used by other Dartsnut games; do not invent that flow while the reference is unavailable.
- Main screen prioritizes gameplay. The secondary screen shows current player color, frame, throw, scores, totals, standings, and winner.
- Use a regular bowling theme and a blacklight bowling theme, a slightly overhead view, large readable pins, the full formation, minimal lane space, and fast/simple play. Each mode must be understandable during its first turn.

### Modes

1. **10-Pin:** regulation ten-pin bowling; ten frames; correct strikes, spares, opens, and tenth-frame bonuses; highest final score wins.
2. **100-Pin:** 100 pins arranged for domino-like chain reactions; two throws per player per frame; throw two uses the pins remaining from throw one; one point per fallen pin; formation resets for each player; selectable 3, 5, or 10 frames; no strike/spare bonuses; highest cumulative score wins.
3. **Remix:** uses a standard 10-pin rack and exactly two throws per player per frame. Throw two continues against the pins remaining after throw one; the rack then resets for the next player. Each fallen pin scores one point, with no strike or spare bonuses. The thrown object may change on each throw (including tennis ball, baseball, basketball, beach ball, football, soccer ball, golf ball, medicine ball, and rubber ball), with distinct size, speed, weight, bounce, and impact behavior. Every player receives the exact same per-throw object sequence during a frame. Selectable 3, 5, or 10 frames; highest cumulative score wins.
4. **Party:** uses special pins, targets, formations, and reactions (including firework, explosive, balloon, heavy, and mystery pins plus domino walls, stars, circles, spirals, arrows, and zigzags) with exactly two throws per player per frame. Throw two continues against whatever targets remain after throw one; the setup then resets for the next player. Each pin or target scores its defined point value. The full setup and available maximum score—including formation, pin types, reactions, mystery outcomes, and deterministic seed—are identical for every player during a frame. Selectable 3, 5, or 10 frames; highest cumulative score wins.

## Planning principles

1. Build pure, deterministic domain code before cabinet adapters.
2. Keep Dartsnut capabilities behind interfaces whose production implementations use only verified APIs. An interface is a test seam, not a claim that hardware supports it.
3. Represent turns, racks, rolls, bonuses, and display snapshots explicitly; never derive a roll retrospectively from totals.
4. Seed and record a match schedule so all players receive the same Remix object or Party setup for a frame. Competitive collision outcomes should be input/physics-driven; randomness must be seeded, controlled, and fairness-tested.
5. Use fixed timestep simulation with interpolation/render decoupling, swept collision where needed, and measurable performance budgets.
6. Keep gameplay usable on the verified main display while secondary-display work remains gated. Do not ship a fake secondary API.
7. End each phase with a runnable, reversible baseline and automated tests. Commit/feature-flag mode additions separately.

## Phase 0: Shared foundation, menus, multiplayer, display abstraction, and scoring architecture

### Goal

Create a testable application shell supporting mode/theme/player/frame selection, 1–4 player turn rotation, immutable score snapshots, shared deterministic schedules, input gating, and display interfaces without changing gameplay semantics prematurely.

### Files expected to change

- Refactor `main.py` to a thin bootstrap.
- Update `conf.json`, `pyproject.toml`, and `uv.lock` only after hardware/packaging review.
- Add modules such as `throw_a_strike/app.py`, `domain/match.py`, `domain/players.py`, `domain/scoring.py`, `input.py`, `display.py`, `rng.py`, and `config.py`.
- Add `tests/` with unit, contract, and state-transition tests.
- Add `.dartsnut` content only if official documentation requires it; never invent it.

### Technical approach

- Define domain types for `Player`, `Mode`, `Theme`, `MatchConfig`, `FrameState`, `ThrowResult`, `Standing`, and a serializable read-only `ScoreboardSnapshot`.
- Fix player order/colors as Blue, Red, Green, Yellow. Treat dart color identity separately from player selection until official mapping is verified.
- Implement round-robin frame flow consistent with an obtained reference Dartsnut multiplayer game. Each player completes the applicable frame throws before the next player; validate this against the reference rather than assuming.
- Define `InputPort`, `MainDisplayPort`, optional `SecondaryDisplayPort`, `AudioPort`, `Clock`, and `Store` protocols. Implement only the verified Dartsnut main input/display/store adapter. Use explicit “secondary unavailable” capability handling, not a placeholder hardware call.
- Separate pure score policies: regulation roll-stream scorer and cumulative-pin scorer. Return frame marks, pending bonuses, cumulative totals, completion, ranks/ties, and winner set.
- Introduce menu/state navigation and consume/arm input only in valid windows; drain/require dart removal between turns to prevent result-skips becoming throws.
- Pin the audited SDK version or explicitly review a newer release. Add dependency-lock and manifest validation checks.

### Acceptance tests

- Menu can configure all four modes, 1–4 players, allowed frame counts, and both themes; 10-Pin is fixed at ten frames.
- Player order and colors are exactly P1 Blue, P2 Red, P3 Green, P4 Yellow; ties retain all tied winners.
- State-transition tests cover back/confirm, match start, throw acceptance, result acknowledgment, player/frame advance, game over, replay, and cancellation.
- Pure 10-Pin scorer passes perfect game=300, all 9-miss=90, all 5-spare with final 5=150, all gutters=0, consecutive strikes, and tenth-frame strike/spare/open matrices.
- Cumulative scorer never applies bonuses and supports 3/5/10 frames.
- Same match seed produces identical per-frame schedules for every player and across replay/serialization.
- Branding snapshot contains only the locked spellings.

### Emulator tests

- Launch through the official emulator once obtained; verify manifest, 30+ minute state navigation, all buttons, injected dart events, removal/re-arm, SIGINT/home flow, and dropped-frame handling.
- Validate main-display pixel dimensions/orientation and capture golden screenshots at native resolution.
- If supported by the official emulator, verify secondary capability detection and synchronized snapshots; otherwise mark this test blocked, not passed.

### Hardware tests

- Confirm native main display dimensions, RGB order/orientation, safe frame length, brightness, frame pacing, and busy behavior.
- Trace every labeled Blue/Red/Green/Yellow dart to index across restarts; verify axis orientation with nine board zones and characterize jitter/latency.
- Inventory/label buttons and test press, hold, debounce, home, and reserved behavior.
- Compare menu/turn flow against at least one current official multiplayer game.

### Dependencies and unresolved questions

- Official multiplayer sample/flow; main and secondary display specs/API; dart-color mapping; control-screen/touch API; packaging schema; emulator; supported Python/Pygame versions.
- Decide desired turn order within a frame from official Dartsnut precedent.
- Decide tie presentation and whether names/initials are supported by platform input.

### Rollback point

Tag the untouched imported prototype as `prototype-audit-baseline`; land foundation behind a selectable legacy bootstrap until parity smoke tests pass. Revert the foundation commit(s) to restore the single-file game.

## Phase 1: Regulation 10-Pin mode

### Goal

Deliver deterministic, skill-led regulation ten-pin play for 1–4 players, including correct racks, second throws, tenth-frame fill balls, scoring, and winners.

### Files expected to change

- Add/update `modes/ten_pin.py`, `physics/`, `render/gameplay.py`, domain scoring/turn modules, and focused tests/fixtures.
- Add only approved/licensed visual assets if procedural rendering is insufficient.

### Technical approach

- Model rack-before and rack-after each throw explicitly. Encode tenth-frame reset rules as a state machine: strike resets before throw two; throw-two strike resets before throw three; a throw-two spare after a non-strike resets before throw three; otherwise throw three uses remaining pins.
- Convert the physical dart hit into a documented, calibrated two-axis launch intent. If velocity is unavailable, use a transparent fixed-speed mapping with position/angle derived from coordinates; do not fabricate pressure/speed data.
- Replace probability cascades with deterministic mass/impulse or authored deterministic reaction rules. Use a fixed simulation timestep, swept ball collision, pin-to-pin propagation, and reproducible result tests.
- Separate simulation from topple animation; record exactly which pins transition standing→down in each throw.
- Show an immediate first-turn overlay: throw at the board to aim the ball; two throws unless strike; remaining rack persists.

### Acceptance tests

- Exhaustive legal tenth-frame categories and property tests ensure 0≤roll≤standing pins and total 0–300.
- Frame marks/cumulative scores match independent trusted fixtures for opens, spares, strikes, turkeys, mixed games, and all fill-ball patterns.
- A strike ends frames 1–9; non-strike allows exactly one throw against remaining pins. Per-player racks never leak.
- Identical simulation input produces identical fallen pins; centered/edge/gutter fixtures are stable and tunable.
- 1–4 player matches rotate correctly and declare highest score/all tied winners.

### Emulator tests

- Play complete gutter, spare-heavy, strike-heavy, and mixed scripted games with injected coordinates.
- Validate input re-arming, no throw consumed during animation/result, readable full rack, stable 30 FPS target, and score snapshot synchronization.

### Hardware tests

- Play complete matches for each player count using labeled darts; test corners, center, repeated quick throws, removal delays, and accidental throws between turns.
- Compare scoring against a paper/independent bowling scorer, especially tenth-frame `X X X`, `X 7 /`, `X 7 2`, `7 / X`, and `0 / X`.
- Observe skill correlation/repeatability across calibrated target zones and cabinet viewing readability.

### Dependencies and unresolved questions

- Coordinate orientation/calibration and color ownership must be verified.
- Choose deterministic physics parameters from hardware playtesting; establish acceptable assist level without random scoring.
- Confirm whether wrong-color darts should be rejected, warned, or merely indicated under official multiplayer conventions.

### Rollback point

Keep Phase 0 menus/foundation and disable the `TEN_PIN` feature flag to return to the last validated shell.

## Phase 2: 100-Pin mode

### Goal

Add a readable, performant 100-pin domino formation with exactly two throws per player per selected frame and simple one-point-per-pin scoring.

### Files expected to change

- Add `modes/hundred_pin.py`, formation data/generator, spatial collision structures, optimized rendering/animation, mode UI, and tests/benchmarks.
- Add approved assets only if needed.

### Technical approach

- Store 100 stable pin IDs and standing/down state. Generate one validated formation at a scale where the complete formation remains readable.
- Preserve remaining pins for throw two, then reset all 100 for the next player. Reset for each frame/player without cross-player mutation.
- Score only unique standing→down transitions; cap each frame at 100; do not label or bonus strikes/spares.
- Use a spatial grid/broad phase and deterministic time-ordered domino propagation. Pool render objects/particles and cap effects.
- First-turn overlay: “Knock down 100 pins — 2 throws — 1 point each.”

### Acceptance tests

- Exactly 100 unique pins spawn and are visible; a pin scores at most once.
- Throw two starts with precisely throw-one survivors. Player switch resets to 100. Frame totals are 0–100 and matches end after 3/5/10 frames.
- No strike/spare bonus exists. Identical input/seed is deterministic. Multiplayer totals/winners are correct.
- Benchmarks stay within the hardware-derived CPU/memory/frame budget at worst-case chain reaction.

### Emulator tests

- Script zero, partial, and all-pin frames; verify reset timing, mode explanation, frame options, standings, and long 4-player/10-frame stability.
- Profile worst-case simultaneous reaction and framebuffer backpressure.

### Hardware tests

- Validate visibility at cabinet distance, input-to-chain latency, full-chain animation duration, accidental next-throw protection, and thermal/frame stability through a maximum-length match.

### Dependencies and unresolved questions

- Native display dimensions may constrain individual pin readability; formation/design must wait for confirmation.
- Define maximum acceptable chain animation duration and hardware performance budget from Phase 0 measurements.

### Rollback point

Disable/remove the independently registered `HUNDRED_PIN` mode; Phase 1 remains shippable.

## Phase 3: Remix mode with changing balls and objects

### Goal

Add fair per-frame thrown-object sequences with visibly and mechanically distinct objects, while keeping scoring cumulative and immediately understandable.

### Files expected to change

- Add `modes/remix.py`, `objects/catalog.py`, physics material/profile data, renderer/effects, schedule tests, and licensed/procedural object assets.

### Technical approach

- Data-drive tennis ball, baseball, basketball, beach ball, football, soccer ball, golf ball, medicine ball, and rubber ball profiles: radius, mass, launch-speed mapping, restitution/bounce, drag/rolling behavior, and pin impulse.
- Generate a two-object sequence once per frame and apply that exact throw-one/throw-two sequence to every player. The object may change between the two throws. Persist schedule IDs/seeds in match state.
- Start every player with a standard 10-pin rack, allow exactly two throws, preserve the standing pins between those throws, and reset the rack before the next player.
- Normalize input affordances so unusual shapes (football) remain controllable. Preview the current/next object and give a one-line property hint on the first occurrence.
- Award one point for each unique standing-to-fallen pin transition. Use cumulative scoring only, with no strike or spare bonuses.

### Acceptance tests

- All nine required example objects load with validated parameters and noticeably distinct deterministic fixture outcomes.
- Every player sees the identical object sequence for each frame/throw; different seeds may vary schedules without biasing players.
- Every player starts each frame with ten pins, receives exactly two throws, and faces only the pins remaining after throw one on throw two; the rack resets before the next player.
- Each pin scores at most once, frame scores remain within 0–10, and strike/spare bonuses are never applied.
- 3/5/10-frame matches total correctly and highest/all-tied winners are correct.
- UI identifies object and essential behavior before a throw; no object can create NaN, escape forever, or exceed simulation timeout.

### Emulator tests

- Force each object and test boundary hits, bounces, gutter/timeout, sequence replay, restart, 4-player equality, readability, and performance.

### Hardware tests

- Validate aiming feel, perceived distinctions, fairness across player colors, explanation comprehension on a first turn, audio/visual anticipation, and full catalog stability.

### Dependencies and unresolved questions

- Art/audio format and budget approval; physics balancing criteria and acceptable differences among object profiles.
- Main-display dimensions, audio routing, emulator support, asset packaging limits, and dart-index/color mapping remain hardware blockers.

### Rollback point

Disable the `REMIX` registry entry; retain shared catalog code only if unused-code checks permit it.

## Phase 4: Party mode with changing pins, formations, and reactions

### Goal

Add fair shared Party setups with special pins/targets, formations, and deterministic reactions that remain legible and safe.

### Files expected to change

- Add `modes/party.py`, `party/catalog.py`, formation/reaction components, effect budgets, content assets, safety/accessibility settings, and tests.

### Technical approach

- Define versioned setup recipes containing formation, target/pin types, reactions, each target's point value, available maximum score, deterministic seed, and explanation key.
- Implement firework, explosive, balloon, heavy, and mystery pin behaviors plus domino walls, stars, circles, spirals, arrows, and zigzags as composable components.
- Generate one complete setup per frame and reuse its formation, pin/target types, reactions, mystery outcomes, point values, maximum score, and deterministic seed unchanged for every player.
- Give each player exactly two throws. Preserve whatever targets remain for throw two, then reset the complete setup before the next player.
- Use a bounded event queue for chain reactions, maximum particle/audio concurrency, flash-reduction option, and deterministic scoring ledger.
- Add each unique removed/achieved pin or target's defined point value to a deterministic scoring ledger. Use cumulative scoring over the selected 3/5/10 frames; highest score wins. Explain each setup in one title plus one action sentence before the first player.

### Acceptance tests

- Every required pin type and formation has a deterministic fixture and bounded completion time.
- Setup/seed, point values, and available maximum score are identical for every player in a frame; scores count each target once and never change after result finalization.
- Every player receives exactly two throws, throw two retains precisely the targets left after throw one, and the complete setup resets before the next player.
- Event queue/effect caps hold under worst-case explosions. Mystery behavior is reproducible and fair.
- 3/5/10-frame lifecycle, totals, ties, winner, and first-turn explanations pass snapshots and domain tests.

### Emulator tests

- Force every recipe and reaction combination; run maximum chain, rapid input, restart, and four-player fairness tests; inspect flash/readability and profile resources.

### Hardware tests

- Validate legibility, cabinet-distance comprehension, effect brightness, audio peaks, reaction latency, performance/temperature, and repeated maximum-length matches.
- User-test first-turn understanding without verbal coaching.

### Dependencies and unresolved questions

- Confirm the content catalog and balance of defined target values without changing the locked equal-maximum-score rule.
- Main-display dimensions, secondary-screen API, dart-index/color mapping, audio routing, emulator support, hardware budgets, photosensitivity/flash requirements, and asset packaging constraints remain unresolved hardware or platform matters.

### Rollback point

Disable `PARTY` as one registry feature; keep Phases 0–3 unaffected.

## Phase 5: Regular and Blacklight presentation and secondary-screen scoreboard

### Goal

Finish coherent regular/blacklight themes and deliver the required secondary scoreboard using a verified platform API, leaving the main display focused on play.

### Files expected to change

- Theme tokens/assets, main gameplay renderer, scoreboard presenter/layout, verified Dartsnut secondary adapter/configuration, visual snapshots, and documentation.
- `conf.json`/`.dartsnut` only as required by official specifications.

### Technical approach

- Use theme tokens for palette, pin/lane/object treatment, contrast, and effects; domain mechanics remain theme-independent.
- Redesign slightly overhead composition around the full formation and large pins, minimizing approach/lane space. Use the confirmed native main resolution.
- Drive both displays from the same immutable snapshot/version. Secondary view shows current player color, mode, frame, throw, frame marks/scores, totals, standings, ties, and winner; main retains only essential current-turn/action feedback.
- Implement the secondary adapter only after obtaining the official API/sample. If the platform owns the control screen, publish only its documented data schema rather than drawing an assumed framebuffer.
- Cache static surfaces/text and update score regions/snapshots only when data changes.

### Acceptance tests

- Both themes cover every mode/state without changing physics/scoring and meet agreed contrast/readability checks.
- Main screenshots show full formation, large readable pins, slight overhead perspective, minimal lane, and no dense score table.
- Secondary snapshots show exact current player color, frame, throw, all frame scores/marks, totals, standings/ties, and winner for 1–4 players, including pending bowling bonuses and tenth frame.
- Display versions remain synchronized across skipped animations, rapid turns, restart, and game over.

### Emulator tests

- At exact native dimensions, capture both themes/modes/player counts and verify secondary updates via the official emulator; test disconnect/backpressure/reconnect only if documented.
- Validate no clipping, stale score, color ambiguity, or excessive main-screen text.

### Hardware tests

- Review both displays from normal throw/control distances and under cabinet lighting; validate Blue/Red/Green/Yellow distinguishability, latency/synchronization, winner/tie screens, burn-in/static-content considerations, and theme brightness.

### Dependencies and unresolved questions

- This phase is gated on the secondary API, ownership, pixel/data format, lifecycle, physical-cabinet parity, and emulator delivery behavior; 64×32 is only the recorded emulator renderer candidate.
- Confirm accessibility targets, approved fonts/assets, theme persistence behavior, and whether the control display accepts touch input.

### Rollback point

Theme and secondary adapters are independently feature-flagged. Fall back to regular theme plus compact verified main-display status, never a fabricated secondary output.

## Phase 6: Audio, animation, balancing, performance, emulator validation, and physical-hardware testing

### Goal

Polish and certify all modes on the supported cabinet without sacrificing fairness, responsiveness, stability, or comprehensibility.

### Files expected to change

- Approved audio/animation assets, mixer/audio adapter, animation/effects systems, tuning data, performance instrumentation, soak/end-to-end tests, deployment docs, and final manifests.

### Technical approach

- Add short, layered but concurrency-limited cues for launch, gutter, impacts, chain reactions, strike/spare, turn, and winner after cabinet audio is verified. Provide volume/mute where supported.
- Time animations independently of simulation; permit safe acceleration after score finalization without accepting a new throw too early.
- Balance using recorded anonymized coordinate→outcome sessions and objective repeatability/fairness metrics. Retain deterministic seeds and regression fixtures.
- Profile CPU, allocation, framebuffer conversion/copy, frame drops, input latency, memory growth, audio latency, and temperature. Cache/pool resources and define graceful effect degradation.
- Run a complete versioned emulator/cabinet qualification matrix and document install, launch, logs, data migration, rollback, and known limitations.

### Acceptance tests

- Every mode/theme/player/frame combination completes; scoring and fairness suites remain green.
- Audio assets initialize/fail gracefully according to the verified API; no clipping, excessive concurrency, or missing-file crash.
- Animations finish within tuned limits, never change finalized scores, and never consume an early next throw.
- Measured FPS/input latency/memory/frame-drop targets established in Phase 0 are met at worst case; multi-hour soak has no unbounded growth or state corruption.
- Persistence round-trip/version migration and corrupted-data recovery preserve game launch; high scores, if product-approved, are correctly namespaced and validated.

### Emulator tests

- Automated smoke matrix for all modes/themes/player counts; scripted golden games; secondary sync; audio where emulator supports it; restart/home/SIGINT; malformed params/store; busy framebuffer; and 8-hour soak.
- Archive emulator version, commands, logs, screenshots, performance traces, and pass/fail report.

### Hardware tests

- Test every supported cabinet/firmware revision: all dart colors/zones, buttons/control screen, both displays, audio, brightness, persistence/reboot, network-independent launch, long soak, thermal load, power interruption, home/exit, install/update/rollback.
- Run novice first-turn comprehension and repeat-player skill/fairness sessions for every mode. Compare players’ shared schedules and detect color/index bias.
- Obtain final operator/product acceptance with documented evidence and known-issue disposition.

### Dependencies and unresolved questions

- Official supported hardware/firmware matrix, cabinet access, deployment/signing process, audio and secondary APIs, measurable performance targets, asset licenses, accessibility/safety criteria, and test participants.

### Rollback point

Create a release candidate tag before polish. Each audio/effect/balance change is data-driven or isolated and reversible; deployment must retain the previous signed cabinet package.

## Recommended first implementation task

After obtaining (or formally recording the absence of) the official multiplayer sample and display specifications, implement a **pure regulation bowling scorer plus legal roll/rack state machine** in a new domain module with exhaustive tenth-frame tests. It is independently testable, requires no undocumented hardware API, fixes the highest-risk correctness defect, and becomes the scoring contract used by multiplayer and both displays. Do not begin by redesigning graphics or guessing the secondary screen.

### Implementation status — Phase 0A: Regulation bowling scoring and rack-state core

**IMPLEMENTED — LOCALLY VERIFIED.** Added `throw_a_strike/__init__.py`,
`throw_a_strike/domain/__init__.py`, `throw_a_strike/domain/bowling.py`,
`tests/__init__.py`, and `tests/test_bowling.py`; this status entry is the only
other change. `python -m unittest discover -s tests -v` passed 31 tests, Python
syntax compilation passed for all new Python files, and `git diff --check`
passed. The module is deliberately not integrated with gameplay, rendering,
physics, multiplayer, or hardware. Cabinet and Dartsnut hardware verification
was not performed; the unresolved hardware limitations elsewhere in this plan
remain.

### Implementation status — Phase 0B: Pure multiplayer match and turn-order domain

**IMPLEMENTED — LOCALLY VERIFIED.** Added
`throw_a_strike/domain/match.py` and `tests/test_match.py`, and updated
`throw_a_strike/domain/__init__.py` to export the public match types; this status
entry is the only other change. `python -m unittest discover -s tests -v` passed
all 51 tests (the existing 31 bowling tests and 20 multiplayer tests), Python
syntax compilation passed for both domain modules and both test modules, and
`git diff --check` passed. The model supports the locked one-to-four-player
color order, independent games and racks, regulation frame rotation, immutable
snapshots, competition standings, and tied winner sets. It remains a pure
domain model and is not integrated with the prototype. No Dartsnut input or API,
dart-index/color hardware mapping, rendering, physics, menus, audio, secondary
screen, or cabinet hardware work occurred. Those integrations and all existing
hardware limitations remain future work.

### Implementation status — Phase 0C: Pure cumulative two-throw scoring core

**IMPLEMENTED — LOCALLY VERIFIED.** Added
`throw_a_strike/domain/cumulative.py` and `tests/test_cumulative.py`, and updated
`throw_a_strike/domain/__init__.py` to export the cumulative game's six public
types; this status entry is the only other change. The game accepts immutable
tuples containing exactly 3, 5, or 10 positive, non-boolean integer frame
maximums, including frame-specific maximums. Every frame requires exactly two
rolls against one decreasing score capacity, even when roll one consumes all
capacity, in which case roll two must be zero. Scores are the direct sum of
accepted points; there are no strike, spare, fill-ball, or other bonuses.

`python -m unittest discover -s tests -v` passed all 77 tests (the existing 31
bowling tests, existing 20 multiplayer tests, and 26 cumulative tests). The
requested Python syntax compilation, protected-file check, `git diff --check`,
and repository status inspection also passed. This remains a one-player pure
domain model. No cumulative multiplayer coordination, prototype/game
integration, graphics, rendering, physics, menus, input, audio, Dartsnut API,
dart-color mapping, or cabinet/hardware integration occurred. Those systems
and all existing hardware limitations remain future work.

### Implementation status — Phase 0D: Pure cumulative multiplayer match coordinator

**IMPLEMENTED — LOCALLY VERIFIED.** Added
`throw_a_strike/domain/cumulative_match.py` and
`tests/test_cumulative_match.py`, updated `throw_a_strike/domain/__init__.py` to
export all seven cumulative-match public types, and added this status section to
`IMPLEMENTATION_PLAN.md`. `python -m unittest discover -s tests -v` passed all
103 tests: the unchanged 31 bowling, 20 regulation multiplayer, and 26
cumulative tests plus 26 cumulative-match tests. The requested Python syntax
compilation, protected-file check, `git diff --check`, and repository status
inspection also passed.

The coordinator supports one through four players in fixed Blue, Red, Green,
Yellow order. Every active player owns an independent cumulative game with the
same immutable frame-maximum sequence. Each player retains the turn for both
required rolls, including a required zero second roll after using all capacity;
only the second accepted roll rotates. The independently tracked global frame
advances and returns control to Blue only after every active player finishes
that frame. Immutable detached snapshots expose player state, current global
turn state, provisional/final competition-ranked standings, and every final
winner tied at the highest score. Invalid rolls leave the complete match state
unchanged.

This remains domain-only coordination. It does not implement 100-pin
formations, Remix object schedules, Party targets/reactions, mode or prototype
integration, physics, rendering, menus, input, audio, Dartsnut APIs, secondary
screens, physical dart-color mapping, hardware, or cabinet behavior. Those
systems and all previously recorded hardware limitations remain future work.

### Implementation status — Phase 0E: Immutable match configuration and deterministic shared schedules

**IMPLEMENTED — LOCALLY VERIFIED.** Added
`throw_a_strike/domain/config.py`, `throw_a_strike/domain/schedule.py`,
`tests/test_config.py`, and `tests/test_schedule.py`; updated
`throw_a_strike/domain/__init__.py` with the new public exports; and added this
status section to `IMPLEMENTATION_PLAN.md`. The full command
`python -m unittest discover -s tests -v` passed all 147 tests (the unchanged
103-test baseline plus 44 configuration and schedule test methods). The
requested Python syntax compilation, protected-file check, prohibited-code
search, `git diff --check`, and repository status inspection also passed.

The locked modes are 10-Pin, 100-Pin, Remix, and Party, represented by
`ten_pin`, `hundred_pin`, `remix`, and `party`. The locked presentation themes
are Regular and Blacklight. Branding is frozen exactly as presenter
“Throw A Way Games,” game title “Throw a Strike,” and the two-line title
treatment “Throw A Way Games presents” followed by “Throw a Strike.” Frozen
`MatchConfig` values require actual mode/theme enum members, one through four
players, and an unsigned 64-bit seed. 10-Pin requires exactly ten frames;
100-Pin, Remix, and Party permit exactly three, five, or ten.

Configuration and schedule payloads use schema version 1, primitive JSON-safe
values, complete nested match configuration, detached mutable payload
containers, strict reconstruction validation, and equality-preserving replay.
All domain-side definitions, frames, schedules, and their exposed collections
are frozen or tuples. Party replay embeds the selected setup's complete
identifier metadata and frame maximum, so reconstruction does not require the
source catalog.

Schedule selection uses SHA-256 over canonical UTF-8 fields beginning
`throw-a-strike|schedule|v1`, the decimal unsigned match seed, and documented
purpose-specific fields. The first eight digest bytes form an unsigned
big-endian selection value. Remix deterministically selects exactly two values
from the locked nine-object catalog for each one-based frame, with a maximum of
10 per frame. Party requires a caller-provided, nonempty immutable catalog with
unique setup IDs and validated identifier tuples/positive maximums. A canonical
JSON SHA-256 fingerprint covers the complete ordered catalog; that fingerprint
drives deterministic setup selection, per-frame unsigned 64-bit seeds, and
mystery-outcome ordering. Party frame maximums exactly mirror selected setup
maximums. Exact seed-42 Remix and Party vectors, including the Party catalog
fingerprint, selections, mystery order, maximums, and frame seeds, lock the
algorithm against drift.

Schedules are authoritative match-level values rather than per-player values.
Player count and presentation theme are deliberately absent from competitive
derivation, so every player receives the same frame/throw sequence and changing
only player count or theme preserves competitive results. The full
configuration remains attached for replay.

This phase records only configuration and supplied Party metadata; it does not
invent Party mechanics, reactions, scoring rules, target behavior, object
physics, or rendering properties. No menu, mode, existing match, prototype,
graphics, physics, rendering, input, audio, display, Dartsnut, physical
dart-color mapping, cabinet, or hardware integration occurred. Those systems
and all previously recorded hardware limitations remain future work.

## Phase 0F: Pure application and game-session state machine

**Status: IMPLEMENTED - LOCALLY VERIFIED**

This phase created `throw_a_strike/application/__init__.py`,
`throw_a_strike/application/session.py`, and `tests/test_session.py`, and updated
only this implementation plan. The full command
`python -m unittest discover -s tests -v` passed all 165 tests (the unchanged
147-test baseline plus 18 session test methods). The requested `py_compile`
command, protected-file check, prohibited-integration search,
`git diff --check`, and repository status inspection also passed.

The public string-valued session phases are `CONFIGURING`, `READY`,
`AWAITING_THROW`, `SHOWING_RESULT`, `PLAYER_TRANSITION`, `FRAME_TRANSITION`,
`GAME_OVER`, and `CANCELLED`. `GameSession` publicly provides `configure`,
`start`, `submit_throw`, `acknowledge_result`, `continue_transition`, `replay`,
`cancel`, and `snapshot`. Incorrect-phase calls raise
`InvalidSessionTransitionError` atomically. Configuration requires an actual
`MatchConfig`: 10-Pin and 100-Pin reject schedules, Remix requires a matching
`RemixSchedule`, and Party requires a matching `PartySchedule`. Supplied
schedules are consumed unchanged and are never regenerated.

Starting and replay construct a fresh private engine in a local variable before
committing session state. 10-Pin uses `BowlingMatch(player_count)`, 100-Pin uses
`CumulativeMatch(player_count, (100,) * frame_count)`, and Remix and Party use
`CumulativeMatch(player_count, schedule.frame_max_scores)`. No mutable match
engine, games collection, or player collection is exposed; callers receive
only the domain's immutable snapshots.

Throws are accepted exclusively in `AWAITING_THROW`. An accepted throw records
its player/color, global frame, throw number, value, capacity/rack before and
after, transition flags, next player, and exact applicable schedule metadata,
then enters `SHOWING_RESULT`. Domain roll errors propagate unchanged and leave
the entire session unchanged. Result acknowledgment prioritizes match complete,
global-frame completion, player-turn completion, and same-player continuation,
entering `GAME_OVER`, `FRAME_TRANSITION`, `PLAYER_TRANSITION`, or
`AWAITING_THROW`, respectively. Player/frame continuation only opens the next
input window because the domain engine already performed rotation.

Remix lookup uses the match's global frame and throw, ensuring each player gets
the exact same scheduled object for a corresponding frame/throw. Party lookup
uses the global frame only, ensuring both throws and every player share the
exact immutable Party frame. Accepted-result snapshots retain that exact
metadata. Neither mode invents mechanics, physical properties, or scoring
beyond the supplied schedule maximums.

Final throws remain in `SHOWING_RESULT` until acknowledged into `GAME_OVER`,
where final immutable standings, all tied winners, configuration, schedule, and
last throw remain available. Replay is available only there, clears the last
throw, creates a zero-score engine, immediately opens the first throw, and
retains the exact configuration and immutable schedule object. Cancellation is
available from every non-cancelled phase, retains configuration, schedule,
latest match snapshot, and last throw, closes normalized current fields, and
permanently blocks every state-changing operation.

`SessionSnapshot` and `SessionThrowSnapshot` are frozen dataclasses. Their
reachable public collections come only from immutable schedule and domain
snapshot tuples. Normalized current frame/player/color/throw/availability and
schedule metadata are populated only in `AWAITING_THROW`; every blocked phase
reports them as `None`. Retained snapshots remain detached from later engine
mutation.

This remains pure application logic. It does not provide clocks, ports,
presentation timing, input queueing, or Party gameplay mechanics. No rendering,
menus, visual widgets, physics, collision detection, input adapter, keyboard
handling, audio, Dartsnut API, secondary display, persistence, networking,
prototype integration, physical dart-color mapping, or hardware behavior was
added.

## Phase 0G: Pure application ports, capability models, and test fakes

**Status: IMPLEMENTED - LOCALLY VERIFIED**

This phase created `throw_a_strike/application/ports.py`,
`throw_a_strike/application/fakes.py`, and `tests/test_ports.py`, and updated
`throw_a_strike/application/__init__.py` and this implementation plan. The full
command `python -m unittest discover -s tests -v` passed all 187 tests (the
unchanged 165-test baseline plus 22 port test methods). The requested
`py_compile` command, protected-file check, prohibited-import and scope
searches, `git diff --check`, and repository status inspection also passed.

Six runtime-checkable structural protocols now define the pure boundaries:
`MainDisplayPort.present(SessionSnapshot)`,
`SecondaryDisplayPort.present(SessionSnapshot)`, `InputPort.poll()`,
`ClockPort.monotonic_seconds()`, `AudioPort.play(AudioRequest)` plus `stop()`,
and `StoragePort.load()`, `save()`, plus `delete()`. Each protocol exposes only
its matching immutable capability snapshot and contains no implementation
state. Runtime checks confirm all six fakes satisfy their respective protocol.

Frozen `PortCapabilities`, `DisplayCapabilities`, `StorageCapabilities`, and
`ApplicationCapabilities` values strictly reject coercion and invalid field
types. Displays explicitly support available-but-unknown dimensions without
inventing defaults. Capability collection reads capability snapshots only,
copies them into a detached frozen aggregate, and represents an omitted
secondary display, audio port, or storage port as explicitly unavailable. This
models optional secondary display capability without claiming that platform
support exists.

The frozen neutral input model contains only a `DART_HIT` or `CONTROL` kind,
sequence, monotonic timestamp, and the fields appropriate to that kind. Dart
indices and control IDs remain opaque; coordinates are finite raw real values.
No color, player, named control, score, force, pressure, speed, or bowling
result is inferred. Frozen audio requests similarly retain only an opaque cue
ID, loop flag, and bounded volume, without defining a cue catalog.

Deterministic in-memory main and secondary displays record immutable session
snapshots; input queues and drains events FIFO; the clock advances only by
validated nonnegative amounts; audio records play and stop requests; and
storage provides sorted byte-keyed contents. Every public history, queue, or
contents view is a newly returned tuple, never the fake's internal list or
dictionary. Invalid operations are atomic. Unavailable fakes reject all
operational use, while available read-only storage permits loads but rejects
saves and deletes without mutation.

This phase remains contracts and test infrastructure only. It did not add an
adapter, runner, renderer, drawing, application loop, physics, menus, audio
playback, file or persistence backend, networking, database, Dartsnut access,
secondary-display integration, hardware dimensions, control interpretation,
dart-color mapping, or any other hardware integration. `GameSession` and all
domain behavior remain unchanged. Presentation/view-model transformation and
explicit fallback composition remain future work.

## Phase 0H: Pure main-display and secondary-scoreboard view models

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- Exact files changed: `throw_a_strike/application/presentation.py`, `tests/test_presentation.py`, `throw_a_strike/application/__init__.py`, and `IMPLEMENTATION_PLAN.md`.
- Full verification command: `python -m unittest discover -s tests -v`; all **208 tests** pass (the 187-test baseline plus 21 presentation test methods). The requested focused presentation suite, `py_compile`, protected-file, forbidden-import, `git diff --check`, and status checks also pass.
- Public API: `PresentationPrompt`, `ScoreboardPlacement`, the frozen frame, player, standing, winner, throw-result, scoreboard, main-display, secondary-scoreboard, and bundle view models, `InvalidPresentationValueError`, and `build_presentation` are exported without removing prior application exports.
- Locked identity: configured models use `LOCKED_BRANDING`; mode labels are exactly `10-Pin`, `100-Pin`, `Remix`, and `Party`, and theme labels are exactly `Regular` and `Blacklight`.
- Phase prompts map configuring, ready, awaiting throw, showing result, player transition, frame transition, game over, and cancelled to their eight specified semantic prompt keys.
- Regulation scorecards copy every domain frame, roll value, mark, resolved or unresolved score, cumulative score, completion state, and confirmed total without recalculation.
- Cumulative scorecards copy accepted point values and maximums, use decimal roll labels, and derive only the specified running presentation total while distinguishing untouched frames from started zero-point frames.
- Accepted session results are copied field-for-field. Awaiting input suppresses stale results; result and terminal/transition phases retain the accepted result when present.
- Scoreboard focus uses normalized session fields while awaiting, the accepted throw while showing a result, the advanced match-level fields during player/frame transitions, and no focus at game over or cancellation.
- An available secondary capability receives the sole scoreboard model even with unknown dimensions. An unavailable secondary capability puts the sole complete scoreboard on the main model. A session without a match has no scoreboard and `NONE` placement.
- Domain standing order and competition ranks are copied without sorting; every domain-provided tied winner is retained in domain order.
- All presentation models are frozen and strictly validate exact constructor types; every public collection rejects lists, dictionaries, and sets and accepts only exact tuples of exact model values. Input snapshots are checked for phase, configuration, match, result, normalized input-window, and mode-specific schedule consistency before projection. Models contain only detached immutable snapshots and identities, so retained bundles cannot advance with a source session and expose no session, match engine, port, or mutable collection.
- Limitations: this phase publishes nothing and supplies no visual layout or user-facing localized copy. A future coordinator and verified adapters remain necessary.
- No rendering, drawing, dimensions, display operations, application loop, input handling, physics, audio playback, persistence, Dartsnut API, or hardware integration was introduced.

## Phase 0I: Pure presentation ports, publisher, and deterministic fakes

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- Exact files changed: created `throw_a_strike/application/publisher.py`,
  `throw_a_strike/application/publisher_fakes.py`, and
  `tests/test_publisher.py`; updated `throw_a_strike/application/__init__.py`
  and `IMPLEMENTATION_PLAN.md`.
- Verification: `python -m unittest discover -s tests -v` passes all **229
  tests** (the unchanged 208-test baseline plus 21 publisher test methods), and
  `python -m unittest tests.test_publisher -v` passes all 21 focused tests.
  The requested compilation, protected-file, prohibited-import, scope,
  whitespace, and repository-status checks also pass.
- Public types: `PublicationTarget`, frozen `PublicationReceipt`, runtime
  protocols `MainPresentationPort` and `SecondaryPresentationPort`,
  `PresentationPublisher`, `InvalidPresentationPublisherValueError`,
  `PresentationPublishError`, `FakeMainPresentationPort`, and
  `FakeSecondaryPresentationPort` are exported without removing earlier API.
- The presentation-specific signatures are
  `MainPresentationPort.present(MainDisplayViewModel) -> None` and
  `SecondaryPresentationPort.present(SecondaryScoreboardViewModel) -> None`;
  each exposes only an immutable `DisplayCapabilities` property.
- Construction structurally validates ports and exact capability types without
  presenting. Every publish preflight re-reads the exact main capability and,
  only when the supplied bundle contains a secondary model, the configured
  secondary capability. All required ports must be available before the first
  output operation; dimensions are never inspected.
- `NONE` and `MAIN` bundles publish their exact main object once and never call
  the secondary port. `SECONDARY` bundles publish the exact main object once,
  then the exact secondary object once. Placement is preserved: no scoreboard
  is copied, duplicated, rebuilt, rerouted, or automatically sent elsewhere.
- A successful frozen receipt always records main publication. `NONE` and
  `MAIN` record no secondary publication; `SECONDARY` records both. Receipts
  never represent partial failure.
- A main operation exception is chained in a `PresentationPublishError`
  targeting `MAIN`, with both progress flags false, no secondary attempt, and
  no retry. A secondary operation exception is chained targeting `SECONDARY`,
  with main true and secondary false, with no retry or fallback.
- Cross-port publication is explicitly **not transactional**. Once main
  publication completes, a secondary failure cannot be rolled back; the error
  exposes this partial-publication state rather than claiming atomicity.
- Both deterministic fake ports validate exact immutable view-model types,
  reject unavailable use atomically, retain accepted objects in order, and
  expose fresh immutable tuple histories. Retained history snapshots do not
  change retroactively, and no mutable collection or port is publicly exposed
  by the publisher.
- Remaining limitations: there is no controller, adapter, layout, localization,
  backpressure policy, or cross-display transaction mechanism. This phase adds
  no rendering, drawing, pixels, input polling, application loop, dimension
  interpretation, timing, physics, audio, storage backend, persistence,
  networking, Pygame, Dartsnut, or actual hardware integration.

## Phase 0J: Pure command-driven ApplicationController

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- Exact files changed: created `throw_a_strike/application/controller.py` and
  `tests/test_controller.py`; updated `throw_a_strike/application/__init__.py`
  and `IMPLEMENTATION_PLAN.md`.
- Verification: `python -m unittest discover -s tests -v` passes all **248
  tests** (the unchanged 229-test baseline plus 19 controller test methods),
  and `python -m unittest tests.test_controller -v` passes all 19 focused
  tests. The requested `py_compile`, protected-file, forbidden-import and scope
  searches, `git diff --check`, and repository-status checks also pass.
- Public command API: the exact eight-member string enum
  `ApplicationCommandKind` and frozen `ConfigureCommand`, `StartCommand`,
  `SubmitThrowCommand`, `AcknowledgeResultCommand`,
  `ContinueTransitionCommand`, `ReplayCommand`, `CancelCommand`, and
  `PublishCurrentCommand` use explicit, strictly validated values rather than
  strings, payload mappings, or generic parameters.
- Construction accepts only exact `ApplicationCapabilities` and
  `PresentationPublisher` values, publishes nothing, retains the immutable
  capability snapshot privately without inspecting dimensions, and creates
  and privately owns one new `GameSession`. No public property exposes the
  session, publisher, capabilities, or ports.
- Exact command dispatch is Configure→`configure`, Start→`start`,
  SubmitThrow→`submit_throw`, AcknowledgeResult→`acknowledge_result`,
  ContinueTransition→`continue_transition`, Replay→`replay`, Cancel→`cancel`,
  and PublishCurrent→`snapshot`. Exact command types are required, subclasses
  are rejected, and no command invokes a second or automatic operation.
- Every successful operation produces one snapshot, calls
  `build_presentation` once with that snapshot and the stored capability
  value, and calls `PresentationPublisher.publish` once with the exact bundle.
  `PublishCurrentCommand` obtains a fresh snapshot and republishes without
  mutating, deduplicating, or repeating an earlier session command.
- Frozen `ApplicationCommandResult` values strictly require and retain the
  exact command kind, session snapshot, presentation bundle passed to the
  publisher, and publication receipt returned by it. They contain no service,
  port, engine, or mutable collection.
- Main-only and secondary-enabled behavior remains entirely authoritative in
  `PresentationPublisher`: the controller neither alters placement nor
  duplicates, reroutes, falls back, or rebuilds scoreboards. Secondary output
  remains main-first and sequential, and dimensions have no dispatch effect.
- Session transition, configuration, and domain scoring failures propagate
  unchanged before presentation construction or publication. They are not
  wrapped, retried, or converted into publication failures.
- Publisher preflight and operation failures are chained in
  `ApplicationControllerPublishError`, which retains the exact command kind,
  advanced snapshot, failed bundle, original publisher-related cause, and
  accurate main/secondary progress. Unrelated programming exceptions are not
  caught.
- Session mutation completes before publication. A publication failure can
  therefore leave the controller in READY, AWAITING_THROW, SHOWING_RESULT, or
  another successfully reached phase. There is deliberately **no rollback or
  cross-layer transactionality**. A caller can later use
  `PublishCurrentCommand` to publish that advanced state without reapplying the
  original mutation; no retry or recovery is automatic.
- The controller uses its construction-time immutable capability snapshot for
  every presentation build and does not recollect capabilities or inspect
  publisher ports. Actual publisher-port availability is checked later by the
  publisher, so capability/port drift can correctly surface as a controller
  publication error.
- Remaining limitations: this is command coordination only. It adds no input
  polling, command translation, application loop, timing, animation,
  rendering, pixels/framebuffers, physics, coordinate or dart-index mapping,
  audio, storage backend, persistence, Pygame, Dartsnut, networking, hardware
  adapter, or hardware integration. The next task should be a verified
  Dartsnut platform-contract spike, not a speculative adapter.

## Risk register

| Risk | Likelihood / impact | Mitigation and trigger |
|---|---|---|
| Emulator main canvas is observed at 128×128 while the project submits 128×160 | High / Critical | Use 128×128 as the renderer candidate, but verify physical-cabinet parity, framebuffer length, format, and orientation before production UI integration. |
| No game-accessible secondary screen/API | High / Critical | Obtain official sample/API; design snapshot publisher and capability handling; escalate product layout if platform owns it. |
| Dart index is not a stable color identity | High / High | Official mapping plus repeated cabinet trace; keep turn identity separate; never hard-code guesses. |
| Remix/Party shared schedules or setups diverge between players | Medium / High | Persist one authoritative per-frame sequence/setup and seed; assert identical maximum opportunity and reset state for every player. |
| Random/chaotic physics overwhelms skill or biases turn order | Medium / High | Deterministic simulation, shared schedules/seeds, repeatability and outcome-distribution tests, recorded hardware balancing. |
| 100-pin/Party chains miss frame budget | Medium / High | Spatial broad phase, event/effect caps, pooling, fixed timestep, early cabinet profiling and worst-case benchmark. |
| SDK changes under unconstrained dependency | Medium / High | Pin audited version; contract tests; review upgrade diffs deliberately. |
| Physical coordinate orientation/noise differs from package docs | Medium / High | Nine-zone calibration on every supported cabinet revision; configurable documented transform. |
| Throws are consumed during results/animations | High / Medium | Explicit input windows, dart-removal/re-arm state, event queue policy, rapid-throw hardware tests. |
| Pygame/audio unavailable or misrouted on cabinet | Medium / Medium | Verify official audio route/sample early; graceful capability handling; approved formats and channel limits. |
| Asset/package limits or licensing block presentation | Medium / Medium | Obtain packaging spec, asset budget/license ledger, CI validation before content production. |
| Persistence location/quota/migration differs in production | Medium / Medium | Launcher-provided store, namespaced versioned schema, corruption/migration/reboot tests; avoid mandatory persistence for play. |
| Tiny resolution makes 100 pins unreadable | High / High | Confirm dimensions, prototype formation at native pixels, cabinet-distance test before full mechanics. |
| Ties/rank/name UX is undefined | Medium / Low | Product decision; domain returns winner sets and competition standings without forcing names. |

## Hardware questions that must be answered before development

1. Does the physical cabinet match the observed 128×128 emulator main canvas, and what are its RGB byte order, stride, maximum payload, refresh rate, orientation, and safe producer protocol? `conf.json` still declares 128×160 and must not be treated as validated.
2. What official API or platform data contract addresses the emulator-observed 64×32 secondary/control screen? What are its format, ownership, lifecycle, refresh limit, launch arguments, and physical-cabinet parity?
3. Which dart indices map to Blue, Red, Green, and Yellow? Are there multiple darts per color, and are indices stable across boot, cabinet, replacement darts, and simultaneous hits?
4. Which physical direction corresponds to x=0/x=127 and y=0/y=127? What calibration, dead zones, jitter, sampling rate, simultaneous-hit behavior, and invalid-state timing should games expect?
5. What multiplayer flow and wrong-dart behavior do current Dartsnut games use? Provide source/sample and an installable reference game.
6. Which named buttons physically exist and how are A/B/home/reserved intended to behave? Is touch/control-screen input separate?
7. Is cabinet audio available to Pygame or another documented API? What device, formats, rates, channels, latency, focus, volume, and safety limits apply?
8. What is the official emulator, version, installation/launch command, input injection method, dual-display support, logging, and parity guarantee?
9. What is the game package/manifest schema, `.dartsnut` role, preview requirement, file/asset limit, working directory, supported Python/architecture, signing/install/update/rollback process?
10. How is `--data-store` provisioned in production? What are quota, retention, permissions, per-game isolation, migration, reset, and cloud/leaderboard capabilities?
11. Which cabinet and firmware versions must be supported, and what CPU/GPU/RAM/frame-time/thermal budgets and certification checks apply?

## Definition of done for the complete game

- Branding everywhere reads “Throw A Way Games” and “Throw a Strike” exactly as locked; metadata, title, previews, and packages are approved.
- 1–4 players use P1 Blue/P2 Red/P3 Green/P4 Yellow through the verified Dartsnut multiplayer flow; color mapping has documentary and physical-test evidence.
- 10-Pin implements regulation legal rolls and scoring, including every tenth-frame edge, and passes exhaustive/property/reference fixtures with final scores 0–300.
- 100-Pin provides exactly 100 pins, two throws against persistent remaining pins per player/frame, per-player resets, 3/5/10 frames, one point per pin, and no bonuses.
- Remix includes all named example objects with distinct tested behavior, a standard 10-pin rack reset for each player, exactly two throws against one persistent rack, one point per fallen pin, no bonuses, and an identical per-throw object sequence for every player in each frame.
- Party includes all named example pin types/formations with bounded reactions, exactly two throws against remaining targets, a per-player setup reset, defined target values, and identical setup, maximum score, reactions, mystery outcomes, and deterministic seed for every player in each frame.
- All modes declare the highest cumulative/final score winner and represent ties correctly; standings and totals never diverge between displays.
- Regular and Blacklight themes show a slightly overhead, complete, large/readable formation with minimal lane and first-turn comprehension validated with novice testing.
- Main display focuses on gameplay. Using the verified secondary API, the secondary display shows current player color, frame, throw, frame scores/marks, totals, standings, and winner at the correct native resolution.
- Dart input, all relevant controls, display backpressure, home/exit, audio, persistence, packaging, deployment, and rollback use only documented/verified APIs and fail safely.
- Deterministic fairness tests, unit/property/integration suites, golden visual tests, complete emulator matrix, physical cabinet matrix, worst-case profiling, and multi-hour soak all pass against recorded targets.
- Assets are licensed, packaged within official limits, readable/accessible, and audio/visual effects meet approved safety and volume/flash criteria.
- Installation, configuration, operator controls, test evidence, known limitations, data migration, diagnostics, and rollback are documented; product/operator acceptance is signed off with no critical unresolved hardware capability.

## Phase 0K: Verified pydartsnut 1.2.1 platform-contract evidence spike

**Status: EVIDENCE COMPLETE - EXACT WHEEL VERIFIED**

- Exact files changed: created `docs/platform/DARTSNUT_PLATFORM_CONTRACT.md`,
  `docs/platform/DARTSNUT_CABINET_VERIFICATION_CHECKLIST.md`,
  `docs/platform/evidence/pydartsnut-1.2.1-contract.json`,
  `tools/inspect_pydartsnut_wheel.py`, and
  `tests/test_dartsnut_platform_contract.py`; updated only `pyproject.toml`,
  `uv.lock`, `PROJECT_AUDIT.md`, and `IMPLEMENTATION_PLAN.md`.
- Inspected package: `pydartsnut` 1.2.1, wheel
  `pydartsnut-1.2.1-py3-none-any.whl`, SHA-256
  `a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f`.
  Static inspection verified the hash before opening the ZIP, exact METADATA
  identity/version, RECORD, source hashes, AST symbols, and line ranges.
- Evidence generation: `python tools/inspect_pydartsnut_wheel.py
  .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl --expected-sha256
  a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f
  --output docs/platform/evidence/pydartsnut-1.2.1-contract.json`; the equivalent
  `--check` command reproduces the committed bytes.
- Dependency: `pyproject.toml` now requires exactly `pydartsnut==1.2.1`.
  `uv.lock` changes only project requirement metadata; pydartsnut version,
  wheel/sdist hashes (sdist
  `f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e`),
  Pygame/NumPy versions, and unrelated resolutions remain unchanged.
- Verified findings: the main-frame method accepts bytearray/tobytes inputs,
  describes RGB888, uses boolean ready/busy/invalid outcomes, and encodes no
  width/height/length. Dart polling has 12 slots; event/active values are
  `(dart_index, x, y)`, indices 0–11 and coordinates 0–127. The implementation
  blocks duplicates and defaults to 0.2 seconds invalid before re-arm. Buttons
  expose the exact eight documented keys with 30 ms polling debounce and rising
  events. Running/SIGINT, brightness range 10–100, JSON widget parsing, shared
  memory initialization/cleanup, and atomic-replace JSON persistence are
  recorded with exact evidence pointers.
- Repository assumptions remain unchanged: `main.py` and `conf.json` use
  128×160; runtime polls event APIs, treats hits as index/x/y, observes
  `engine.running`, and submits through the SDK main-frame method.
- Contradictions: 128×160 in runtime/manifest versus no package-encoded display
  dimensions and 0–127 package coordinate prose; method prose says 0.5-second
  re-arm while implementation defaults to 0.2. None is resolved by preference.
- Secondary search: no API was found for any required term. This does not prove
  the launcher, cabinet, another package, or a private API lacks such support.
- Unknowns include physical size/channel order/stride/orientation/calibration,
  refresh and drop policy, dart color mapping/stability, real simultaneous
  input, wrong-dart policy, secondary/touch/audio, emulator/launcher/package,
  storage retention, compatibility, and performance budgets. Operator follow-up
  is specified in `docs/platform/DARTSNUT_CABINET_VERIFICATION_CHECKLIST.md`.
- Safe boundaries: a narrow injected package facade, neutral raw event capture,
  verified submission validation, running observation, and deterministic fakes.
  Blocked work: choosing final native size, physical transform/color/policy,
  secondary output, audio, deployment, and performance targets.
- Validation commands: full `python -m unittest discover -s tests -v`; focused
  `python -m unittest tests.test_dartsnut_platform_contract -v`; plus evidence
  `--check`, `py_compile`, protected-file, archive, scope, diff, and status
  checks. Final suite before the integrity correction: **259 tests** (248 unchanged baseline plus 11 new tests).
- Remaining limitation: this evidence spike adds no adapter, rendering, input
  polling loop, physics, audio, storage adapter, Pygame integration, application
  loop, or hardware integration.

### Phase 0K evidence-integrity correction for PR #12

- Production inspection now requires the canonical filename, exact package
  name/version, computed locked wheel SHA-256, and the same canonical
  `--expected-sha256`; caller-selected hashes cannot bless modified wheels.
- Detailed values are extracted from precise AST/literal/docstring nodes.
  Missing and ambiguous values become unknown, and synthetic parser inspection
  is clearly separate and marked synthetic.
- The JSON contains 115 actual claim records (114 verified package
  metadata/source claims), 24 hardware unknowns, and 3 contradictions.
  `generated_claim_count` is the length of the claims collection, not evidence
  pointer count. Every verified claim references precise evidence.
- Secondary search covers source text, classes, methods, module functions,
  public assignments, imports/exports, string constants, METADATA headers and
  description, RECORD paths, and safely decoded small UTF-8 files; result arrays
  are populated from matches rather than constants.
- Focused coverage is now 28 tests. The complete suite is **276 tests**: the
  existing unchanged 248 tests plus 28 Phase 0K integrity tests. Final literal
  integrity coverage proves dictionary-comprehension values, temporary suffix
  strings, duplicate constructor options, conflicting button dictionaries, and
  three-way secondary-search status classification are source-derived or
  conservatively unknown.

## Phase 0L: Narrow dependency-injected Dartsnut SDK facade

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** The unchanged baseline was 276 tests; the final suite is 315 tests, including 39 focused facade tests.
- **Exact files changed:** created `throw_a_strike/platform/__init__.py`, `throw_a_strike/platform/dartsnut_sdk.py`, `throw_a_strike/platform/dartsnut_sdk_fakes.py`, and `tests/test_dartsnut_sdk.py`; updated only this plan and `PROJECT_AUDIT.md`.
- **Public types:** `DartsnutButtonId`, `RawDartHit`, `DartsnutSdkOperation`, `DartsnutSdkProtocol`, `DartsnutSdkFacade`, `FakeDartsnutSdk`, `InvalidDartsnutSdkValueError`, `InvalidDartsnutSdkResponseError`, and `DartsnutSdkOperationError`.
- **Wrapped SDK surface:** the facade reads `running` and calls only `get_dart_hits()`, `get_button_events()`, `reset_blocking_state()`, `update_frame_buffer(frame)`, `set_brightness(brightness)`, and `close()`.
- **Validation and errors:** exact raw list/tuple/dict/bool/integer shapes and ranges are enforced. Malformed completed responses use an operation-tagged response error; operational exceptions use an operation-tagged error, retain and chain the exact cause, and are never retried.
- **Fake:** the dependency-injected deterministic SDK-shaped fake provides FIFO dart, button, and framebuffer-result queues plus immutable call, framebuffer, brightness, reset, close, and queue inspection values.
- **Framebuffer and brightness:** opaque exact `bytes`/`bytearray` values are copied into a fresh `bytearray` and forwarded without dimension, stride, channel, or length validation. Brightness accepts only exact integers from 10 through 100, with no clamping.
- **Explicit exclusions:** no retry/wait policy, framebuffer dimension validation, player/color mapping, coordinate transformation, concrete `pydartsnut` import/construction, hardware/shared-memory access, renderer, loop, or secondary-display behavior was introduced.
- **Remaining limitations:** physical-cabinet display parity, pixel orientation/order, backpressure policy, physical axis orientation, dart ownership/color, and the supported secondary-output API remain unresolved. Phase 0K remains the unchanged package-source evidence baseline.
- **Recommended next task:** Phase 0M should add a neutral `InputPort` adapter that consumes facade values, uses an injected clock, adds monotonic sequence values, and preserves raw identifiers and coordinates without gameplay interpretation.


### Phase 0L follow-up: recorded emulator display evidence

**Evidence classification: VERIFIED_EMULATOR_OBSERVATION.** A recorded emulator run visibly confirms the intended emulator canvases as **128×128 for the main gameplay display** and **64×32 for the second/control display**. The screenshot also shows that the deployment panel was **not connected to the bound physical device**, so this observation must not be represented as verified physical-cabinet behavior.

- **Future renderer candidate targets:** main renderer `128×128`; secondary renderer `64×32`.
- **Boundary retained:** `DartsnutSdkFacade` continues to forward opaque bytes without width, height, stride, channel, or payload-length validation. No renderer or secondary-display implementation is added in Phase 0L.
- **Still unresolved:** the supported secondary-screen SDK submission API, physical-cabinet parity, formats/orientation, lifecycle, and delivery behavior.
- **Evidence integrity:** this observation supplements but does not modify or reclassify the Phase 0K package-source evidence JSON.

## Phase 0M: Neutral Dartsnut InputPort adapter

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** the unchanged baseline was 315 tests; the final suite is 337 tests, including 22 focused adapter tests.
- **Exact files changed:** created `throw_a_strike/adapters/__init__.py`, `throw_a_strike/adapters/dartsnut_input.py`, and `tests/test_dartsnut_input.py`; updated only this plan and `PROJECT_AUDIT.md`.
- **Constructor boundary:** `DartsnutInputPort` requires an exact injected `DartsnutSdkFacade`, a structurally valid injected `ClockPort`, and an optional exact nonnegative integer initial sequence. Construction invokes no facade or clock-time operation and captures clock capabilities exactly once.
- **Capabilities:** the adapter returns detached exact `PortCapabilities` values based on the construction-time clock-availability snapshot; later reads neither revisit the clock nor invoke the facade.
- **Poll operation order:** each available explicit poll reads dart hits once, reads button events once, reads the injected monotonic clock once only for a nonempty combined batch, constructs the complete immutable result locally, commits sequence state, and returns an exact tuple.
- **Batch composition and timestamps:** all darts retain facade order and precede all buttons in facade order. This deterministic composition is not verified physical cross-source ordering. Every event in a nonempty batch receives the same single timestamp; coordinates and raw button values retain their numeric/string meaning under existing `InputEvent` normalization.
- **Sequences:** consecutive values begin at the injected initial sequence and continue across successful polls. Empty polls and all failures leave sequence state unchanged; no reset or wraparound API exists.
- **Empty and unavailable behavior:** empty polls perform both finite SDK reads but no clock read and return `()`. An unavailable snapshot rejects polling before any facade or clock operation.
- **Failures and source consumption:** facade, clock, and `InputEvent` errors propagate unchanged without retry. Reads are explicitly nontransactional: a button failure may follow consumption of darts, and a clock failure may follow consumption of both raw batches; there is no rollback, replay, or reconstruction even though sequence state remains unchanged.
- **Explicit exclusions:** no automatic blocking reset, player/color mapping, coordinate transformation/calibration, gameplay interpretation or command dispatch, continuous loop, timer, global clock, hardware access, rendering, physics, or secondary-display behavior was added.
- **Remaining limitations:** cross-source physical order is unknowable through the separate SDK methods, source consumption is nontransactional, and runtime input-window/reset policy remains intentionally outside this adapter.
- **Recommended next task:** Phase 0N should add a pure emulator-targeted immutable 128×128 framebuffer model and deterministic RGB888 encoder, without Pygame, facade submission, physical-cabinet parity claims, secondary-output guesses, or game rendering/assets.

## Phase 0N: Pure control style and one-throw setup machine

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** the Phase 0M baseline was 337 tests; the final suite is **364 tests**, including **21 focused configuration tests** and **23 focused throw-control tests**.
- **Exact files changed:** created `throw_a_strike/domain/throw_controls.py` and `tests/test_throw_controls.py`; updated `throw_a_strike/domain/config.py`, `throw_a_strike/domain/__init__.py`, `tests/test_config.py`, this plan, and `PROJECT_AUDIT.md`.
- **Configuration:** `ControlStyle` provides Quick Play (`quick`) and Advanced Play (`advanced`), with Quick Play as the `MatchConfig` default. Every one of 10-Pin, 100-Pin, Remix, and Party accepts either style. Schema version 2 has the exact former fields plus `control_style`; exact version 1 payloads migrate to Quick Play.
- **Quick Play:** a machine begins at **THROW READY**, always Straight and locked at 70 percent. One valid semantic dart command creates one immutable `ThrowSetup` while retaining its raw dart index, x, and y numbers.
- **Advanced Play:** the pure flow is SET CURVE, confirm, SET POWER, confirm, THROW READY, then one dart creates the setup. Curve levels in exact order are `LEFT_3`, `LEFT_2`, `LEFT_1`, `STRAIGHT`, `RIGHT_1`, `RIGHT_2`, `RIGHT_3`, labelled L3/L2/L1/STR/R1/R2/R3 with strengths -1.00/-0.66/-0.33/0.00/0.33/0.66/1.00.
- **Power meter:** each step lasts exactly 0.150 seconds and the repeating 1.8-second sequence is 70, 80, 90, 100, 90, 80, 70, 60, 50, 40, 50, 60. It has no duplicated endpoint pause and depends only on elapsed supplied command time. 80 is labelled **PERFECT** only; it adds no strike behavior or probability.
- **Timing and terminology:** **THROW READY** begins its own walkback/throw timer. Warning activates at 20 seconds; at 30 seconds the terminal result is **FOUL**, with no setup. Curve and power selection each default deterministically after eight seconds; a sparse command traverses every reached deadline.
- **Early darts:** darts during curve or power selection enter an untimed recovery, create no setup or foul, ignore controls until `REARMED`, preserve curve, and restart the recorded selection phase timer (and power meter at 70).
- **Monotonic and terminal behavior:** supplied timestamps may be equal but never decrease; a rejected backward command is atomic. COMPLETE and FOUL ignore later valid commands, preserve their immutable outcome, and offer no reset.
- **Future Phase 0O mapping (documentation only):** `btn_left` → LEFT, `btn_right` → RIGHT, `btn_a` → CONFIRM, `btn_b` → BACK, and dart-hit `InputEvent` → DART_HIT. The runtime will generate REARMED and TICK. `btn_up`, `btn_down`, `btn_home`, and `btn_reserved` have no Phase 0N gameplay action; HOME and RESERVED remain unchanged below the gameplay mapping layer.
- **Future selection rules:** Left/Right changes the highlighted style, A confirms, B returns to the previous setup page, Quick Play is highlighted by default, and a 15-second timeout chooses Quick Play. No setup UI or selection timer is implemented here.
- **Future prompt vocabulary:** SET CURVE, SET POWER, THROW READY, TOO SOON, REMOVE DART, THROW NOW, FOUL, and 0 PINS.
- **Explicit exclusions:** no `InputEvent` consumption or raw-button mapping; randomness, scoring, pinfall, probability, physics, player/color ownership, coordinate transformation/calibration, renderer, framebuffer, secondary display, platform/adapter imports, hardware, global clock, sleep, runtime loop, or automatic blocking reset.
- **Recommended next task:** Phase 0O should add only a pure input-to-control interpreter implementing the documented mappings while preserving timestamps and raw dart fields. It must not add player/color mapping, transforms, blocking reset, physics, scoring, rendering, or a continuous loop.

## Phase 0O: Pure InputEvent-to-throw-control interpreter

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** the Phase 0N baseline was 364 tests; the final suite is **394 tests**, including **30 focused Phase 0O tests**.
- **Exact files changed:** created `throw_a_strike/application/throw_control_input.py` and `tests/test_throw_control_input.py`; updated `throw_a_strike/application/__init__.py`, this plan, and `PROJECT_AUDIT.md`.
- **Exact mappings:** raw `btn_left`, `btn_right`, `btn_a`, and `btn_b` map to `LEFT`, `RIGHT`, `CONFIRM`, and `BACK`, respectively. A `DART_HIT` `InputEvent` maps to a `DART_HIT` command. The exact raw controls `btn_up`, `btn_down`, `btn_home`, and `btn_reserved`, as well as every other unmapped valid control ID, are ignored.
- **Dart recovery only:** mathematically integral application-boundary floats are recovered as exact integers (`-0.0` becomes numeric zero), then the domain enforces dart indices 0–11 and coordinates 0–127. Raw x/y order and numeric aim are preserved. There is no rounding, clamping, scaling, swapping, inversion, offset, rotation, or calibration.
- **Order, time, and sequence:** exact event timestamps are copied unchanged; mapped and duplicate events retain caller-supplied order, including equal or descending timestamps. Transport sequence values are consumed only through stream order and are intentionally neither copied into commands nor used to sort, deduplicate, or validate the batch.
- **Atomic pure batch:** an exact tuple is validated and interpreted from first to last, ignored controls are omitted, and failures raise without a returned partial tuple or external side effects. No mutable history is retained.
- **Architectural layer:** this application module translates the neutral application boundary value into an existing domain command without depending on adapters or platform code.
- **Explicit exclusions:** no polling, clock access or timestamp generation, machine construction/mutation, automatic `TICK` or `REARMED`, blocking reset, player/color mapping, curve/power calculation, physics, pinfall, scoring, rendering, framebuffer submission, hardware access, or runtime loop was added.
- **Recommended next task:** Phase 0P should add a pure runtime throw-control coordinator with injected `InputPort` and `ClockPort`, exactly one owned `ThrowControlMachine`, one finite batch and one clock-derived `TICK` per explicit step, preserved command order, and immutable results/snapshots. It must not add a loop, sleep, direct hardware/reset access, physics, pinfall, scoring, rendering/framebuffers, player/color mapping, or coordinate transformation.

## Phase 0P: Hardware-independent explicit-step throw-control coordinator

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** the Phase 0O baseline was 394 tests; the final suite is **411 tests**, including **17 focused Phase 0P tests**.
- **Exact files changed:** created `throw_a_strike/application/throw_control_coordinator.py` and `tests/test_throw_control_coordinator.py`; updated `throw_a_strike/application/__init__.py`, this plan, and `PROJECT_AUDIT.md`.
- **Constructor contract:** an exact `ControlStyle`, structurally valid injected `InputPort` and `ClockPort` with exact `PortCapabilities`, and a domain-valid `started_at` are required. Unavailable capabilities remain constructible. Construction reads capabilities and creates one machine, but does not poll, read time, interpret or apply commands. Invalid start values retain the chained domain error.
- **One-attempt ownership:** each coordinator privately constructs and permanently owns exactly one `ThrowControlMachine`; it accepts no machine, exposes no machine, and provides no reset or replacement operation. Later orchestration must create a new coordinator for each bowling attempt.
- **Explicit sequence:** each nonterminal `step()` checks terminal state, polls one complete finite batch exactly once, invokes the Phase 0O interpreter once, applies every mapped command in supplied order, then inspects the snapshot. Only when still nonterminal does it read the injected clock once, construct and apply one semantic `TICK`, and return the final record. Input always precedes the tick.
- **Terminal rules:** input-terminal COMPLETE/FOUL skips the clock and records `tick_timestamp=None`. A later step is rejected before polling or reading the clock, preventing an old attempt from consuming future input.
- **Immutable result:** the frozen result retains the exact valid event and mapped-command tuples, full applied input count, optional normalized tick timestamp, final exact immutable snapshot, and a derived terminal flag. Coordinator-generated `TICK` is represented only by the timestamp, not in the interpreted command tuple.
- **Staged errors:** `POLL_INPUT`, `INTERPRET_INPUT`, `APPLY_INPUT`, `READ_CLOCK`, and `APPLY_TICK` errors retain all valid progress available at their boundary and chain the operational cause. Failures are explicitly nontransactional: there is no repoll, reread, retry, input restoration, command rollback, or machine reconstruction.
- **Quick Play example:** one valid dart is mapped by Phase 0O, completes at Straight/70 percent with exact raw dart index and x/y aim, returns one event and command, and skips the clock.
- **Advanced Play example:** ordered Right/Confirm enters SET POWER before its tick; Confirm at exactly 0.150 locks 80 percent PERFECT and enters THROW READY before its tick; a later dart preserves curve, power, raw dart index, and x/y and completes without a clock read.
- **Timing:** a clock tick at 20 seconds activates warning and one at the exact 30-second THROW READY deadline creates FOUL with no `ThrowSetup`. `started_at`, event timestamps, and clock values must share the same monotonic domain; values are never offset, clamped, repaired, sorted, or reordered.
- **Explicit exclusions:** no `REARMED`, blocking reset, loop, sleep, global clock, adapter/platform or hardware access, physics, pinfall, scoring, session/controller mutation, rendering, framebuffer submission, secondary display, player/color mapping, or coordinate transformation was added.
- **Recommended next task:** Phase 0Q should add a pure immutable display-neutral throw-control presentation model for the locked prompts, curve labels, power percentage/feedback, and warning state. It must not draw pixels, submit framebuffers, invent secondary-display APIs, access hardware, reset blocking state, generate `REARMED`, or calculate physics, pinfall, or scores.

## Phase 0Q: Pure display-neutral throw-control presentation

**Status: IMPLEMENTED - LOCALLY VERIFIED**

- **Baseline/final verification:** the Phase 0P baseline was 411 tests; the final suite is **429 tests**, including **18 focused Phase 0Q tests**.
- **Exact files changed:** created `throw_a_strike/application/throw_control_presentation.py` and `tests/test_throw_control_presentation.py`; updated `throw_a_strike/application/__init__.py`, this plan, and `PROJECT_AUDIT.md`.
- **Public API:** `InvalidThrowControlPresentationValueError`, `ThrowControlPrompt`, `ThrowControlCurveIcon`, `ThrowControlPresentation`, `build_throw_control_presentation`, and `build_throw_control_step_presentation`.
- **Prompts and exact labels:** SET_CURVE → `SET CURVE`; SET_POWER → `SET POWER`; THROW_READY → `THROW READY`; TOO_SOON → `TOO SOON`; REMOVE_DART → `REMOVE DART`; THROW_NOW → `THROW NOW`; FOUL → `FOUL`; ZERO_PINS → `0 PINS`.
- **Exact phase mapping:** SET_CURVE and SET_POWER each use their corresponding sole primary prompt. Normal THROW_READY uses THROW READY alone; warning THROW_READY keeps THROW READY primary and adds THROW NOW secondary. EARLY_DART_RECOVERY uses TOO SOON plus REMOVE DART. COMPLETE has no prompts. FOUL uses FOUL plus 0 PINS.
- **Curve semantics:** LEFT_3, LEFT_2, and LEFT_1 map to semantic `LEFT`; STRAIGHT maps to `STRAIGHT`; RIGHT_1, RIGHT_2, and RIGHT_3 map to `RIGHT`. Labels and strengths remain the exact domain values; no glyph or asset file is selected.
- **Power semantics:** percentage is copied from `snapshot.displayed_power_percent`, feedback is copied from `snapshot.power_feedback`, and lock state is exactly whether `snapshot.locked_power_percent` is present. Feedback labels are WEAK, GOOD, PERFECT, POWER, and OVERDRIVE; PERFECT remains metadata only.
- **Terminal semantics:** COMPLETE is terminal with THROW outcome and deliberately has no completion prompt. FOUL is terminal with FOUL outcome and displays FOUL plus 0 PINS. Every nonterminal phase has no outcome.
- **Source of truth:** the snapshot builder maps only an exact immutable `ThrowControlSnapshot`; the step-result builder delegates exclusively through `result.snapshot` and does not reinterpret events, commands, or tick timestamp. Both builders are pure and retain no state.
- **Display-neutral boundary:** the frozen model describes presentation meaning only. It adds no dimensions, layout, coordinates, pixels, framebuffer, fonts, colors, art, animation, flashing cadence, orientation, stride, byte order, or display submission.
- **Explicit exclusions:** no hardware, Dartsnut, adapters, platform code, input polling, clock access, command generation, `TICK`, `REARMED`, blocking reset, machine/coordinator mutation, ball trajectory, physics, pinfall, scoring, session/controller changes, player/color mapping, coordinate transformation, or secondary-display API.
- **Accelerated recommended next task:** Phase 0R should be an Emulator Control Test Vertical Slice that renders this model and wires the existing input/coordinator into a finite emulator runtime. It may target the observed 128×128 main emulator display and the observed 64×32 control emulator display only through verified APIs, keep gameplay/pin deck dominant with a bottom HUD, and document any secondary-screen limitation rather than inventing a submission API. Ball trajectory, collision, pinfall, scoring, and multiplayer remain outside that slice.

## Phase 0R: Interactive emulator control-test vertical slice

**Status: IMPLEMENTED - EMULATOR TEST READY**

- **Baseline/final verification:** baseline 429 tests; final suite **468 tests**, including 4 clock, 11 selector, 8 renderer, and 16 runtime/entry-point tests.
- **Exact files:** created `throw_a_strike/adapters/system_clock.py`, `throw_a_strike/application/throw_control_style_selection.py`, both `throw_a_strike/rendering` files, both `throw_a_strike/runtime` files, four focused tests, and `docs/EMULATOR_CONTROL_TEST.md`; updated `main.py`, `conf.json`, adapter/application exports, this plan, and `PROJECT_AUDIT.md`.
- **Selection and rendering:** Quick begins selected, Left/Right select, A confirms strictly before the deadline, and the exact 15-second boundary confirms Quick before commands. Event batches are validated and interpreted once before timeout resolution. Pure drawing code produces deterministic 128×128 packed RGB888 bytes, a close ten-pin deck, and compact lower HUD with locked curve/power and the complete WEAK, GOOD, PERFECT, POWER, or OVERDRIVE feedback retained during THROW READY flashing.
- **Runtime wiring:** one existing Dartsnut input adapter feeds one coordinator constructed only after confirmation. Each active step polls/coordinators once and submits once. Quick and Advanced, warning/FOUL, accepted coordinates, failed framebuffer acceptance, strict step-phase consistency, entry-point/manifest behavior, and cleanup after construction, running-state, step, sleep, ordinary, and BaseException exits are covered.
- **Evidence boundary:** 128×128 and RGB888 are emulator-only observations/assumptions, not SDK or physical parity proof. No secondary submission API was found or invented.
- **Intentional hold:** early recovery caches TOO SOON/REMOVE DART and requires restart because no verified removal signal exists; it adds neither reset nor REARMED. Terminal state similarly requires restart.
- **Exclusions:** no trajectory, animation, collision, pin result, score, frame progression, multiplayer, player/color mapping, coordinate transformation, audio, asset, or cabinet claim.
- **Recommended next task:** Phase 0S should consume unchanged aim x/y, locked curve, and power to produce deterministic trajectory and pin-contact data plus post-dart animation, separate from scoring. It must add no randomness, mapping guesses, physical transforms, score submission, frame advancement, or multiplayer orchestration.

## Phase 0R.1: Dart rearming and automatic FOUL retry hotfix

**Status: IMPLEMENTED - RETEST READY**

- **Verification:** the final suite is **474 tests**, including **22 focused emulator-control runtime tests**.
- **Fresh-attempt boundary:** after manual Quick or Advanced confirmation, or the exact 15-second Quick timeout, the runtime consumes selection input, calls the existing facade `reset_blocking_state()` exactly once, constructs exactly one coordinator in the preserved style, and submits one initial framebuffer. Reset failures propagate before coordinator construction and runner cleanup still closes the facade.
- **FOUL retry:** FOUL plus 0 PINS is cached in `FOUL_HOLD` for exactly 1.5 seconds. Before the deadline each step reads the injected clock once, consumes no input, performs no reset, and resubmits the cached frame once. At or after the deadline, one reset precedes one clean coordinator and one fresh attempt framebuffer; Quick restarts at THROW READY/STR/70 and Advanced at SET CURVE/STR/70.
- **Unchanged holds:** COMPLETE alone uses `TERMINAL`, preserves exact raw dart index/x/y, and remains restart-only without reset. EARLY_DART_RECOVERY alone uses `RECOVERY_HOLD` and remains restart-only without polling, clock reads, reset, or `REARMED`.
- **Evidence boundary:** this narrow retest hotfix follows emulator evidence. It adds no physics, pinfall, scoring, multiplayer, coordinate transform, player mapping, secondary-display API, or physical-cabinet parity claim.

## Phase 0R.2: Visible dart acceptance and continuous throw retest

**Status: IMPLEMENTED - CONTINUOUS RETEST READY**

- **Verification:** the final suite contains **477 tests**, including **23 focused runtime tests** and **10 focused RGB888 renderer tests**.
- **Accepted diagnostic:** COMPLETE now enters `ACCEPTED_HOLD` and renders DART ACCEPTED plus the exact raw D-index/X/Y over the existing pin deck and locked curve/power HUD. It adds no ball, pinfall result, score, player/color mapping, or coordinate transformation.
- **Continuous retry:** the completed snapshot and `ThrowSetup` remain preserved. Before the exact 1.5-second deadline, each step reads the clock once, polls no input, performs no reset, and resubmits the cached diagnostic once. At the deadline, one reset and one new coordinator begin a clean attempt in the selected style and submit one fresh frame.
- **Unchanged paths:** FOUL retains its 1.5-second automatic retry. Early recovery retains its restart-only cached TOO SOON/REMOVE DART behavior without clock polling, reset, or `REARMED`.
- **Evidence boundary:** the second screen remains unused. Local click evidence does not establish a connected physical board or cabinet parity. No physics, pinfall, scoring, secondary-display API, or parity claim is added.

## Phase 0R.3: Emulator stale-dart replay-loop hotfix

**Status: IMPLEMENTED - EMULATOR LOOP RETEST READY**

- **Verification:** the final suite contains **480 tests**, including **26 focused emulator-control runtime tests**.

- **Direct evidence:** continuous emulator testing reported `Dart 0 BLOCKED (event fired at [77, 84])` and then `active at coordinate (77, 84)`. The emulator retained the active dart, and each automatic reset made the same coordinate available again. This disproves the Phase 0R.1 and 0R.2 automatic-reset assumptions.
- **Emulator reset policy:** this diagnostic runtime performs zero automatic `reset_blocking_state` operations during construction, selection, confirmation, timeout, attempt creation, accepted/FOUL retry, recovery, terminal handling, or cleanup. The verified facade operation remains unchanged for later physical-board work.
- **Stable retries:** A confirms style only. A new board event alone can produce DART ACCEPTED; its exact raw index/x/y holds for 1.5 seconds, then one fresh coordinator starts in the preserved style without reset. With no new click it stays active, so THROW NOW and FOUL remain reachable. FOUL likewise retries after 1.5 seconds without reset. Early recovery remains restart-only.
- **Evidence boundary:** the second screen remains unused. No physics, pinfall, scoring, multiplayer, coordinate transform, player mapping, secondary-display API, or physical-board assumption is added.


### Phase 0R.4 30-second throw timer record

**Status: IMPLEMENTED - 30-SECOND TIMER RETEST READY.** THROW READY now owns an exact 30-second attempt timer: THROW NOW begins at exactly 20 seconds and FOUL wins at exactly 30 seconds, producing a 10-second warning window. Time advancement still precedes same-timestamp commands, so a dart at the 30-second deadline loses to FOUL. Advanced SET CURVE and SET POWER time is excluded; its timer begins only on entry to THROW READY. Quick and Advanced retries receive clean timers and warning state. Accepted-dart and FOUL holds remain exactly 1.5 seconds, and emulator automatic blocking resets remain disabled.

**Final verification:** the complete suite passes **484 tests**.

Dartsnut Agent emulator evidence records displayed Blue 1/5/9, Red 2/6/10, Green 3/7/11, and Yellow 4/8/12, corresponding to raw zero-based indices Blue 0/4/8, Red 1/5/9, Green 2/6/10, and Yellow 3/7/11. This patch documents but does not implement that mapping. Standard game flow will later use the first two same-color darts per round; each third dart is reserved for later rules. This is not a physical-board parity claim. No scoring, round progression, player assignment, throw-slot enforcement, coordinate transformation, secondary-display API, or physical-board assumption was added.

## Phase 0S — two-throw round foundation

Status: IMPLEMENTED - TWO-THROW ROUND RETEST READY

The pure round contract now models two explicit throws, an unchanged or reduced standing rack, exact zero/PIN_HIT vocabulary, and the emulator-only same-color dart-slot policy. The diagnostic runtime exercises one Blue round with raw darts 0 then 4, temporary MISS results, wrong-dart rejection, per-throw FOUL progression, and a restart-only terminal screen. Physics, scoring, multiplayer/frame progression, transforms, and secondary output remain later phases.

The final retest correction preserves all locked control prompts beneath a compact round header, gives FOUL precedence over a wrong dart at the 30-second deadline, and rejects impossible manually constructed public round snapshots.

Final verification restores the locked THROW READY blink in that compact round HUD: blink-off hides only THROW READY, while THROW NOW and every non-ready prompt remain visible. The post-correction suite contains 502 passing tests.

## Phase 0S.1 — stale-safe emulator active-dart input

**Status: IMPLEMENTED - STALE-SAFE EMULATOR INPUT RETEST READY**

The emulator diagnostic now combines transition/block-based `get_dart_hits` events with continuous `get_active_darts` observation. Startup active darts form a non-scoring baseline; an absent-to-active transition or changed coordinate is a fresh placement, with same-dart evidence deduplicated in favor of the normal hit. This makes a retained raw Dart 0 movable after Quick confirmation without resetting SDK blocking state. Throw 1 FOUL still advances after 1.5 seconds to Throw 2, where any fresh Blue raw 0, 4, or 8 may complete the round.

This policy belongs only to the emulator adapter. The physical event adapter is unchanged and no physical-board behavior is inferred. No physics, scoring, multiplayer rotation, coordinate transform, secondary-display API, or automatic `reset_blocking_state` operation is added.

## Phase 0S.2 — active-player color enforcement

**Status: IMPLEMENTED - PLAYER-COLOR DART RETEST READY**

Bowling Throw 1 versus Throw 2 now comes only from the two-throw round state; physical dart identity no longer selects a throw. The emulator-confirmed color policy accepts Blue raw 0/4/8 for either throw when fresh, while Red, Green, and Yellow produce a one-second WRONG COLOR / USE BLUE DART hold without a result or throw consumption. Quick requires no retrieval between throws, Advanced may reuse the same dart after fresh removal/replacement, and a Throw 1 FOUL leaves every Blue dart available for Throw 2. The stale startup baseline, changed-coordinate freshness, normal/active deduplication, 20/30-second timing, and zero-reset policy remain intact.

The mapping is emulator evidence, not physical-board parity. Fixed DART 1 then DART 5 enforcement was removed without adding physics, scoring, multiplayer rotation, coordinate transforms, a secondary-display API, or physical assumptions.

## Phase 0S.2a — ROUND COMPLETE sticky-hold correction

**Status: IMPLEMENTED - ROUND COMPLETE HOLD RETEST READY**

The public runtime step now exposes an accepted setup only during `ACCEPTED_HOLD`; the retained diagnostic setup is not leaked after the transition to `ROUND_COMPLETE`. Regression coverage completes all four accepted/FOUL combinations and verifies five further sticky hold steps preserve the framebuffer and exactly two results without input polling, clock reads, blocking resets, terminal progression, or exceptions. This is a post-round sticky-state correction, not a gameplay-rule, timing, rendering, physics, scoring, multiplayer, coordinate, or secondary-display change.

## Phase 0S.2b — straight-curve icon direction correction

**Status: IMPLEMENTED - UPWARD STRAIGHT ICON RETEST READY**

The STRAIGHT curve icon is now a compact vertical up-arrow whose tip points toward the pin deck. LEFT and RIGHT geometry, STR labeling, framebuffer dimensions, every display state, and all gameplay, timing, input, scoring, physics, multiplayer, coordinate, and secondary-screen behavior remain unchanged. This is a display-only icon correction.

### Phase 0S.3 — Advanced manual skill-stop setup

Advanced setup is deliberately manual: Curve waits indefinitely for A, then the
Power meter waits indefinitely for A while cycling through
`40, 50, 60, 70, 80, 90, 100, 90, 80, 70, 60, 50` in exact 0.200-second steps.
The input event timestamp selects the locked value, and THROW READY alone begins
the 30-second attempt timer. Emulator early-dart removal now synchronizes the
active baseline and resumes Curve or restarts Power at 40 without consuming a
bowling throw. This is emulator-only recovery, not physical-board parity. Pending dart-hit and button batches accumulated behind the recovery screen are discarded at removal before rearming, so setup resumes only from fresh input. No
trajectory, physics, pinfall, scoring integration, multiplayer rotation,
coordinate transform, secondary-display, or audio work is included.

**IMPLEMENTED - ADVANCED SKILL-STOP RETEST READY**

### Phase 0T: deterministic ball trajectory and post-throw animation

**Status: IMPLEMENTED - BALL TRAJECTORY RETEST READY**

The emulator now builds one immutable quadratic Bézier trajectory only after a legal dart, retains raw aim metadata, and applies a declared display-local clamp solely for its visible target. Curve determines bend and Power determines the exact clock-derived duration. BALL ROLL polls no input; the diagnostic MISS is committed at arrival, with the standing rack unchanged. Collision, pinfall, scoring, multiplayer rotation, audio, physical calibration, and secondary-screen work remain future phases.

## IMPLEMENTED - PINFALL RETEST READY

Phase 0U adds deterministic emulator-only swept ball-to-pin collision and pinfall. The ball path is divided into exactly 256 quadratic Bézier subdivisions and tested against standing pins with a 6-pixel ball/pin contact radius. Pin centers and child links are owned by `throw_a_strike.domain.pinfall` and are reused by rendering.

Pinfall uses an authored deterministic energy graph: initial energy is `power_percent // 10`; CENTER sends through left/right costs 3/3, LEFT uses 2/4, and RIGHT uses 4/2. Propagation is breadth-first, never random, and missing/down pins do not receive or transmit energy.

Pinfall animation lasts 0.750 seconds, waves begin every 0.120 seconds, and each pin fall lasts 0.300 seconds. Survivor racks persist into Throw 2; a first-throw rack clear completes the diagnostic round early while preserving the existing Throw 2 progression convention. This phase intentionally adds no scoring, multiplayer rotation, audio, physical calibration, physical `DartsnutInputPort` changes, or secondary-display work.

## Phase 0V Status

IMPLEMENTED - SINGLE-PLAYER 10-PIN RETEST READY

- Added a one-player Blue-only regulation 10-Pin emulator runtime backed by the existing `GameSession`, `BowlingMatch`, and `BowlingGame` scoring path.
- Added a ten-pin scoring HUD and game-over renderer for the Regular emulator theme.
- Preserved the two-throw diagnostic emulator runtime for regression testing.
- Scope remains locked: no multiplayer, additional modes, audio, calibration, physical input changes, or secondary display features were added.

## Phase 0W - Regulation event presentation foundation

- Added a deterministic, hardware-independent regulation presentation timeline for single-player ten-pin events.
- `THROW_READY` is modeled as a one-shot 1.5-second logical cue that is cancelled by legal throws, Back transitions, result submission, foul, and game-over transitions.
- Result callouts are derived from the existing `GameSession`/`BowlingGame` snapshots and pinfall result kind, preserving the existing scoring source.
- Physical Screen 2 integration remains a later adapter task; this phase exposes pure event/view-model and RGB888 rendering boundaries only.

### Phase 0X secondary display emulator preview

Status: implemented on feature branch. A memory-backed `MemorySecondaryDisplayPort` and emulator-only `EmulatorSecondaryDisplayPort` now provide a Screen 2 preview surface fed exclusively by the existing `RegulationPresentationTimeline` view model and existing regulation RGB888 event renderer. The normal ten-pin runtime preserves Screen 1 frame submission and optionally mirrors Screen 2 event frames to the preview port.

A developer-only event gallery is available with `python main.py --event-gallery` or `python -m throw_a_strike.runtime.secondary_display_gallery`. It renders every supported regulation presentation label without mutating scoring/session state and remains headless-test friendly through the memory adapter. No physical secondary-display SDK assumption or physical Dartsnut adapter change is part of this phase.

Phase 0X review follow-up: normal gameplay now passes no secondary adapter unless `--screen2-window` is requested. Screen 2 framebuffer storage is bounded by default, visible pygame previews pump events and close deterministically, and the visible gallery advances through each regulation label for a readable hold while the headless gallery remains instantaneous for tests.

### Pin impact arcade transfer model follow-up

Status: implemented on feature branch. Pinfall now uses a deterministic authored transfer graph instead of the earlier fixed child-cost wave. Contact is categorized through centralized arcade bands (`left_contact`, `near_left_pocket`, `center_contact`, `near_right_pocket`, `right_contact`) and transfer energy is derived from direct pin, contact side, incoming direction, curve strength, power, and currently standing rack. The 60-80% green zone is meaningful without being automatic: 70% center/near-center is strike-capable, 60% remains weaker, and 80% broadens imperfect-contact propagation. Partial rear racks can transfer between adjacent survivors, while distant splits such as 7-10 remain difficult.

Phase 0X.1 review follow-up: Screen 1 THROW READY prompts are now static across ticks in the ten-pin and diagnostic renderers/runtimes. The emulator CLI now uses `parse_known_args()` so Dartsnut Agent-provided `--params`, `--shm`, and `--data-store` arguments remain compatible while local `--event-gallery` and `--screen2-window` options still work.

### Phase 0X.2 advanced lane arrows, Quick Play skill shots, and power risk

Implemented emulator-only tuning centralizes bullseye, pin-contact, split-recipe, lane-arrow, and ready-cue constants. Quick Play remains immediate: it starts at THROW READY, resolves to Straight, LaneArrow.CENTER, and 70% power, and dart placement alone supplies semantic strike/pin/contact intent. The localized bullseye strike zone is rounded around the dartboard center and no longer treats the whole center column as the same headpin shot.

Advanced Play now flows SET CURVE -> SET LANE ARROW -> SET POWER -> THROW READY -> dart. Five symmetric lane arrows use arcade start-X constants FAR_LEFT=36, LEFT=50, CENTER=64, RIGHT=78, FAR_RIGHT=92 while preserving BALL_START_Y. These constants are initial physical-board tuning values and should be adjusted centrally after cabinet testing.

Pinfall uses reusable deterministic trick-shot recipes for 7-10 green-zone kick conversions and Advanced-only 90-100% power-rebound conversions. Power is risk-shaped rather than higher-is-better: 70% is PERFECT, 60/80 GOOD, 90 POWER, 100 OVERDRIVE, and low power remains accurate but weak. Overpower can strike or convert with precise arrow/curve/contact but otherwise creates deterministic leaves without RNG or rigid-body physics.

Early darts during Advanced setup are non-blocking: the dart is marked stale, TOO SOON / REMOVE DART is transient, controls remain live, existing choices are preserved, and REARMED clears the stale dart before a new legal ready throw. Screen 1 THROW READY is a one-shot 1.5-second cue; the logical ready state continues to accept darts after it disappears. Future Party, Remix, 100-Pin, and other modes can reuse the centralized constants and recipe model, but those modes are not implemented by this phase.
### Phase 0X.3: dual-screen playtest integration

Status: implemented locally; cabinet validation required before merge. The game manifest and regulation runtime use the official 128×160 full-frame layout. Screen 1 remains a 128×128 dart-sensitive aiming/playfield surface. Screen 2 uses the lower-left 64×32 region for live score/status, simplified level-view ball roll and pin impact, result callouts, and final score. Advanced order is locked as SET AIM -> SET CURVE -> SET POWER -> THROW READY -> dart. This phase changes presentation and setup ordering only; it does not retune pinfall, scoring, collision, multiplayer, audio, or additional modes.
