# Midtown Traffic Lab — pilot results

Run on 21 September 2026 with SUMO 1.27.1 and TypeSafe Jev 1.13.0. **The first Jev controller did not improve traffic in this model.** The tuned coordinated fixed plan had lower delay in both demand scenarios. This is a result about this implementation and these assumptions, not a general limit on Jev or AI signal control.

## Primary result

All values below are means across five matched traffic seeds. Primary delay is cumulative SUMO time loss plus insertion delay, divided by every requested evaluation trip, including unfinished trips.

| Demand | Tuned fixed | Actuated | Queue pressure | Jev | Jev minus fixed (95% paired interval) |
|---|---:|---:|---:|---:|---:|
| Published AM | 40.4 s | 61.7 s | 59.9 s | 89.4 s | +49.1 s (37.4 to 60.8) |
| Synthetic surge | 47.0 s | 87.4 s | 77.0 s | 143.1 s | +96.2 s (83.7 to 108.6) |

Five replications per arm is a pilot. Intervals use the paired Student-t method across seeds, not individual vehicles. They cover seed-to-seed variation within this model, not uncertainty in geometry, behavior or actual NYC operation. No secondary-metric multiple-comparison adjustment is made.

## Supporting traffic measures

Travel times include completed trips only and therefore need to be read alongside unfinished demand. Mean/peak queues cover all vehicles in the network during the ten-minute measurement window; peak is the mean of per-run maxima.

### Published AM demand

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Finished by 13:00 | Finished after drain | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 104.7 | 174.9 | 29.6 / 61.8 | 554.0 | 689.0 | 4.0 | 1.14 | 2.9 |
| Actuated | 125.2 | 214.3 | 48.2 / 97.0 | 547.2 | 685.2 | 7.8 | 2.12 | 374.7 |
| Queue pressure | 124.1 | 195.2 | 44.0 / 83.4 | 549.0 | 687.6 | 5.4 | 2.38 | 95.0 |
| Jev | 153.0 | 259.5 | 74.0 / 149.8 | 499.4 | 681.2 | 11.8 | 2.46 | 652.9 |

### Synthetic surge demand

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Finished by 13:00 | Finished after drain | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 111.5 | 196.4 | 40.8 / 86.0 | 709.0 | 870.4 | 5.4 | 1.22 | 45.6 |
| Actuated | 146.9 | 295.5 | 74.3 / 163.6 | 649.0 | 844.0 | 31.8 | 2.37 | 667.6 |
| Queue pressure | 140.8 | 234.0 | 66.9 / 147.8 | 669.4 | 862.8 | 13.0 | 2.74 | 435.2 |
| Jev | 188.0 | 378.4 | 120.9 / 278.4 | 528.6 | 750.8 | 125.0 | 3.20 | 1358.3 |

The mean requested evaluation cohort is 693.0 vehicles in AM and 875.8 in surge; counts match across controllers. Every requested vehicle entered the network in every primary run. Stops are SUMO waiting episodes. Congested link-seconds are a spillback proxy: halted vehicles present and occupancy above 80% of assumed storage, not a measured queue-tail position. Delay is accumulated through minute 16; unfinished vehicles would incur additional delay afterward.

## Real-time inference

Across 1,866 real API batches, latency was 237 ms at the median, 410 ms at P95, 619 ms at P99 and 1791 ms maximum. There were zero API errors, deadline misses or fallback actions. 10,094 model actions were applied.

Every Jev run advanced at one simulated second per wall second while a separate thread made API calls. Observations and client scheduling are included in measured latency. Actions waited for the actual response and the next simulation poll; maximum extra polling delay was 203.5 ms with a 200 ms timestep. Maximum host clock lag was 34.1 ms. All accepted actions were verified against the recorded model answer and arrived before application. Roadside sensor and physical actuation latency remain unmodeled.

Ten independent replications ran concurrently, so measured service times include that provider/client load. Replay speed affects presentation only; it never rescales the original API latency. Conventional algorithms ran accelerated, with measured computation delay rounded up to a simulation step.

