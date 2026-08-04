# Throw a Strike — Project Audit

## Audit scope and evidence

This is an investigation of repository commit `270905d` and the locally locked dependency set. The repository contains only `main.py`, `conf.json`, `pyproject.toml`, `uv.lock`, `README.md`, and a tracked Python bytecode file; it contains **no asset files, tests, examples, `.dartsnut` file, or `.dartsnut` directory**. The two commits only establish the README and import the original bowling game, so history supplies no additional design or hardware contract.

Hardware findings below distinguish facts demonstrated by this project and the source/metadata of the locked `pydartsnut==1.2.1` wheel from assumptions. “Verified” means verified in those sources, not verified on a physical cabinet.

## 1. Current architecture

### Structure and ownership

The entire game is one `main()` function. Constants, mutable session state, nested physics/scoring helpers, input polling, state transitions, rendering, and hardware submission all live in `main.py`. There are no domain models, mode abstractions, player records, test seams, or asset-loading services. `conf.json` declares a game called Bowling at size `128 × 160`; `pyproject.toml` requires Python 3.11+, Pygame, NumPy, and unconstrained `pydartsnut` (resolved to 1.2.1 in `uv.lock`).

### Game states and transitions

| State | Entry and behavior | Exit |
|---|---|---|
| `TITLE` | Initial/reset state; still renders a lane and HUD behind the “NEON BOWL” overlay. | A press or any dart hit resets a one-player ten-frame game and enters `AIM_POS`. |
| `AIM_POS` | Left/right moves the launch position from x=25 through 103 in three-pixel steps. | A enters `AIM_ANGLE`; a dart immediately starts `ROLLING`. |
| `AIM_ANGLE` | A frame-rate-dependent sweeper moves between -18° and +18°. | A locks the angle and starts `ROLLING`; a dart bypasses the sweep and starts a coordinate-derived roll. |
| `ROLLING` | Moves the ball, permits left/right steering, detects gutters and pin contacts, then computes knocked pins. | When ball y < 30, enters `RESULT` for 50 loop iterations. |
| `RESULT` | Displays result text. A or a dart skips the remaining timer. | Routes to another throw, next frame, or `GAME_OVER`. |
| `GAME_OVER` | Displays only a single final score. | A or a dart returns to `TITLE`. |

B, up, and down are read but unused. Home and reserved are not read by the game. There are no menu, player-count, mode, frame-count, theme, pause, or confirmation states.

### Main update loop

The loop runs while both local `running` and `engine.running` are true, nominally at 30 FPS. Each iteration:

1. drains only Pygame quit events;
2. polls Dartsnut button events and dart-hit events;
3. uses only the first simultaneous dart hit;
4. updates particles and shake lifetime;
5. updates the state machine and physics;
6. redraws the complete frame;
7. flips a local Pygame window;
8. converts the logical surface through `pygame.surfarray.array3d`, transposes it with NumPy, and calls `engine.update_frame_buffer()`; and
9. limits the loop to 30 FPS.

Movement, the aiming sweep, result duration, particle motion, steering increments, and shake decay are per-frame rather than delta-time based. The return value from `update_frame_buffer()` is ignored.

### Rendering flow

The logical surface and desktop display are both 128 × 160. Every frame is drawn procedurally: an 18-pixel top HUD, a perspective lane rendered to a newly allocated 128 × 110 surface, and a 32-pixel bottom instruction/result panel. Pins are two-pixel circles with one-pixel stripes. The ball scales from radius six near the player to two near the pins. Particles and random whole-lane shake represent impact. The complete 128 × 160 RGB frame is submitted to Dartsnut after a desktop flip.

There is no secondary renderer, scoreboard grid, responsive layout, sprite/image/font asset, animation timeline, dirty-region strategy, accessibility treatment, or theme abstraction. The view is strongly perspective-based but pins occupy only x=52–76 and y=36–48, making them extremely small rather than “large and readable.”

### Input flow

`get_button_events()` supplies rising-edge boolean values. A advances/locks/skips; left/right move or steer depending on state. Dart hits are expected as `(dart_index, x, y)`. Any hit starts a game from the title. During either aim state, only x is used: it is clamped to 25–103 and mapped into an angle based on distance from center. The received y and dart identity are discarded. During rolling, result, and game-over, darts do not control the ball (apart from skipping a result or resetting at game over).

