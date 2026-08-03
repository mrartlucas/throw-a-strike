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
| Main display dimensions/API | **PARTIALLY VERIFIED** | `update_frame_buffer(frame)` accepts `bytearray` or an object with `tobytes()`, writes RGB888 bytes into shared memory when status byte is 1, returns `True`; it returns `False` when busy/invalid. Package example creates 128 × 128 imagery and darts map to 128 × 128. This project/conf instead declares and submits 128 × 160. The API does not validate dimensions or byte length before slice assignment. | Obtain the PixelDarts game manifest/display specification and emulator shared-memory buffer length for this hardware generation. Verify whether main output is 128×128 or 128×160 before further rendering work. Test exact RGB byte order, orientation, clipping, and busy-frame retry/drop behavior. |
| Secondary display dimensions/API | **UNRESOLVED** | Neither this repository nor pydartsnut 1.2.1 exposes a second framebuffer, control-display surface, or secondary-display dimensions. The `--shm` option selects one display shared-memory name; it does not document multiple displays. | Required: current official SDK/API documentation plus a working multiplayer game/sample that writes the secondary/control screen, including dimensions, pixel format, lifecycle, and launch arguments. If it is owned by the platform UI rather than the game, obtain the schema for publishing player/frame/score data. |
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
