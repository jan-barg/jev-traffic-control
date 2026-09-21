# Viewer validation — 21 September 2026

Verified in the Codex browser at its normal 947 px viewport:

- Completed benchmark and all four controller rows render from exported results.
- Morning and surge Jev replays load alongside the matching fixed-plan replay.
- Play resumes elapsed time; pause stops playback; seek selects a recorded time.
- Controller selection also loads the actuated and pressure comparisons.
- Clicking a right-hand signal shows its logged action, acceptance and observation age.
- WebMCP configuration accepts valid inputs; rejects an out-of-range time without changing state.
- No browser console errors were reported and page width did not overflow the viewport.
- Benchmark report and run-data links point to exported local assets.
- JavaScript syntax check passed; all eight compressed replay files parse successfully.

Visual inspection covered both animated maps, metric counters, the result callout and table. Mobile breakpoints were not exercised. Technical simulation validation is reported separately in BENCHMARK_RESULTS.md and results/validation.json.