Consequently a physical throw does not express two-dimensional aim, speed, trajectory, or object choice, and hits arriving while the ball rolls are silently consumed by the SDK’s blocking behavior. Keyboard input is not implemented; local desktop testing requires Dartsnut shared memory and its input producer.

### Existing bowling mechanics

Ten standing booleans represent a standard triangular rack at fixed screen positions. A ball begins at `(x, 120)`, travels upward at `vy=-3.5`, and receives an initial horizontal velocity from button timing or dart x. Left/right can alter `vx` by 0.15 on each button event. Perspective gutter bounds narrow toward the pin deck; crossing a bound permanently gutters the ball for that throw.

Direct ball/pin collision is a circle-distance test. A directly hit pin is removed, creates eight particles, and starts a breadth-first cascade. Only pins 1–6 have downstream rules. Each eligible left/right child falls randomly with a velocity-biased probability clamped to 20–95%. Pins cannot collide laterally, bounce, rotate, or transfer measured momentum. The ball passes through all pins along its path and can directly contact multiple pins in successive frames.

The game keeps remaining pins for a normal second throw and resets the rack at normal frame boundaries. In the tenth, it attempts to reset after a strike or spare.

### Current scoring behavior

`frame_rolls` stores the current frame and `all_rolls` stores completed frames. The scoring function flattens all supplied rolls, marks unresolved strike/spare cumulative scores as `None`, and returns a total containing only resolved frames plus open frames. Frames 1–9 use the usual two-following-roll strike bonus and one-following-roll spare bonus in principle; frame 10 is simply the sum of its allowed throws.

However, the displayed “SCORE” can temporarily omit a pending frame rather than clearly show it as pending. There is no per-frame scorecard. Roll legality is not validated independently from mutable pin state, and flawed tenth-frame pin reset/counting can produce invalid or negative roll values, making otherwise reasonable score arithmetic unreliable.

### Animation and collision behavior

Animation is limited to linear ball translation, blinking aim arrows/title prompt, eight short-lived particles per fallen pin, and six frames of random screen shake. Pins disappear immediately; they do not visibly topple or trigger a time-ordered chain reaction. Collision and movement use discrete frames, so tunneling is possible. Random cascade decisions occur immediately within one update, not over an animation. There is no audio.

## 2. Dartsnut hardware integration

### Capability matrix

