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

- This phase is gated on secondary dimensions, API, ownership, pixel/data format, lifecycle, and emulator support.
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

## Risk register

| Risk | Likelihood / impact | Mitigation and trigger |
|---|---|---|
| Main display is 128×128 while project submits 128×160 | High / Critical | Resolve from official spec and framebuffer length before UI implementation; native hardware pattern test. |
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

1. What are the exact native width, height, RGB byte order, stride, maximum payload, refresh rate, and safe producer protocol of the main display? Is `conf.json`’s 128×160 valid despite the SDK’s 128×128 examples?
2. What official API or platform data contract addresses the secondary/control screen? What are its dimensions, format, lifecycle, refresh limit, launch arguments, and emulator support?
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
