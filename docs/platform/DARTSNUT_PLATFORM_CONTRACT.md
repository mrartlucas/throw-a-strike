# Dartsnut 1.2.1 package platform contract

## 1. Scope

This is a static contract for one locked wheel, not a hardware, firmware,
launcher, or emulator contract. The inspector parses archive text and Python AST
without importing the package, executing its code, opening shared memory, or
accessing hardware.

## 2. Exact inspected artifact

The inspected artifact is `pydartsnut-1.2.1-py3-none-any.whl`, SHA-256
`a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f`,
with locked sdist SHA-256
`f3618dc311e77773f6e655b11cb448e94940c59af32ad060e77a9ed616583d8e`.
Its METADATA names `pydartsnut`, version `1.2.1`, and Python requirement `>=3.1`
(CLM-001, CLM-002, CLM-003; E001).

Production inspection requires that exact filename, computed wheel hash, and
caller-supplied expected hash. The internal synthetic mode is only a parser test
helper and its output is explicitly marked synthetic.

## 3. Evidence policy

Every extracted fact is a claim in the JSON. A `VERIFIED_PACKAGE_SOURCE` or
`VERIFIED_PACKAGE_METADATA` claim contains precise evidence IDs; each evidence
record identifies archive path, source SHA-256, symbol, syntax line range, and
specific extraction method. Missing or ambiguous values are `UNKNOWN`/`null`,
not copied from known-wheel expectations. Repository usage, public documents,
search absence, hardware unknowns, and contradictions use separate statuses.

## 4. Executive findings

The source-derived contract covers constructor options, framebuffer control
branches, neutral input values, brightness bounds, and persistence operations.
Width, height, channel count, byte length, stride, and physical channel order
remain unknown. Neither 128×128 nor 128×160 is selected.

## 5. Package API inventory

The AST found `Dartsnut.__init__`, render-semaphore helpers, resource-tracker
handling, `sigint_handler`, `update_frame_buffer`, `close`, `__del__`, dart and
button polling/event methods, brightness, and persistence methods. Their exact
signatures are claims CLM-012 through CLM-028, each backed by its own
`ast.FunctionDef` evidence rather than a range shorthand.

## 6. Main-display contract

`update_frame_buffer` has signature `(self, frame)` (CLM-017). Its source has an
`isinstance(..., bytearray)` branch and a `hasattr(..., "tobytes")` branch
(CLM-039, CLM-040). The docstring contains the wording `RGB888` (CLM-048); this
proves package wording, not physical channel behavior or a separately encoded
channel count.

AST comparisons extract status literals 2 and 1 (CLM-042, CLM-043). Source
returns are `False`, `True`, and `False` at their respective precise return
nodes (CLM-045, CLM-046, CLM-047), the ready branch assigns status 0 (CLM-044),
and calls the render semaphore helper (CLM-041). No unambiguous width, height,
channel-count, or byte-length-validation claim was extracted; those fields are
unknown rather than inferred.

## 7. Dart input contract

Three independent `range(12)` call nodes establish the package's consistent
12-slot iteration (CLM-049, CLM-050, CLM-051). Event and active append nodes
construct three-element tuples (CLM-052, CLM-053). Mapping syntax contains raw
thresholds 1800 and 39800, output constant 127, and divisor 299
(CLM-066–CLM-077). These literals do not prove physical orientation or
calibration.

The invalid-state comparison explicitly contains `[-1, -1]` and `[0, 0]`
(CLM-078, CLM-079). Class assignments extract defaults 0.2 seconds idle before
unblock and 0.0 seconds minimum active duration (CLM-080, CLM-081). Precise call
nodes add, remove, and clear blocked indices (CLM-082–CLM-085). Package prose
instead mentions 0.5 seconds (CLM-115), producing contradiction C003.

**No player-color mapping is asserted.** **No physical coordinate orientation is asserted.** Index/color ownership, index stability, loaded simultaneous input,
wrong-dart behavior, and physical transforms remain unknown.

## 8. Button input contract

An exact `ast.Dict` contains `btn_a`, `btn_b`, `btn_up`, `btn_right`, `btn_left`,
`btn_down`, `btn_home`, and `btn_reserved` (CLM-086). The debounce assignment is
0.03 seconds (CLM-087). Exact literal evaluation of the event dictionary
comprehension's value node produces `False` (CLM-088); a nonliteral or
conflicting set of comprehension values would instead be unknown. Its loop
processes `(btn_name, button_pressed)` (CLM-089).
These names do not establish physical placement or intended game controls.

## 9. Lifecycle contract

Construction has signature `(self)` (CLM-012), assigns `running=True`
(CLM-037), and registers `signal.signal(signal.SIGINT, self.sigint_handler)`
(CLM-029). Signatures for `sigint_handler`, `close`, and `__del__` are extracted
(CLM-016, CLM-018, CLM-019). Detailed launcher lifecycle, process update-loop
requirements, and physical cleanup effects remain unknown where no dedicated
claim was extracted.

## 10. Brightness contract