| Capability | Status | Evidence and exact known contract | What remains |
|---|---|---|---|
| Dart-event payload | **VERIFIED** | In pydartsnut 1.2.1, `get_dart_hits()` returns `list[tuple[int,int,int]]`; each tuple is `(dart_index, x, y)`. Index is 0–11. Raw polling returns exactly 12 `[x,y]` entries. Invalid positions are `[-1,-1]`; the input handler also treats `[0,0]` as invalid for event generation. A hit blocks that index until an invalid interval (source default 0.2 seconds, despite stale 0.5-second method/README wording). | Confirm actual firmware/input producer observes the same invalid-state timing on hardware. |
| Dart coordinate system | **VERIFIED** | SDK maps each hardware axis from approximately 1800–39800 to integer 0–127; low/high values clamp to 0/127. Both axes are board/display coordinates. | Establish physical orientation (which cabinet edge is x=0/y=0), calibration, precision/noise, and whether `(0,0)` can be a legitimate corner hit; use a labeled 3×3 physical throw test. |
| Dart identity | **PARTIALLY VERIFIED** | The event exposes one of 12 slot indices, stable enough for SDK-level blocking. No package source defines ownership/color semantics for those indices. | Obtain official dart-index/color/player mapping documentation or a maintained multiplayer sample; otherwise log each physical Blue/Red/Green/Yellow dart set on a cabinet and repeat after restart/reconnection. |
| Blue mapping | **UNRESOLVED** | No repository or pydartsnut mapping exists. | Required evidence: official multiplayer example/package docs or physical labeled-dart test identifying its index/indices. Do not infer Blue from index 0. |
| Red mapping | **UNRESOLVED** | No repository or pydartsnut mapping exists. | Same evidence; do not infer Red from index 1. |
| Green mapping | **UNRESOLVED** | No repository or pydartsnut mapping exists. | Same evidence; do not infer Green from index 2. |
| Yellow mapping | **UNRESOLVED** | No repository or pydartsnut mapping exists. | Same evidence; do not infer Yellow from index 3. |
| Main display dimensions/API | **VERIFIED_EMULATOR_OBSERVATION** | A recorded emulator run visibly confirms a 128×128 main gameplay canvas. Separately, package evidence shows that `update_frame_buffer(frame)` accepts `bytearray` or an object with `tobytes()`, returns boolean acceptance, and performs no dimension or byte-length validation; this project/conf still declares 128×160. | Treat 128×128 as the main renderer candidate target. Physical-cabinet parity, RGB order/orientation, stride, clipping, safe payload length, and backpressure behavior still require verification. |
| Secondary display dimensions/API | **VERIFIED_EMULATOR_OBSERVATION** | The same recorded emulator run visibly confirms that the emulator exposes a second/control canvas at 64×32. Neither this repository nor pydartsnut 1.2.1 identifies a supported submission API for it. | Treat 64×32 as the secondary renderer candidate target only. Obtain the supported API or platform data contract, format, ownership, lifecycle, and physical-cabinet parity before implementing secondary output. |
| Buttons/control input | **VERIFIED** | Polling and rising-edge APIs expose `btn_a`, `btn_b`, `btn_up`, `btn_right`, `btn_left`, `btn_down`, `btn_home`, and `btn_reserved`; polling has a 30 ms debounce. | **UNRESOLVED** which buttons exist/are labeled on each physical cabinet and whether a separate touch/control screen emits another API. Verify with platform docs and a cabinet input trace. |
| Audio | **UNRESOLVED** | Pygame can load/play audio on ordinary hosts, but pydartsnut has no audio method and the repository has no audio files or cabinet routing/format/volume documentation. | Obtain official cabinet audio guidance and a known-good sample; verify mixer initialization, channels, supported formats, latency, output level, and platform focus/mute behavior physically. |
| Assets | **PARTIALLY VERIFIED** | The current game needs no external assets because all visuals use Pygame primitives and the default bundled font. Pygame can load assets, but Dartsnut packaging rules are absent. `conf.json` has an empty preview string. | Obtain manifest/package specification: allowed paths/formats, case sensitivity, archive/size/memory limits, preview dimensions, licensing expectations, and runtime working directory. |
| Persistent/high-score storage | **VERIFIED** | SDK provides atomic JSON-serializable `set_value(key,value)` and `get_value(key,default)` backed by `data.json`; launcher may supply `--data-store`. | Retention scope, quota, permissions, per-game isolation, migration/backup behavior, and whether competitive high scores require platform services are **UNRESOLVED** and need official documentation/hardware validation. |
| Emulator testing | **UNRESOLVED** | SDK requires existing display shared memory (`pdishm` by default), input shared memory (`pdoshm`), and uses `/pdishm_render_ready`. No emulator executable, setup document, `.dartsnut` configuration, or sample producer is included. A plain `python main.py` cannot initialize without that host. | Obtain official emulator distribution/version and launch guide, shared-memory host, input injection procedure, log access, manifest installation flow, and multiplayer/secondary-display simulation. |
| Physical-machine testing | **UNRESOLVED** | The shared-memory design shows the game is intended to be launched by a Dartsnut host, but repository/package docs do not describe deployment or certification. | Obtain supported cabinet/firmware matrix, developer install/signing workflow, recovery/rollback process, diagnostics, and an allocated test cabinet. Execute display, input/color, audio, persistence, thermal/performance, and long-session tests described in the implementation plan. |

### SDK lifecycle and integration notes

`Dartsnut()` parses process arguments, exits if either shared-memory segment is absent, sets `running=False` on SIGINT, and accepts timing overrides `--min-active-duration` and `--idle-unblock-duration`. Its framebuffer is a producer/consumer protocol: status 1 accepts a frame, status 2 is busy, and other statuses reject it. The current game neither closes the engine explicitly nor responds to a dropped frame.

