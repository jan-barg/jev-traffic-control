# Running and auditing Midtown Traffic Lab

The experiment is closed. For outcomes, start with the [results overview](../README.md). This guide preserves the setup, model and reproduction details. The browser replay needs no API key; new live Jev runs use the configured paid TypeSafe account.

## Run locally

Python 3.12 and a compatible SUMO wheel are required. This project was exercised on macOS arm64 with SUMO 1.27.1.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

For Jev, create a local `.env` containing `TYPESAFE_API_KEY=...`. The file is ignored by Git. Never put the key in browser code or a public artifact. `.env.example` lists the expected names. The integration pins `jev-1.13.0` by default.

The generated network is already included. To regenerate and retune the conventional plan:

```sh
.venv/bin/python -m trafficlab.tune
```

The development sweep evaluates 16 fixed plans on seeds 901 and 902. The selected plan has a 90-second cycle, 52 seconds of avenue green, 30 seconds of cross-street green, three-second yellow and one-second all-red intervals. Its offsets create a nominal 9 m/s avenue progression. The signed `progression_speed_mps` implementation parameter is -9 because SUMO's offset convention advances the program clock; it does not imply cars travel backwards.

Run a single conventional replication:

```sh
.venv/bin/python -m trafficlab.run --controller fixed --seed 11 --scenario am --warmup 180 --duration 600 --drain 180 --replay
```

Run the complete pilot benchmark:

```sh
.venv/bin/python -m trafficlab.benchmark --only conventional --parallel 3
.venv/bin/python -m trafficlab.benchmark --only jev --parallel 10
.venv/bin/python -m trafficlab.report
```

The Jev command makes paid API calls using the configured account. Ten independent real-time replications run concurrently for approximately 16 minutes. It does not accelerate their simulated clocks. The measured service latency includes this concurrent request load. Lower concurrency increases total elapsed time and can change provider latency. The conventional runs complete much faster; controller computation is still measured and rounded up to a simulation step before an action is applied.

Run the separate bounded extension after the original benchmark (the launcher refuses to overwrite existing bounded results):

```sh
.venv/bin/python -m trafficlab.benchmark_bounded --parallel 10
.venv/bin/python -m trafficlab.run_bounded --policy keep --seed 11 --scenario am --warmup 180 --duration 600 --drain 180 --tag bounded_keep_check --out-root tmp/bounded-validation
.venv/bin/python -m trafficlab.validate_bounded
.venv/bin/python -m trafficlab.report
```

The bounded benchmark also makes paid, real-time API calls and takes approximately 16 minutes at concurrency ten. The keep-only run is a deterministic regression check, without API calls. `bounded_protocol.json` freezes the new policy and all original result hashes before evaluation. The audit verifies the actual signal transitions, response arrival times and exact keep-only equivalence. Native Jev is neither rerun nor replaced by this command. For another experiment, retain the existing evidence and use a fresh checkout/output set rather than overwriting it.

## Coordinated plan selection

This experiment uses four arms: the original 52/30-second fixed plan, the best single plan from a development sweep, a numerical selector and Jev choosing from the same plan library. All retain 90-second cycles and the original coordination offsets. The new controllers change persistent green-split profiles across all twelve intersections; this version does not change offsets or cycle lengths.

Seven profiles were evaluated on six development demand patterns and seeds 901–902 (84 simulations). The five retained plans include the original reference, one winner per development pattern and the best static plan across the morning/surge/directional-shift mixture. The retuned fixed baseline is selected before evaluation so ordinary retiming is not credited to Jev.

Every 90 seconds, starting at second 60, the selectors receive current queues and occupancies, the last two minutes of arrivals and an approximate 180-second queue forecast for every candidate. Forecasts use observed vehicle positions and speeds and propagate traffic between finite-capacity links using recent boundary arrival rates, published turn shares and assumed discharge rates. The numerical arm minimizes forecast queue delay plus a terminal queue penalty; Jev evaluates the same candidates with a neutral prompt. Neither receives future departures, scenario labels or scheduled demand-change times.

The selected plan becomes eligible three seconds after observation and rolls into each intersection at its next local cycle start. This preserves coordination and clearance durations. Actual observation, forecast and API time are measured; Jev runs at 1x wall time, with a two-second request deadline and no retries. Late or failed requests retain the current plan. Numerical computation is also measured and delayed before acceptance. Installation waits affect both arms' traffic outcomes.

