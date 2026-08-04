# Dartsnut 1.2.1 package platform contract

## 1. Scope

This spike records what can be established by static inspection of the locked SDK
artifact. It is a **package contract**, not a statement that cabinet hardware,
firmware, the launcher, or an emulator behaves identically. No package code was
executed and no hardware was accessed (E001–E025).

## 2. Exact inspected artifact

The artifact is `pydartsnut-1.2.1-py3-none-any.whl`, version 1.2.1, SHA-256
`a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f`, size
12,897 bytes. Its METADATA identifies `pydartsnut`, requires Python `>=3.1`, and
the lock records sdist SHA-256
`f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e`
(E001).

## 3. Evidence policy

`VERIFIED_PACKAGE_SOURCE` means an AST/source pointer into that exact wheel;
`VERIFIED_PACKAGE_METADATA` means its METADATA/RECORD; and
`VERIFIED_REPOSITORY_USAGE` describes this repository only. Search absence is
`NOT_FOUND_IN_INSPECTED_PACKAGE`. Cabinet-dependent questions remain
`UNKNOWN_HARDWARE`; disagreements are `CONTRADICTION`. The JSON is normative.

## 4. Executive findings

The wheel exposes `pydartsnut.Dartsnut` (E011). It implements one main-frame
submission method (E015), neutral dart and button APIs (E017–E018, E022–E025),
running/SIGINT state (E012, E014), brightness (E019), and JSON persistence
(E020–E021). It does **not** encode a framebuffer width, height, or byte length
(E015). Therefore neither 128×128 nor the repository's 128×160 is selected.

## 5. Package API inventory

The public surface found is `remove_shm_from_resource_tracker`,
`sigint_handler`, `update_frame_buffer`, `close`, `get_darts`, `get_buttons`,
`set_brightness`, `set_value`, `get_value`, `get_dart_hits`,
`get_active_darts`, `reset_blocking_state`, and `get_button_events`
(E013–E025). Construction is `Dartsnut()` but parses `--params`, `--shm`,
`--data-store`, `--min-active-duration`, and `--idle-unblock-duration`; defaults
are `{}`, `pdishm`, `None`, `None`, and `None` respectively (E012).

## 6. Main-display contract

`update_frame_buffer(frame)` accepts a `bytearray` or calls `tobytes()` on an
object, with no image conversion or length validation. Package prose calls the
bytes RGB888. Status 2 returns `False`; status 1 copies the payload after the
status byte, changes status to 0, posts the render semaphore, and returns
`True`; other status values return `False` (E015). Width, height, stride, safe
payload length, physical channel order, update rate, and dropped-frame policy
are not proven.

## 7. Dart input contract

`get_darts()` returns 12 `[x, y]` slots, maps valid raw axes to integers 0–127,
and uses `[-1, -1]` for the raw invalid sentinel (E017). Event and active APIs
return lists of `(dart_index, x, y)` tuples, with indices 0–11 (E022–E023).
Event handling also treats `[0, 0]` as invalid, blocks an index after emission,
and by implementation re-arms after 0.2 continuous seconds invalid; all valid
slots are examined in index order (E005–E010). This is not a player-color map
or a guarantee of physical orientation, stability, or loaded simultaneity.

## 8. Button input contract

Polling defines exactly `btn_a`, `btn_b`, `btn_up`, `btn_right`, `btn_left`,
`btn_down`, `btn_home`, and `btn_reserved`, returning debounced current boolean
states with a 0.03-second implementation delay (E018). Events are rising-edge
booleans over the polling keys (E009, E025). Names do not prove physical
placement or intended game controls.

## 9. Lifecycle contract

Construction installs SIGINT handling, sets `running=True`, connects named
display and input shared memory, opens a render semaphore, creates the store
directory, and builds an input handler; missing memory exits with status 1
(E012). SIGINT sets `running=False` (E014). `close()` releases the semaphore and
the destructor invokes it (E016). Launcher lifecycle and loop frequency remain
unknown.

## 10. Brightness contract

`set_brightness(brightness)` writes values 10 through 100 inclusive to the
input buffer, silently ignores other values, and has no explicit return value
(E019). Its physical luminance and safety effects are unknown.

## 11. Widget-parameter contract

`widget_params` is `json.loads()` of the `--params` string, default `{}`;
invalid JSON is printed and terminates with status 1 (E012).

## 12. Persistence contract