The dependency is not bounded in `pyproject.toml`, even though `uv.lock` currently resolves 1.2.1. Development must treat the lockfile version as the audited contract or deliberately pin/upgrade after reviewing changes. The package metadata links a source repository, but no SDK tests/examples are vendored here.

## 3. Current limitations and defects

### Regulation scoring and tenth-frame defects

1. **Tenth-frame strike followed by a non-strike corrupts the third throw.** After a first strike the rack resets. If throw two knocks fewer than ten, the code does not reset (correct), but its throw-three count uses `(10 - sum(frame_rolls) % 10) - standing_now`; for `[10, 4]` with six standing this becomes `6 - standing_now`, reporting zero even if the third throw knocks pins. The base should be the standing count before that throw.
2. **Two tenth-frame strikes can yield a negative third throw.** After `[10,10]`, the rack resets. The condition `sum(frame_rolls) in (10,20)` initially happens to count from ten, but after the third roll the general design has no legality guard; adjacent reset/count branches are fragile and not modeled as explicit rack state.
3. **Tenth-frame feedback mislabels bonus strikes.** “STRIKE!” is restricted to the first roll; strikes on bonus throws become “10 PINS.” A second-roll 10 after a first strike can also satisfy the spare message check because the sum is 20 only avoiding equality by accident, rather than semantic roll context.
4. **Scoring accepts invalid frame arrays.** No pure validator enforces frames 1–9, tenth-frame bonus eligibility, maximum pins against a standing rack, or exactly ten completed frames.
5. **Pending bonuses make the total misleading.** An unresolved strike/spare contributes nothing to displayed total, with no pending marker or frame grid.
6. **No test coverage.** Perfect game (300), all spares (150), alternating patterns, consecutive strikes, tenth-frame `X X X`, `X 7 /`, `X 7 2`, `7 / X`, and gutter/open cases are unverified.

### Gameplay and multiplayer limitations

- There is exactly one player, one hard-coded ten-frame mode, one ball, one rack, and one final total. No turn rotation, player colors, equal per-frame shared sequences, standings, ties, winner presentation, or per-player rack reset exists.
- A dart’s identity is discarded, so the game cannot enforce the current player’s dart color even after mapping becomes known.
- The dart y coordinate is discarded and x produces both launch position and a deterministic center-relative angle; physical accuracy has limited influence. Button steering during travel further divorces the result from the initial throw.
- Random cascades with a minimum 20% and maximum 95% chance dominate outcomes, so identical accurate inputs can score differently. Random particles/shake are cosmetic, but pin randomness is competitive.
- Only the first hit in a batch is processed; remaining hits are lost. Throws during non-input states may be consumed/block the dart before the next turn.
- The result delay is skippable by any dart, potentially consuming a real player throw as UI input.

### Layout and presentation problems

- The main screen mixes score, instructions, results, and gameplay despite the planned separation to a secondary scoreboard.
- Ten pins occupy roughly 24×12 pixels and are only a few pixels each; this violates the required large, readable, full formation emphasis and cannot visually support 100 distinct pins as-is.
- The lane consumes most vertical space while the pin deck is tiny, contrary to “minimal lane space.” Text is small, all caps, default-font, and not tested for cabinet viewing distance.
- The title and metadata still say Bowling/Neon Bowl/Dartsnut Team rather than the locked brand/title. The requested brand spelling must always remain “Throw A Way Games,” never combined.
- No regular/blacklight toggle, onboarding, menus, scorecard, standings, winner view, animation for fallen pins, or mode-specific visual language exists.
- The declared 128×160 layout conflicts with the SDK’s documented 128×128 example/coordinates; on hardware this could distort, crop, overrun the expected framebuffer payload, or fail entirely.

### Performance and maintainability risks