Evaluation uses fresh seeds 31–35, four arms and three scenarios (60 runs). The directional case is synthetic: baseline inflow for the first 200 evaluation seconds, then avenue inflow ×0.65 and cross-street inflow ×2.2 for 200 seconds, then avenue ×1.4 and cross street ×0.6. Morning and uniform surge remain in the benchmark. Compare Jev against both fixed plans and the numerical selector using paired intervals; improvement over the original reference alone does not isolate a Jev contribution.

From a fresh output set, after retaining the original evidence:

```sh
.venv/bin/python -m trafficlab.tune_plans
.venv/bin/python -m trafficlab.run_coordinated --controller fixed --seed 11 --drain 180 --tag plan_fixed_check --out-root tmp/plan-validation
.venv/bin/python -m trafficlab.benchmark_coordinated --only conventional --parallel 3
.venv/bin/python -m trafficlab.benchmark_coordinated --only jev --parallel 15
.venv/bin/python -m trafficlab.validate_coordinated
.venv/bin/python -m trafficlab.report_coordinated
```

Keep the host awake and its network connected throughout live runs. On macOS, prefix the live benchmark command with `caffeinate -diu`; leave the lid open. The first coordinated live batch was invalidated by host sleep and repeated in full with unchanged controllers. Its metrics, file hashes and execution evidence are retained in [the retry record](../results/coordinated_execution_retry.json).

The selected library and completed results are already included in this checkout. The tuning/benchmark commands refuse to overwrite them. The live command uses the configured paid TypeSafe account; fifteen staggered concurrent replications take about 16 minutes. Independent validation checks observed signal phases, cycle starts, per-intersection installation times, model-answer agreement, actual response timing, paired demand, conservation and the hashes of all fifty previous results. A fixed-only regression exactly reproduces the original runner.

`results/coordinated_protocol.json` freezes the experiment before evaluation. `results/coordinated_summary.json` and `coordinated_validation.json` contain results and audit evidence. The viewer exports these separately as `coordinated-summary.json`, `coordinated-runs.json` and `coordinated-report.md`, with preselected seed-31 trajectories. Raw forecasts, API responses, actions and signal-installation logs remain in `results/raw/plan_*/`.

Preview the exported viewer:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory viewer/dist
```

Open `http://127.0.0.1:8765`. Choose an experiment and demand scenario, select the comparison controller, pause/seek, change playback speed, or click a signal on the right-hand map to inspect its last applied decision. Playback consumes no API tokens. Representative replays were selected in advance: seed 11 for the original controllers and seed 31 for coordinated plans.

## Data and model

`data/midtown_am.json` contains 48 published turning volumes from Figure 13-6a of the Midtown South FEIS. All 16 internal links balance exactly. The resulting expected boundary demand is 4,165 vehicles/hour. The generator uses Poisson boundary arrivals and movement probabilities inferred from the published turns. Actual controller-dependent internal flows remain free to change. Identical seeds generate identical departures, routes, vehicle types and desired-speed factors across controllers.

The model assumes 80 m blocks, 260 m avenue spacing, three avenue lanes, one cross-street lane, 180 m boundary approaches, a 25 mph nominal speed cap, 5% trucks and otherwise passenger cars. Fixed routes may include loops because choices are sampled from local turning shares; this is not an observed origin/destination matrix. A route-length guard fails rather than silently truncating a very long route. SUMO handles car following, lane changes, junction movement and vehicle interactions. Driver noise during simulation is disabled; stochasticity is in the pre-generated traffic schedules and vehicle parameters, which are shared between arms.

The surge scenario raises boundary arrival rates by 50% in the middle half of the ten-minute evaluation window. It is a synthetic stress case based on the same turning shares, not a measured NYC incident.

Detailed data provenance and outstanding field-data gaps are in [the NYC audit](../docs/NYC_BENCHMARK_AUDIT.md).

## Controllers and latency

- **Tuned fixed-time:** an assumed coordinated plan selected using separate development seeds. It is not labeled actual NYC signal control.
- **Simple actuated:** after minimum green, switch when the opposing approach is queued and the active approach is empty or has been green for 40 seconds; maximum green still applies.
- **Queue pressure:** compare queued vehicles with turn-share-weighted downstream queues and one-vehicle hysteresis. This is a simple pressure heuristic, not a reproduction of every max-pressure algorithm.
- **Jev:** choose `hold` or `switch` from compact approach queues, approach vehicle counts, precomputed pressure, downstream storage estimates, current phase and phase age. Batch independent intersection questions; the model cannot see future departures.
- **Bounded Jev:** retain the fixed controller's coordination and choose one avenue/cross-street green split per local cycle: 47/35, 52/30 or 57/25 seconds. The cycle remains 90 seconds. The model sees current queues, vehicles, lane counts, downstream storage and a 15-second arrival estimate from current positions and speeds, with no future departures. A request is made 30–40 seconds into avenue green, subject to a two-second deadline and a 42-second application cutoff. Late or failed responses keep the baseline. Adjustments expire each cycle.

