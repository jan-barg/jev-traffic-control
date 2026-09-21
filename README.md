# Midtown Traffic Lab

**Experiment closed: the tested Jev controllers did not demonstrate an advantage over the strongest conventional baselines.**

We compared three ways of using TypeSafe Jev to control traffic lights against fixed-time schedules and simple numerical controllers. The test used a SUMO simulation of twelve schematic intersections on Sixth and Seventh Avenues, West 25th–30th Streets, informed by published NYC turning volumes. Real API latency was included while traffic continued moving.

[**Open the side-by-side replay**](https://jan-barg.github.io/jev-traffic-control/) · [Detailed methods and reproduction](docs/REPRODUCING.md) · [Data provenance and limits](docs/NYC_BENCHMARK_AUDIT.md)

## What we found

- **Native Jev increased delay substantially.** Choosing whether individual signals should hold or switch performed worse than the tuned fixed schedule in both tested scenarios.
- **Bounded Jev largely reproduced fixed-time control.** It retained the baseline split in 1,254 of 1,256 applied decisions; allowing a five-second adjustment did not produce a useful improvement.
- **Coordinated Jev did not outperform a retuned fixed plan.** Selecting a corridor-wide plan reduced average delay against the original reference in two scenarios, but those paired uncertainty intervals included zero. The retuned fixed plan had lower mean delay in all three scenarios.
- **Jev mostly repeated the numerical choice.** In coordinated control, it selected the supplied forecast's minimum-cost plan on 145 of 150 decisions. There was no demonstrated advantage over selecting that minimum directly in code.

These findings concern these implementations and modeled conditions. They do not establish a general limitation of Jev or AI traffic control, or effectiveness on actual NYC streets.

## Results

The primary measure is **accumulated delay per requested evaluation trip, in seconds**: SUMO time loss plus waiting to enter the network, including unfinished and uninserted trips. Lower is better. Each number is a mean across five paired traffic seeds. **Bold marks the lowest mean in each scenario, including exact ties.** Bold does not imply statistical significance.

### Original controllers and bounded extension

| Controller | Morning | Morning + 50% surge |
|---|---:|---:|
| Tuned fixed-time | **40.37** | **46.95** |
| Actuated | 61.67 | 87.37 |
| Queue pressure | 59.91 | 77.02 |
| Native Jev | 89.45 | 143.12 |
| Bounded Jev | 40.39 | **46.95** |

The original pilot contains 40 runs; bounded Jev adds ten runs on the same seeds (11–15). The bounded controller was designed after observing the pilot, so its comparison is exploratory. Native Jev's delay increase versus fixed-time was **49.1 s/trip** in morning traffic (95% paired interval: 37.4 to 60.8) and **96.2 s/trip** in the surge (83.7 to 108.6).

[Original pilot report](docs/BENCHMARK_RESULTS.md) · [Bounded Jev report](docs/BOUNDED_JEV_RESULTS.md) · [Results data](results/summary.json)

### Coordinated plan selection

| Controller | Morning | Morning + 50% surge | Changing directional demand |
|---|---:|---:|---:|
| Original tuned fixed-time | **39.33** | 44.53 | 52.34 |
| Retuned fixed plan | 39.40 | **42.52** | **45.44** |
| Numerical plan selector | 40.34 | 43.63 | 46.84 |
| Coordinated Jev | 40.29 | 43.37 | 46.84 |

This separate experiment contains 60 runs on fresh seeds (31–35). Compare controllers **within each table**: the different seeds explain why the same original fixed controller has different averages across the two experiments.

Coordinated Jev's mean difference from the original fixed plan was:

| Scenario | Jev minus original fixed (s/trip) | 95% paired interval |
|---|---:|---:|
| Morning | +0.96 | −0.44 to +2.36 |
| Surge | −1.17 | −3.28 to +0.95 |
| Changing demand | −5.50 | −12.66 to +1.66 |

Negative differences favor Jev. **All three intervals include zero.** Jev and the numerical selector produced identical primary delay in every changing-demand replication; their differences in the other two scenarios were small and uncertain. Improving the plan library helped, but this experiment did not establish an added benefit from Jev's selection.

[Coordinated report, including queues, travel times and completion](docs/COORDINATED_RESULTS.md) · [Results data](results/coordinated_summary.json) · [Frozen protocol](results/coordinated_protocol.json)

## What the controllers actually did

| Approach | Decision |
|---|---|
| Tuned fixed-time | Repeat a coordinated 90-second schedule: 52 seconds of avenue green, 30 seconds of cross-street green, and eight seconds of clearance. Selected on separate development seeds. |
| Actuated | Switch when the opposing road is waiting and the current approach empties or its green reaches 40 seconds, subject to common green limits. |
| Queue pressure | Compare queues while accounting for downstream congestion, using a simple pressure rule. |
| Native Jev | Every five seconds, choose hold or switch for each eligible intersection from its observed traffic state. |
| Bounded Jev | Choose a five-second green transfer or retain the baseline at each intersection; the change lasts one cycle and preserves coordination. |
| Retuned fixed plan | Keep one junction-specific split profile, selected offline from seven candidates on separate development seeds. |
| Numerical plan selector | Every 90 seconds, choose the lowest forecast queue cost from five corridor plans. |
| Coordinated Jev | Choose from those same five plans using the same forecasts and observed traffic. Install changes at eligible local cycle starts. |

The coordinated forecast projects 180 seconds in two-second steps, using current queues, vehicle positions and speeds, recent boundary arrival rates, turning shares and downstream space. Its cost is predicted queued vehicle-seconds plus 30 seconds per vehicle still queued at the horizon. That penalty and the assumed discharge rate are modeling choices, not NYC-calibrated measurements. Neither selector sees scheduled future departures or demand changes.

## Timing, validation and limits

There are **110 retained benchmark runs**, in addition to development and sensitivity simulations. The final code passed 20 automated tests. The coordinated audit independently checked 45,780 phase durations and 7,080 cycles, with no signal-timing violations, conflicting greens, simulated collisions or teleports. All earlier results were preserved.

Jev ran at one simulated second per wall-clock second. Coordinated control made **150 real API calls**, with **412 ms median** and **552 ms P95** end-to-end latency, zero API errors and zero missed deadlines. Actual inference and the subsequent wait for plan installation affected the traffic outcome. Replay speed only changes the animation. See the reports for native and bounded latency measurements.

The first coordinated live batch was invalidated by laptop sleep and repeated in full with unchanged code, seeds and validity rules. Its metrics and file hashes are disclosed in the [execution retry record](results/coordinated_execution_retry.json); no valid run was selected or discarded based on traffic performance.

The conclusions remain limited:

- Five paired seeds per scenario form a small pilot. Intervals are paired Student-t intervals without multiple-comparison adjustment and do not cover uncertainty in the physical model.
- Published turning counts inform arrivals and routes. Cars do turn, but geometry, lanes, driving behavior, fleet mix and signal timings are assumptions; the reference is not a verified NYC DOT timing plan.
- The model excludes pedestrians, bicycles, bus stops and curbside obstruction. Surge and directional changes are synthetic cases.
- No independent NYC travel-time or queue observations were used for field validation. Zero simulated collisions is an implementation check, not evidence of street safety.

[Original validation](results/validation.json) · [Bounded audit](results/bounded_validation.json) · [Coordinated audit](results/coordinated_validation.json)

## Explore or reproduce

The [GitHub Pages viewer](https://jan-barg.github.io/jev-traffic-control/) displays recorded SUMO trajectories, synchronized playback, signal decisions and downloadable metrics. Viewing it requires no API key and makes no Jev calls. Representative replay seeds were selected in advance: 11 for the original experiment and 31 for coordinated plans.

To view the same files locally:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory viewer/dist
```

Open `http://127.0.0.1:8765`. For dependencies, simulation commands, model assumptions and audit procedures, see [Running and auditing the experiment](docs/REPRODUCING.md). New live benchmarks make paid TypeSafe API calls.

Source, summary results and representative replays are committed. Full raw simulation/request logs remain in the ignored local `results/raw/` directory; the repository does not contain every raw trace. [Version 1.0.0](https://github.com/jan-barg/jev-traffic-control/tree/v1.0.0) preserves the first implementation.

GitHub Pages publishes only `viewer/dist/` through [the deployment workflow](.github/workflows/pages.yml). Viewer changes pushed to `main` update the site automatically; deployment never reruns the experiment or requires a TypeSafe secret.