- New surfaces, every text glyph, a full surfarray, a NumPy transpose, and an RGB byte conversion occur every frame. At 128×160 this may be acceptable, but 100 animated pins, richer effects, a second screen, and audio could exceed cabinet CPU/frame budgets.
- Particle removal is quadratic (`remove` while iterating a copy); cascade uses `pop(0)`; collision checks every standing pin every rolling frame. These are small now but unsuitable assumptions for 100-pin/Party scenes.
- Discrete collision permits tunneling, and all timing depends on achieving 30 FPS. Hardware stalls change aim difficulty and animation duration.
- Framebuffer backpressure is ignored, so visual frames silently drop. There is no telemetry, exception boundary, graceful host/home behavior, deterministic RNG injection, profiling budget, or automated headless route.
- Nearly every variable is captured mutable local state in a 600+ line function. That prevents isolated scoring, turn-order, physics, display, and persistence tests.
- `ball_spin`, `ball_active`, `standing_before`, B/up/down input, and received hit y are unused or effectively dead, indicating incomplete mechanics.
- The tracked `__pycache__` artifact is platform/Python-specific and should eventually be removed, but it is untouched in this planning-only task.

### Blockers for real PixelDarts hardware

The following must not be guessed: actual main-display dimensions; secondary-display/control-screen contract; Blue/Red/Green/Yellow dart mapping; supported multiplayer launch/turn flow; physical coordinate orientation; audio routing; packaging/preview rules; and emulator/cabinet deployment. Until the first three are resolved, Phase 0 can build pure domain logic and abstract interfaces, but it cannot truthfully complete production display/input integration.

## Phase 0K exact-wheel evidence update

Static AST inspection records the exact `pydartsnut` 1.2.1 wheel
`pydartsnut-1.2.1-py3-none-any.whl` (SHA-256
`a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f`)
and its locked sdist (SHA-256
`f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e`).
`pyproject.toml` is pinned to `pydartsnut==1.2.1`; package, Pygame, NumPy,
wheel, and sdist resolutions remain unchanged in `uv.lock`.

The package main-frame method accepts a `bytearray` or an object exposing
`tobytes()`, describes RGB888, and returns boolean acceptance based on shared
status, but encodes no width, height, or byte-length validation. The repository
and manifest's 128×160 assumption therefore conflicts with the package's
0–127 coordinate descriptions and historical examples; neither size is
selected. Dart events are confirmed as lists of `(dart_index, x, y)` tuples
over 12 slots. Exact button keys are `btn_a`, `btn_b`, `btn_up`, `btn_right`,
`btn_left`, `btn_down`, `btn_home`, and `btn_reserved`. Physical player-color
meaning and coordinate orientation remain unresolved.

No secondary-display API was found in the inspected wheel. This is a scoped
package search result, not evidence that the launcher, cabinet, another package,
or a private API lacks secondary output. Evidence is committed at
`docs/platform/evidence/pydartsnut-1.2.1-contract.json`, interpretation at
`docs/platform/DARTSNUT_PLATFORM_CONTRACT.md`, reproduction tooling at
`tools/inspect_pydartsnut_wheel.py`, and cabinet follow-up at
`docs/platform/DARTSNUT_CABINET_VERIFICATION_CHECKLIST.md`.

The safe next boundary is a narrow dependency-injected SDK facade around only
verified raw methods and deterministic fakes. Native rendering dimensions,
physical transforms, player/color mapping, wrong-dart policy, secondary output,
audio, performance targets, and packaging remain blocked pending recorded
platform/cabinet evidence.

### Phase 0K evidence-integrity correction

The inspector now derives detailed contract values from exact AST/literal nodes
instead of populating known-wheel constants. Production mode rejects every
artifact unless its filename, package metadata, computed hash, and expected hash
all identify the canonical locked wheel. A separate internal synthetic mode is
used only by parser tests and marks its result noncanonical.

The evidence now contains 115 explicit claim records, including 114 verified
metadata/source claims, with precise evidence pointers; 24 hardware unknowns;
and 3 unresolved contradictions. Absent or ambiguous synthetic syntax produces
unknown fields. Secondary-display discovery now searches Python text and AST
symbols/functions/assignments/imports/string constants, METADATA headers and
description, RECORD paths, and every safely decoded small UTF-8 wheel file.

### Phase 0K final literal-integrity correction