For the original three adaptive arms, a deterministic guard enforces 22-second minimum greens, 60-second maximum greens, three-second yellow and one-second all-red. An inference result is applied only after its actual measured arrival time, rounded to a simulation step, and only if its phase epoch remains valid. A two-second request deadline triggers queue-pressure fallback. Late or superseded responses are discarded. The client does not retry. Forced transitions and fallback actions are logged separately from model decisions.

Bounded Jev instead operates within SUMO's original coordinated program. It moves the end of avenue green by at most five seconds and compensates during cross-street green so the next cycle begins at the original time. It keeps all yellow and all-red durations. Its three allowed splits satisfy the original green bounds. The `keep` choice makes no signal-duration write; always choosing it exactly reproduces the fixed plan. This controller has its own module and runner; the native code is unchanged.

The integration measures observation preparation, client scheduling and API completion. Roadside sensing and physical actuation delays are not measured by this setup. Simulation step is 0.2 s. Clock lag is logged; a run is marked technically invalid if maximum lag reaches a full step. This checks the host's ability to maintain real time, not deployment readiness.

## Metrics and validation

The evaluation cohort includes all vehicles scheduled during the ten-minute measurement window. Three minutes of warm-up precede it; a three-minute drain follows it. Warm-up vehicles remain on the road and influence traffic, but are excluded from cohort trip metrics. Network queue metrics cover the measurement window and include every vehicle physically present.

Primary outcome: **SUMO `timeLoss` plus insertion delay, divided by all requested cohort trips**, including unfinished and never-inserted vehicles. For never-inserted vehicles, elapsed time since their scheduled departure is retained as entry delay. Lower is better. This is cumulative loss through a fixed horizon, not predicted eventual delay after the simulation stops.

Supporting measures: completed-trip mean and 95th-percentile travel times; mean/peak number of halted vehicles; completed throughput before demand ends and after drain; unfinished/uninserted trips; waiting episodes; and congested link-seconds. The last measure is a spillback **proxy**: at least one halted vehicle and occupancy above 80% of nominal storage, assuming 7.5 m per vehicle. It is not a directly measured queue-tail position. Trip-time columns are conditional on completion and must be read alongside unfinished counts.

Five evaluation seeds (11–15) are paired across four original controllers and two demand cases: 40 original runs. The bounded extension adds ten, for 50 total. Report differences using paired Student-t 95% intervals across seeds. Individual vehicles are not treated as independent experimental replications. Secondary metrics are descriptive; no multiple-comparison correction or broad superiority claim is made. The comparison between bounded and native Jev changes both coordination and decision policy; the fixed arm tests whether bounded choices improve the coordinated baseline.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m trafficlab.validate
```

Tests cover signal clearances, minimum/maximum green, stale responses, deadlines, no early application, demand reproducibility and accounting for unfinished demand. Runtime checks cover vehicle conservation, conflicting greens, collisions, teleports and clock lag. The validation script checks in-sample turning-flow consistency, an independent deterministic rerun, and conventional-controller sensitivity to boundary length, lane count, demand and timestep. Those checks do not replace held-out travel-time and queue observations. Jev sensitivity to those alternative physical assumptions is not yet evaluated.

## Files

- `trafficlab/`: network/demand generation, controllers, runner, tuning, benchmark and reporting.
- `scenario/`: generated SUMO network and metadata; demand files are deterministic per seed.
- `results/protocol.json`: protocol and source hashes recorded before the pilot.
- `results/bounded_protocol.json`, `results/bounded_validation.json`: frozen extension design, original-result hashes and independent signal/latency audit.
- `results/summary.json`, `results/validation.json`: aggregated outcomes and verification evidence.
- `results/raw/`: per-run SUMO trip files, request/action logs, results and compressed replay. Ignored by Git because reruns create sizeable outputs. Retain these locally to audit the delivered benchmark.
- `viewer/dist/`: static presentation, exported run metrics and compressed trajectories. It contains no API key and cannot operate real traffic lights.

Sources: [SUMO trip metrics](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html), [TypeSafe documentation](https://docs.typesafe.ai/), [NYC study record](https://zap.planning.nyc.gov/projects/2024M0142). The requested TypeSafe skill is installed in `.agents/skills/typesafe-ai/`.