Jev chose hold 8,448 times and switch 1,646 times. The guard forced 742 transitions at maximum green. The controller receives local aggregate state and downstream occupancy, but no explicit arrival forecast or corridor offset target. Poor coordination or the choice policy could explain the worse results; the present experiment does not isolate the cause. Fast inference alone did not produce good control.

## What was validated

- 40/40 primary runs passed technical runtime checks: vehicle conservation, no simulated collisions, no teleports, no conflicting avenue/cross-street greens and acceptable real-time clock lag.
- Eight automated tests passed, covering clearances, minimum/maximum green, stale/invalid actions, delayed responses, deadlines, reproducible demand and unfinished-trip accounting.
- One independent fixed-controller rerun exactly reproduced metrics, movement counts and demand hash.
- All primary simulator/controller/network/data hashes still match the protocol recorded before evaluation. All four arms share identical demand/network hashes for each scenario and seed.
- The 48 simulated AM turning flows have 3.88% volume-weighted absolute error against the published inputs, averaged across five fixed-plan runs. This is an in-sample consistency check, not independent calibration or field validation.
- 42 additional conventional sensitivity runs passed. Fixed-plan delay stayed below the simple pressure heuristic in every tested variant. These do not validate Jev under changed assumptions.

| Sensitivity case | Fixed delay (s) | Pressure delay (s) |
|---|---:|---:|
| base | 40.9 | 57.2 |
| short buffer | 40.4 | 57.9 |
| long buffer | 41.0 | 59.6 |
| two avenue lanes | 43.9 | 88.0 |
| demand minus 15pct | 39.0 | 57.0 |
| demand plus 15pct | 40.9 | 69.3 |
| step 100ms | 40.7 | 57.3 |

SUMO recorded 8 emergency-braking warnings in the primary runs. Zero simulated collisions is an implementation check, not evidence of real-world crash safety.

## Scope and next experiment

This is a 2D replay of a microscopic SUMO simulation at 12 intersections: Sixth and Seventh Avenues, West 25th–30th Streets. Its 48 AM turning volumes come from Midtown South FEIS Figure 13-6a (June 2024 collection campaign). All 16 internal links balance. Poisson arrivals and sampled turn routes create stochastic traffic realizations. Roads are schematic; lanes, block lengths, speeds, fleet mix and signal settings are assumptions.

The reference plan was selected from 16 candidates on separate development seeds 901–902: a 90-second cycle, 52/30-second avenue/cross greens and nominal 9 m/s avenue progression. It is not verified NYC DOT timing. All adaptive arms share 22–60-second green limits, three-second yellow and one-second all-red. Their initially synchronized greens differ from the coordinated fixed offsets. The comparison concerns complete controller designs, not an isolated replacement of one timing decision.

Measurement uses three minutes of warm-up, ten minutes of demand and three minutes of drain. Surge means 50% higher boundary demand during the middle five minutes. It is a synthetic stress case. Pedestrians, bicycles, bus stops, parking interference and observed origin/destination routes are absent. Published FEIS delay estimates are modeled outputs, not independent ground truth.

A useful next controller would retain the coordinated plan and let Jev make bounded adjustments using predicted arrivals and downstream capacity. Develop it on separate seeds; freeze the policy before testing new seeds. Then obtain actual lane/turn restrictions, signal plans, held-out travel times and queue observations, add pedestrians/transit, and recalibrate before expanding to a neighborhood. The existing runner and viewer support that iteration; this pilot does not justify a borough-scale or real-street benefit claim.

## Reproduction and sources

See [README](../README.md) for commands, assumptions and metric definitions; [validation evidence](../results/validation.json), [paired results](../results/summary.json) and [protocol](../results/protocol.json) for machine-readable details. Raw requests, signal actions, SUMO trip logs and replays are retained locally under `results/raw/`.

[NYC Midtown South study record](https://zap.planning.nyc.gov/projects/2024M0142) · [SUMO trip metrics](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) · [TypeSafe documentation](https://docs.typesafe.ai/) · [NYC data audit](NYC_BENCHMARK_AUDIT.md)