Button dictionary-comprehension value nodes and temporary-path string constants
are now literal-evaluated directly. Duplicate constructor options and button
dictionaries are combined conservatively, and metadata/text-only secondary
matches are `UNKNOWN_HARDWARE` rather than package-source verification.

### Phase 0L narrow SDK facade record

Phase 0L adds a platform layer below the application ports. Its dependency-injected facade reads `running` and wraps exactly `get_dart_hits()`, `get_button_events()`, `reset_blocking_state()`, `update_frame_buffer(frame)`, `set_brightness(brightness)`, and `close()`. It neither imports nor constructs concrete `Dartsnut`, and it performs no shared-memory or cabinet access. Mutable raw responses are strictly validated and normalized to immutable neutral values; operational failures are chained once without retries. A deterministic SDK-shaped fake supports later adapter tests.

Phase 0L itself selects and validates no display dimensions and adds no dart-to-player/color mapping, physical coordinate transform, renderer, application loop, or secondary output. Phase 0K remains the package-source evidence reference; later emulator observations are recorded separately and do not alter its evidence JSON. The safe next boundary is Phase 0M: a neutral `InputPort` adapter with injected time and sequence generation that preserves raw dart indices, coordinates, and button IDs without assigning gameplay meaning.


### Emulator display observation after Phase 0L

**Evidence classification: VERIFIED_EMULATOR_OBSERVATION.** A recorded emulator run visibly confirms a **128×128 main gameplay display** and a **64×32 second/control display**. The deployment panel shown in the emulator screenshot was **not connected to the bound physical device** during this observation. These findings establish intended emulator canvas sizes only; they do not establish physical-cabinet parity.

Future rendering candidates may therefore target **128×128 for the main renderer** and **64×32 for the secondary renderer**. The observation does not identify a supported secondary-screen SDK submission API. It does not change the Phase 0K package-source evidence JSON, and it does not add dimensions, validation, rendering, or secondary-output behavior to `DartsnutSdkFacade`.

### Phase 0M neutral Dartsnut input adapter record

Phase 0M adds an adapter boundary from an exact dependency-injected
`DartsnutSdkFacade` and structurally valid injected `ClockPort` to the existing
runtime-checkable `InputPort`. Each explicit available poll reads darts exactly
once, then buttons exactly once, then reads one monotonic timestamp only when
the combined batch is nonempty. Its deterministic batch composition places all
darts before all buttons while preserving each source's order; this is not a
claim about physical cross-source event order.

The adapter assigns consecutive monotonic sequence values and commits its next
value only after every immutable `InputEvent` is successfully constructed.
Empty polls and failures do not advance it. Source reads remain
nontransactional: darts may already be consumed when button reading fails, and
both sources may be consumed when clock reading fails; there is no rollback,
replay, or reconstruction. Facade and clock errors propagate unchanged.

No automatic blocking reset, player/color mapping, coordinate transformation,
gameplay command interpretation/dispatch, loop, rendering, or hardware access
is introduced. The safe next boundary is Phase 0N: a pure emulator-targeted
immutable 128×128 framebuffer model and deterministic RGB888 byte encoder,
without SDK submission or physical-cabinet parity claims.

### Phase 0N pure throw-control record

Phase 0N adds match-level Quick Play and Advanced Play control styles. `MatchConfig` schema version 2 serializes the selected style, defaults to Quick Play, and migrates exact schema version 1 payloads to Quick Play; all four modes accept both styles.

A pure one-attempt machine now models curve selection, a deterministic 0.150-second-step power meter, THROW READY, early-dart recovery, COMPLETE, and FOUL. The meter contains no randomness and 80 percent is only labelled PERFECT. Completed setups preserve raw dart index and x/y numbers without player/color mapping or coordinate transformation.

The boundary adds no scoring, pinfall, physics, rendering, framebuffer submission, hardware or platform access, global clock, runtime loop, or automatic blocking reset. The safe next boundary is a pure Phase 0O `InputEvent`-to-semantic-command interpreter that preserves event time and raw dart values; runtime integration remains later.

### Phase 0O pure throw-control input interpretation record

