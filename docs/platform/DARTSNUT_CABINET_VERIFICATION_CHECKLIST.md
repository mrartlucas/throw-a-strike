# Dartsnut cabinet verification checklist

Use one copy per cabinet/firmware combination. Preserve logs, photos, patterns,
and timing traces; do not translate dart indices into player colors on this
sheet unless separate authoritative mapping evidence is attached.

**Cabinet model:** __________________  **Firmware version:** __________________

**Tester:** __________________  **Date:** __________________

For **every** row complete:

- Actual observation: __________________
- Evidence file or photo: __________________
- Pass / fail: __________________

| Test ID | Prerequisite | Action | Expected observation (not a pre-filled hardware result) |
|---|---|---|---|
| DISP-01 solid-color framebuffer | Approved test harness and recoverable cabinet | Submit separate all-zero, red-component, green-component, blue-component, and all-maximum payloads | Record visible coverage, clipping, color, and acceptance; compare only with the submitted bytes. |
| DISP-02 channel-order pattern | Labeled RGB component pattern | Submit spatially separated component bands | Record actual band colors and establish channel order from evidence. |
| DISP-03 native-width pattern | Numbered one-pixel columns at candidate widths | Submit each approved candidate safely | Record the width that displays exactly once without crop/wrap; do not assume one. |
| DISP-04 native-height pattern | Numbered one-pixel rows at candidate heights | Submit each approved candidate safely | Record the height that displays exactly once without crop/wrap; do not assume one. |
| DISP-05 corner markers | Distinct labeled corner pixels/blocks | Submit markers after safe size is known | Record which physical corner shows each marker. |
| DART-01 x-axis orientation | Coordinate logger and labeled horizontal targets | Throw at left, center, right targets repeatedly | Record raw index/x/y and determine physical x-axis orientation statistically. |
| DART-02 y-axis orientation | Coordinate logger and labeled vertical targets | Throw at top, center, bottom targets repeatedly | Record raw index/x/y and determine physical y-axis orientation statistically. |
| DART-03 center coordinate | Marked physical center | Throw repeated center shots | Record distribution, error, and jitter; no perfect center is presumed. |
| DART-04 nine-zone dart test | Labeled 3×3 target overlay | Throw repeated shots in all nine zones | Record index and coordinate distributions for every zone. |
| DART-05 all twelve dart indices | Twelve individually labeled physical darts | Insert/throw each dart separately | Record every emitted slot index; record labels neutrally without guessing ownership. |
| DART-06 repeated insertion and removal | Logger with timestamps | Repeat insert/remove cycles for every dart | Record misses, duplicates, index changes, and invalid intervals. |
| DART-07 duplicate blocking | One labeled dart held active | Trigger once and keep it present while polling | Record whether and when duplicate events occur. |
| DART-08 re-arm timing | Timestamped coordinate/event logger | Remove for varied intervals around package defaults, then reinsert | Measure the actual minimum invalid interval for a new event. |
| DART-09 simultaneous darts | Two or more labeled darts and synchronized operators | Activate combinations simultaneously | Record all events, order, loss, latency, and repeatability under load. |
| BTN-01 every named button | Button logger | Press/release A, B, Up, Right, Left, Down, Home, and Reserved separately | Record exact keys, edges, latency, and physical labels. |
| BTN-02 button debounce | Timestamped logger | Tap/bounce each safe ordinary button at varied intervals | Measure suppression and repeat behavior. |
| BTN-03 Home behavior | Operator-approved recoverable session | Exercise Home in every relevant lifecycle state | Record launcher/process behavior and data/frame consequences. |
| BTN-04 Reserved behavior | Written operator authorization | Exercise Reserved in a controlled session | Record behavior; stop if platform safety guidance requires it. |
| BRIGHT-01 brightness minimum and maximum | Approved luminance procedure | Submit 10 and 100, plus authorized boundary probes | Record acceptance, measured output, persistence, and safety behavior. |
| DISP-06 display busy behavior | Harness that observes every return/status | Submit while consumer is busy | Record return, blocking duration, accepted frame, and recovery. |
| PERF-01 update-rate test | Frame IDs and timestamp capture | Ramp rates within approved safety limits | Record accepted/dropped frames, latency, CPU, temperature, and stable ceiling. |
| LIFE-01 process shutdown | Recoverable launcher session | Send approved shutdown/SIGINT and normal launcher exit | Record `running`, cleanup, process status, display, and relaunch behavior. |
| STORE-01 data-store persistence | Isolated disposable key namespace | Write values; restart process/cabinet; read; test approved corruption/reset cases | Record scope, retention, quota/error behavior, and recovered values. |
| SEC-01 secondary-screen discovery | Platform docs, launcher logs, all cabinet screens visible | Run the package harness and inspect documented IPC/configuration | Record APIs, ownership, dimensions, lifecycle, or confirmed absence only for this setup. |
| AUDIO-01 audio discovery | Approved silent/low-level sample and operator | Enumerate documented route and play safely | Record device, format, latency, focus, level, and failure behavior. |
| EMU-01 emulator comparison | Versioned emulator and matching cabinet evidence | Repeat display/input/lifecycle/store cases | Record every parity and divergence with emulator version. |

## Per-test sign-off (copy for each row)

**Test ID:** __________________  **Cabinet model:** __________________

**Firmware version:** __________________  **Tester and date:** __________________

**Actual observation:** __________________

**Evidence file or photo:** __________________

**Pass / fail:** __________________