The optional `--data-store` directory otherwise defaults to the package source
directory (cwd only if `__file__` is unavailable), and the file is `data.json`
(E012). `set_value(key, value)` loads JSON, treats read corruption as an empty
mapping, writes an indented `.tmp`, and uses `os.replace`; write failures clean
up and raise `IOError` (E020). `get_value(key, default=None)` returns the default
for a missing file/key or read/JSON failure (E021). Quota, retention, isolation,
and filesystem-level atomic guarantees are outside the wheel.

## 13. Secondary-display search

The exact source, identifiers, strings, public methods/classes, and embedded
description were searched for `secondary`, `second_display`, `scoreboard`,
`control_screen`, `touch_screen`, `auxiliary`, `aux_display`, `lcd`,
`dual_display`, and `widget_display` (E001–E025).

**No secondary-display API was found in the inspected pydartsnut 1.2.1 wheel.**

**This does not prove that the Dartsnut launcher, cabinet platform, another
package, or a private API lacks secondary-display support.**

## 14. Repository assumptions

`main.py` imports `Dartsnut`, creates 128×160 surfaces, polls button events and
dart hits, unpacks hits as index/x/y, observes `engine.running`, uses six named
buttons, and submits its display through the package method. `conf.json`
declares `[128, 160]`. Before this phase the project dependency was
unconstrained while the lock selected 1.2.1. These are
`VERIFIED_REPOSITORY_USAGE`, not cabinet facts.

## 15. Contradictions

- **C001:** `main.py` assumes 128×160 while the implementation encodes no
  dimensions (and describes dart coordinates as 0–127). Native size and safe
  payload length remain unresolved.
- **C002:** `conf.json` declares 128×160 while the package encodes no display
  dimensions. Launcher schema and cabinet patterns are required.
- **C003:** `get_dart_hits` prose says 0.5 seconds, but the handler implements a
  0.2-second default (E022, E005–E007). No preference resolves final policy.

The inspected metadata supplies descriptive examples but no contrary
framebuffer implementation; public examples are secondary evidence and cannot
override E015.

## 16. Unknown hardware behavior

Blocking unknowns are: U001 physical display size; U002 channel order; U003
stride; U004 refresh limit; U005 safe rate; U006 dropped frames; U007 axis
orientation; U008 calibration; U009 dead zones; U010 jitter; U011 real-load
simultaneity; U012 color mapping; U013 index stability; U014 wrong-dart policy;
U015 external secondary API; U019 emulator behavior; U020 packaging; U021
launcher lifecycle; U023 cabinet/firmware compatibility; and U024 performance
budgets. Also unresolved are U016 touch behavior, U017 button placement, U022
store quota/retention, and U018 cabinet audio routing.
Each JSON record identifies the proposed operator/document/emulator evidence
and whether adapter, rendering, or multiplayer work is blocked.

## 17. Safe implementation boundaries

Subject to the unresolved native-size conflict, exact-package facts are enough
to design a narrow injected SDK facade, validate only properties actually
proven for main submission, capture neutral raw dart/button values, observe
running state, and provide deterministic fakes (E015, E017–E025). No facade is
implemented here.

## 18. Blocked implementation work

Do not finalize native render size, build a secondary-screen adapter, map dart
indices to colors, choose a physical coordinate transform, decide multiplayer
wrong-dart/re-arm policy, set cabinet performance targets, integrate audio, or
define packaging/deployment until the relevant unknowns are resolved.

## 19. Unblocked implementation work

A following small phase may create a dependency-injected package facade around
the verified methods and deterministic fake SDK objects. It must preserve raw
values, contain no application loop, and avoid secondary display and gameplay
policy.

## 20. Evidence index

E001 is wheel METADATA. E002–E010 cover `EngineProtocol`/`InputHandler` and its
constructor, dart, button, and reset methods. E011–E025 cover `Dartsnut`, its
constructor, resource/lifecycle methods, framebuffer, dart/button, brightness,
and persistence methods. Exact archive paths, hashes, symbols, extraction
methods, and line ranges are in the committed JSON.

## 21. Reproduction instructions

```bash
rm -rf .contract_tmp && mkdir -p .contract_tmp
python -m pip download --no-deps --only-binary=:all: --dest .contract_tmp pydartsnut==1.2.1
sha256sum .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl
python tools/inspect_pydartsnut_wheel.py .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl \
  --expected-sha256 a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f \
  --output docs/platform/evidence/pydartsnut-1.2.1-contract.json
python tools/inspect_pydartsnut_wheel.py .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl \
  --expected-sha256 a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f \
  --check docs/platform/evidence/pydartsnut-1.2.1-contract.json
```