Phase 0O adds a pure application-layer interpreter. Exact raw `btn_left`, `btn_right`, `btn_a`, and `btn_b` controls map to `LEFT`, `RIGHT`, `CONFIRM`, and `BACK`; neutral dart hits map to semantic `DART_HIT`. Up, Down, Home, and Reserved controls are ignored, and neither `TICK` nor `REARMED` is generated. Exact timestamps, supplied stream order, repeated events, raw dart index, and x/y axis order are preserved. Sequence remains transport metadata: it is not copied, sorted, deduplicated, or validated by the semantic interpreter.

Coordinate handling recovers mathematically integral floats to integers only. It adds no rounding, clamping, scaling, swapping, inversion, calibration, or player/color mapping. The boundary performs no polling, clock access, machine mutation, automatic blocking reset, physics, pinfall, scoring, rendering, framebuffer submission, hardware access, or loop. The safe next boundary is a Phase 0P explicit-step coordinator with injected input and clock ports and one owned throw-control machine; direct hardware and continuous runtime behavior remain outside that phase.

### Phase 0P explicit-step throw-control coordinator record

**Status: IMPLEMENTED - LOCALLY VERIFIED.** Phase 0P adds a hardware-independent application coordinator that privately owns exactly one `ThrowControlMachine` for one attempt and advances it only through explicit `step()` calls. It accepts injected `InputPort` and `ClockPort` instances, polls exactly one finite batch per nonterminal step, reuses the Phase 0O interpreter once, and applies mapped commands in caller order. If input leaves the machine nonterminal, it reads the clock exactly once and applies one clock-derived `TICK`; terminal input completion skips the clock. A pre-poll terminal guard prevents later calls from consuming input intended for another attempt.

Each successful step returns an immutable complete record of events, interpreted commands, applied count, optional tick timestamp, and final snapshot. Operational errors identify polling, interpretation, input application, clock reading, or tick application and retain valid partial progress with their chained cause. The coordinator never retries, repolls, rereads, restores drained events, rolls back applied commands, or reconstructs its machine.

No `REARMED`, blocking reset, loop, sleep, global clock, hardware/adapter/platform access, physics, pinfall, scoring, rendering, framebuffer submission, secondary display, player mapping, color mapping, or coordinate transformation is introduced. The safe next boundary is Phase 0Q: a pure immutable display-neutral presentation model translating snapshots and step records into locked throw-control prompt, curve, power, feedback, and warning data without pixels, hardware, resets, physics, pinfall, or scoring.

### Phase 0Q pure throw-control presentation record

**Status: IMPLEMENTED - LOCALLY VERIFIED.** Phase 0Q adds a pure frozen presentation value for one attempt, built solely from an exact immutable throw-control snapshot. Its exact vocabulary is SET CURVE, SET POWER, THROW READY, TOO SOON, REMOVE DART, THROW NOW, FOUL, and 0 PINS. During warning, THROW READY remains primary and THROW NOW is secondary. Early-dart recovery displays TOO SOON plus REMOVE DART; terminal foul displays FOUL plus 0 PINS. COMPLETE has no prompt because a later animation/physics layer takes control.

The model assigns only semantic curve icon IDs: all three left levels use LEFT, Straight uses STRAIGHT, and all three right levels use RIGHT. It preserves the domain curve label and strength, displayed power percentage, feedback metadata, and locked-power state. The step-result builder uses only its snapshot; events, commands, and tick timestamp create no additional behavior.

This boundary adds no display dimensions, layout, coordinates, pixels, framebuffer, fonts, colors, renderer, hardware access, clock access, input polling, command generation, `TICK`, `REARMED`, blocking reset, machine/coordinator mutation, physics, pinfall, scoring, player/color mapping, coordinate transformation, or secondary-display submission API. The safe next boundary is Phase 0R, a finite Emulator Control Test Vertical Slice that renders and wires the established semantics through verified APIs, targets observed emulator dimensions without claiming cabinet parity, and documents rather than guesses any secondary-output limitation.

### Phase 0R interactive emulator control-test record