The chained comparison extracts inclusive numeric bounds 10 and 100
(CLM-090), and an assignment writes the supplied value to
`self.shm_pdo_buf[49]` (CLM-091). The method contains no explicit `return`, so
its implicit return is `None` (CLM-092). Physical luminance and safety effects
remain unknown.

## 11. Widget-parameter contract

The `--params` option default is the string `{}` (CLM-030), and a precise call
node proves parsing with `json.loads` (CLM-035). Other invalid-input effects are
not promoted to verified detailed claims unless extracted in the JSON.

## 12. Persistence contract

Constructor syntax extracts `--data-store` default `None` (CLM-032), directory
creation with `os.makedirs` (CLM-036), and filename `data.json` from
`os.path.join` (CLM-038). Default-path source calls include `os.path.abspath`,
`os.path.dirname`, and `os.getcwd` (CLM-093–CLM-095), with precise exception
branches recorded in CLM-096–CLM-100.

`set_value`/`get_value` signatures are CLM-023 and CLM-024. Exact calls establish
`json.load`, `json.dump`, `os.replace`, existence checks, and cleanup removal
(CLM-101–CLM-112). The temporary suffix `.tmp` is extracted from the precise
string-constant node used by its assignment (CLM-113); a missing or conflicting
suffix literal would instead be unknown. These package operations do not establish cabinet quota, retention,
isolation, or filesystem guarantees.

## 13. Secondary-display search

For every required term, the inspector searches all Python source text; AST
class names, method names, module-level functions, assigned public names,
imported/exported names, and string constants; METADATA headers and METADATA
description body; RECORD paths; and all safely decodable small UTF-8 text files.
The JSON separately populates `matching_symbols`, `matching_source_locations`,
`public_api_candidates`, `metadata_matches`, `record_matches`, and
`text_file_matches` from actual results.

An empty complete search is `NOT_FOUND_IN_INSPECTED_PACKAGE`; a public source
candidate is `VERIFIED_PACKAGE_SOURCE`; prose/text matches without a public
source candidate are `UNKNOWN_HARDWARE`.

All result collections are empty for this wheel, so:

**No secondary-display API was found in the inspected pydartsnut 1.2.1 wheel.**
(CLM-114)

**This does not prove that the Dartsnut launcher, cabinet platform, another
package, or a private API lacks secondary-display support.**

## 14. Repository assumptions

`main.py` currently uses a 128×160 surface, neutral hit tuple unpacking, named
button events, `engine.running`, and the main framebuffer method; `conf.json`
declares `[128, 160]`. These are `VERIFIED_REPOSITORY_USAGE`, not package-source
or hardware claims, and neither file was changed.

## 15. Contradictions

- **C001:** the runtime's 128×160 assumption versus no extracted package width
  or height remains unresolved.
- **C002:** the manifest's `[128, 160]` versus no extracted package width or
  height remains unresolved.
- **C003:** package prose says 0.5-second re-arm (CLM-115) while the class default
  assignment is 0.2 seconds (CLM-080). No preference resolves final policy.

## 16. Unknown hardware behavior

U001–U024 in the JSON cover physical dimensions, channel order, stride, refresh
and drop behavior, orientation, calibration, dead zones, jitter, loaded
simultaneity, color mapping, index stability, wrong-dart policy, secondary and
touch APIs, button placement, audio, emulator, packaging, launcher lifecycle,
store retention, compatibility, and performance. Each record states why source
is insufficient, a verification method, and which work it blocks.

## 17. Safe implementation boundaries

A future narrow, injected SDK facade may wrap only claim-backed methods, retain
neutral raw dart/button values, observe running state, and use deterministic
fakes. Submission validation must not invent dimensions, channel count, or byte
length.

## 18. Blocked implementation work

Final render dimensions, secondary output, player-color mapping, physical
coordinate transforms, wrong-dart and final re-arm policy, audio, performance
targets, and packaging/deployment remain blocked.

## 19. Unblocked implementation work

Evidence maintenance, deterministic parser/fake tests, and a claim-limited SDK
facade design are unblocked. No adapter is implemented in this phase.

## 20. Evidence index

The committed JSON is the complete index: 115 claim records link to precise
metadata or syntax evidence. Detailed values cite `ast.Constant`, `ast.Compare`,
`ast.Dict`, `ast.For`, `ast.Return`, `ast.Call`, `ast.Assign`, or
`ast.get_docstring` nodes rather than whole-method pointers.

## 21. Reproduction instructions

```bash
rm -rf .contract_tmp && mkdir -p .contract_tmp
python -m pip download --no-deps --only-binary=:all: --dest .contract_tmp pydartsnut==1.2.1
python tools/inspect_pydartsnut_wheel.py \
  .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl \
  --expected-sha256 a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f \
  --output docs/platform/evidence/pydartsnut-1.2.1-contract.json
python tools/inspect_pydartsnut_wheel.py \
  .contract_tmp/pydartsnut-1.2.1-py3-none-any.whl \
  --expected-sha256 a207168cf36ba04352d3710933e159a1311948363be18c4bbd81ce4ae5916f4f \
  --check docs/platform/evidence/pydartsnut-1.2.1-contract.json
```