**Status: IMPLEMENTED - EMULATOR TEST READY.** The obsolete random prototype is replaced by a small entry point using the Phase 0Q architecture: `DartsnutInputPort`, one selected `ThrowControlCoordinator`, the pure presentation builder, and a pure RGB888 renderer. Control-style selection defaults/times out to Quick at 15 seconds; Left/Right select and A confirms. Quick begins ready at Straight/70, while Advanced exposes curve and moving power lock before readiness.

The observed emulator target is a 128×128, 49,152-byte main-only packed RGB888 frame with all ten pins above a compact prompt/curve/power/feedback/style HUD. This is an emulator observation and encoding assumption, not SDK dimension validation or physical-cabinet orientation/color/parity evidence. The observed 64×32 screen remains unresolved because no secondary API was found; none was invented.

Each active iteration performs one finite selection poll or coordinator step and one main submission. Warning retains THROW NOW at 30 seconds; 60 seconds shows FOUL and 0 PINS. COMPLETE retains accepted raw dart coordinates in the coordinator outcome but shows no ball or pin result. Early recovery intentionally holds cached TOO SOON/REMOVE DART without polling, clock access, hardware reset, or REARMED until app restart. Terminal frames likewise hold.

No trajectory, bowling-ball animation, collision, pin result, scoring, frame progression, multiplayer, player/color or dart-index mapping, coordinate transformation, audio, automatic reset, assets, or physical behavior claim is added.

### Phase 0R.1 dart rearm and FOUL-retry record

**Status: IMPLEMENTED - RETEST READY.** New emulator evidence showed that a physical dart was not accepted and the resulting FOUL held indefinitely. The runtime now invokes only the verified facade `reset_blocking_state()` operation after style selection is consumed and before each fresh coordinator and initial attempt framebuffer. Constructor and active-selection steps do not reset. Quick, Advanced, and the 15-second Quick timeout all use this same ordered boundary, and a reset failure prevents coordinator construction and propagates through runner cleanup.

FOUL now enters a distinct terminal-presentation `FOUL_HOLD`, retaining FOUL plus 0 PINS and its exact tick timestamp. For exactly 1.5 seconds it reads the injected clock once per step, polls no input, performs no reset, and republishes the cached frame. At the deadline it resets once, constructs one clean coordinator at the current timestamp in the already selected style, and submits one fresh attempt frame. Quick resumes at THROW READY/STR/70; Advanced resumes at SET CURVE/STR/70. Prior warning and FOUL outcome state are not carried forward.

COMPLETE remains the only `TERMINAL` phase and holds exact accepted raw dart index/x/y until restart without reset. EARLY_DART_RECOVERY remains the only `RECOVERY_HOLD` phase and still holds TOO SOON/REMOVE DART until restart without polling, clock access, reset, or `REARMED`. The verified final suite contains 474 tests, including 22 focused runtime tests.

This is emulator-based retest preparation, not physical-cabinet parity evidence. It adds no physics, pinfall, scoring, multiplayer, coordinate transformation, player mapping, secondary-display API, dart-removal API, or guessed orientation/color behavior.

### Phase 0R.2 visible acceptance and continuous-retest record

**Status: IMPLEMENTED - CONTINUOUS RETEST READY.** Every normally accepted dart now preserves the exact completed coordinator snapshot and `ThrowSetup`, displays DART ACCEPTED and unchanged raw D-index/X/Y, and enters `ACCEPTED_HOLD`. The diagnostic retains the pin deck and locked curve/power HUD but adds no ball, pinfall, or score.

The verified suite contains 477 tests, including 23 focused runtime tests and 10 focused RGB888 renderer tests.

For exactly 1.5 seconds the accepted hold reads the clock once per step, polls no input, performs no reset, and republishes its cached frame. At or after the deadline it resets blocking state once, constructs one clean coordinator at the current timestamp, preserves Quick or Advanced style, clears the old outcome, and submits one fresh initial attempt frame. FOUL retry and restart-only early recovery remain unchanged.

An emulator log containing “event fired” proves only emitted emulator input; “BLOCKED” may describe duplicate suppression pending reset. Physical testing requires the Deploy panel to say Connected. Local clicks, the unused second screen, and this runtime establish no physical-board parity. No physics, pinfall, scoring, player/color mapping, coordinate transformation, secondary-display API, or cabinet-parity claim was added.
