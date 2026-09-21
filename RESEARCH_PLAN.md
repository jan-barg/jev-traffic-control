# Jev traffic-control experiment

Research checked 20 September 2026; NYC data audit added 21 September 2026. This document preserves the original design and proposed extensions. A working 12-intersection SUMO prototype, 2D viewer and 40-run pilot are now complete: see [README](README.md) and [benchmark results](docs/BENCHMARK_RESULTS.md). The first Jev controller increased delay relative to the tuned fixed plan. Field validation remains outstanding; several richer observations and road users proposed below are not part of the delivered vehicle-only pilot.

**Location decision after the data audit:** start with Sixth and Seventh Avenues at West 25th–West 30th Streets, a 12-signal core covered by the Midtown South FEIS's existing-volume maps. Use its June 2024 collection campaign as the initial historical reference, with exact dates and reused-study inputs still to confirm. The [completed audit](docs/NYC_BENCHMARK_AUDIT.md) records the evidence, source cache, Atlantic Avenue backup and outstanding data request. A working public local-street travel-time feed was found, but both links through this core returned zero samples in the downloaded snapshot. Actual historical signal plans and independent same-period travel-time/queue observations remain missing. We can build an NYC-informed prototype now; it is not yet an independently validated NYC benchmark.

Use **SUMO for traffic, a Python controller adapter for Jev, and a 2D overhead browser viewer for synchronized comparisons**. Debug with one intersection, then run the first substantive NYC experiment on the proposed 12-signal core with surrounding roads as a buffer. These sizes are proposed project scopes, not measured hardware limits. The primary comparison must include Jev's measured response time while traffic continues moving, as requested by the user.

The TypeSafe skill is installed for Codex in `.agents/skills/typesafe-ai/`; `skills-lock.json` records its source and hash. Installation used the requested `npx skills add` method. The initial attempt encountered the full Xcode installation's license prompt; retrying with the separately installed, working Command Line Tools Git succeeded without changing Xcode. The skill's live documentation informed this design.

## Existing software worth reusing

| Option | What it provides | Fit for this project |
| --- | --- | --- |
| [SUMO](https://sumo.dlr.de/docs/) | Open-source microscopic traffic simulation, pedestrians, scenario tools and a built-in GUI | Recommended simulation engine; individual vehicles, lane interactions and crossings matter for this experiment |
| [SUMO-RL](https://github.com/LucasAlegre/sumo-rl) | SUMO signal-control environments with observations and discrete phase actions | Useful adapter/examples; Jev does not require reinforcement-learning training |
| [RESCO](https://github.com/Pi-Star-Lab/RESCO) | Existing SUMO scenarios and fixed-time, max-pressure and other controller implementations | Useful external benchmark and baseline reference; its documented city scenarios are not NYC |
| [CityFlow](https://github.com/cityflow-project/CityFlow) | Microscopic engine designed for large signal-control experiments, Python interface, multithreading | Strong alternative if throughput becomes the priority; benchmark locally before believing comparative speed claims |
| [UXsim](https://github.com/toruseo/UXsim) | Compact Python macroscopic/mesoscopic network simulator | Useful for regional congestion studies; less suitable as the main lane-level intersection experiment |

SUMO's [TraCI interface](https://sumo.dlr.de/docs/TraCI/) can observe a running simulation and alter signals. A [traffic-light tutorial](https://sumo.dlr.de/docs/Tutorials/TraCI4Traffic_Lights.html) already demonstrates the required control loop. We would build the experiment harness, Jev adapter and presentation layer, rather than vehicle physics.

There is also a promising NYC shortcut: [TrafficClaw](https://github.com/usail-hkust/TrafficClaw) advertises SUMO networks, routes and demand assets for Manhattan, Queens and Brooklyn in its [public dataset](https://huggingface.co/datasets/TrafficClaw/TrafficClaw-Env-Data). The public file index confirms `.net.xml` and `.sumocfg` files for **Upper Manhattan, Inner Brooklyn and Inner Queens**, at dataset revision `dbfb993c63d66522dde1cd80ec9e6c89a7119407`. These names should not be taken as complete borough coverage. Its dataset card declares MIT; upstream geographic data terms and code licensing still need checking before vendoring. Inspect calibration, dates, boundary conditions and signal provenance before adopting a subset. This research pass has not run those scenarios or established that they reproduce present-day NYC. Its agent framework is much broader than this project's needs.

## What ordinary signals do

There is no single universal baseline. Common operating modes include a repeated timed plan, detection-driven green extensions or skipped phases, and coordinated operation across neighboring intersections. Coordination controls the relative timing between signals so vehicles can progress along a corridor. Adaptive systems revise timing in response to observed conditions. These concepts are described in [FHWA's detector handbook](https://www.fhwa.dot.gov/publications/research/operations/its/06108/03.cfm).

[NYC DOT](https://www.nyc.gov/html/dot/html/infrastructure/signals.shtml) says its signal cycles usually last 45–120 seconds and are selected using local traffic volumes and patterns. It also documents leading and exclusive pedestrian intervals. A [2012 DOT account of Midtown in Motion](https://www.nyc.gov/html/dot/html/pr2012/pr12_25.shtml) establishes that coordinated and responsive traffic management existed in Midtown; it does not identify today's controller configuration at a chosen intersection.

Use four controller arms:

1. **Coordinated fixed-time:** credible cycle lengths, green shares and corridor offsets. Use actual plans if obtained; otherwise tune on development demand and label this a representative baseline.
2. **Conventional actuated:** extends green or changes phases using traffic detectors, within the same timing constraints. SUMO provides built-in [actuated and delay-based controllers](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html).
3. **Max-pressure:** a conventional algorithm that favors movements with high upstream queues relative to downstream queues, subject to our shared constraints. RESCO includes an implementation to inspect.
4. **Jev:** chooses among admissible actions using the same available traffic observations as the adaptive baselines.

The central question is whether Jev adds value beyond a capable conventional adaptive controller. Beating a poorly timed light alone would not answer it. A no-signal condition is optional for a different research question and is not the appropriate primary comparator here.

## Stochastic experiment design

Use microscopic simulation with stochastic demand and behavior. Start with seeded arrivals at network entrances, sampled turning/routes and sampled vehicle characteristics. A time-varying Poisson process can be an initial demand generator, but measured counts, burst arrivals and platoons should replace or supplement it as evidence becomes available. Let traffic propagation inside the network produce its own interactions.

Pre-generate each demand realization and reuse it across controllers: the same scheduled vehicles, desired departure times, routes, classes and incidents. Keep initial traffic and signal state identical. Match seeds and random streams where possible; the same seed alone does not guarantee that controllers consume internal random numbers identically after their trajectories diverge. Hold route choice fixed in the first experiment; evaluate rerouting separately later. Controllers see current and historical observations, not the future demand schedule.

Proposed evaluation protocol:

- Develop on separate demand patterns and seeds; freeze prompts, timing parameters and decision rules before the final comparison.
- Pilot a few replications, then start with around 20–30 paired seeds per scenario and adjust the count using the observed variance. This is a starting budget, not a statistical guarantee. FHWA discusses [replication requirements](https://ops.fhwa.dot.gov/trafficanalysistools/tat_vol3/sectapp_a.htm).
- Use a warm-up, a fixed evaluation window and a bounded drain period. A starting configuration is 15 minutes of warm-up and 60 minutes of demand; inspect congestion and warm-up stability before fixing these values.
- Test ordinary demand, directional rush-hour demand, oversaturation, sudden surges, blocked lanes and noisy or missing detectors. Freeze incident times and exposure across arms.
- Report paired differences with 95% confidence intervals across independent runs. Do not treat correlated vehicles from one run as independent experimental replications.

Choose the primary outcome before tuning. A useful first outcome is accumulated vehicle delay, including delay before insertion, over the common evaluation horizon. Report requested trips, admitted trips, completed trips, residual queues and unfinished trips alongside it. Use average and 95th-percentile trip times as supporting measures, with the unfinished-trip treatment explicit. SUMO's [trip output](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) distinguishes departure delay, waiting, time loss and unfinished vehicles; these should not be silently conflated.

Also measure queue lengths, spillback, stops, approach-level service, pedestrian waiting, bus delay, forced fallback use, signal switches, collisions/teleports and API latency. Track vehicles that cannot enter the map: an apparent gain must not come from leaving demand outside the simulated roads or omitting unfinished trips. Make teleport handling explicit and consistent, and flag affected runs.

For a NYC claim, include pedestrian crossing demands and timing constraints early. Start with vehicle-delay reporting if needed, but label that limitation. Add person-delay comparisons once occupancy assumptions are specified; a bus full of passengers should not silently count as equivalent to one car. Travel-time improvements are not evidence of improved crash safety.

## Jev's role

The current [model documentation](https://docs.typesafe.ai/models) lists text/JSON input, not images or video. Read observations directly from SUMO initially. A future camera input would need a separate perception system, evaluated as another component.

For each eligible decision, code computes queues, recent arrivals, waiting-time summaries, downstream occupancy, phase age and pedestrian demand. Include a compact recent history and nearby intersection summaries. Code also computes pressure, thresholds and admissible actions. TypeSafe specifically identifies [numeric precision and irrelevant context](https://docs.typesafe.ai/model-jaggedness/jev-1.13) as limitations; do not delegate arithmetic or dump every vehicle into the prompt.

Ask a narrow [Choice question](https://docs.typesafe.ai/primitives/choice): select an allowed green extension or an allowed transition to a named phase. Start with a five-second decision cadence, then compare slower/event-driven decisions. That cadence is a hypothesis to test, not a requirement to change the lights every five seconds.

The controller wrapper enforces minimum green, maximum green, required yellow/all-red transitions, crossing clearance, compatible movements and service limits. These limits come from the scenario definition and apply to all relevant arms. Jev never writes arbitrary lamp states. When only one action is admissible, code executes it without a model call. When the API fails or returns too late, a predetermined conventional controller provides the action. Record the selected, rejected, overridden and applied actions separately.

Use the [Python SDK](https://docs.typesafe.ai/sdk/python) in the backend, keeping the API key server-side. Pin the evaluated model version, log request state and returned probabilities, and preserve SDK/config versions. The current documented version is `jev-1.13.0`; verify it again at implementation time. Model confidence describes its distribution, not the probability that an action improves traffic. If confidence affects fallback, tune that policy on development scenarios and report how often the fallback actually acts.

Batch independent intersection questions only over compact, relevant shared state, as the [TypeSafe skill](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md) recommends. Questions in a batch cannot see each other's answers. Neighbor observations and joint-action validation therefore still matter; batching alone does not coordinate a network. A later experiment can compare local phase selection with Jev selecting corridor strategies over a slower timescale. Identify hybrids separately so gains from conventional control are not attributed entirely to Jev.

## NYC geography and scale

| Proposed scope | What it answers | Main limitation |
| --- | --- | --- |
| One intersection | Does the adapter and signal state machine behave correctly? | Cannot establish network coordination benefits |
| A corridor of 5–10 signals | Can decisions preserve progression along a street? | Limited cross-street network effects |
| A patch of roughly 9–16 signals | Do local gains survive queues spilling into neighboring blocks? | Requires checked turning movements and boundary demand |
| A district of roughly 50–200 signals | Can the policy coordinate over a wider area? | More calibration, API throughput and runtime work |
| Hundreds to thousands of signals | Borough-scale system behavior | Substantial demand reconstruction, computation and validation |

These ranges describe useful stages. SUMO is designed for large networks, but this machine's throughput, memory needs and Jev latency have not been measured. A borough-scale model is technically plausible; a credible borough-scale experiment is a later research project.

Import geography with SUMO's [OpenStreetMap tools](https://sumo.dlr.de/docs/Networks/Import/OpenStreetMap.html), or audit and crop reusable NYC assets. Check one-way streets, lanes, connectivity, turns, bus stops and crossings. Include surrounding uncontrolled roads/signals and test the effect of moving the boundary. An imported map does not contain a validated demand model or necessarily the actual signal schedule. SUMO's [Manhattan tutorial](https://sumo.dlr.de/docs/Tutorials/Manhattan.html) is a synthetic grid model, not a ready reconstruction of Manhattan.

[NYC automated traffic counts](https://data.cityofnewyork.us/d/7ym2-wayt) can constrain volumes. The [dataset description](https://catalog.data.gov/dataset/automated-traffic-volume-counts) says coverage is sampled rather than continuous across the year. [TLC trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) can inform taxi/FHV travel patterns, but do not represent every car, truck, bus, cyclist or pedestrian. Match the modeled period to the data rather than mixing dates without adjustment. Obtain or measure turning shares, pedestrian flows and local timings separately where missing.

Maintain three explicit evidence levels: synthetic benchmark; NYC geography with assumed/calibrated demand; locally validated NYC scenario with verified baseline timings. Results at one level should not be presented as evidence for a stronger level. A complete public current timing-plan archive was not verified in this research pass.

## Benchmark against observed NYC traffic

Added 21 September 2026. The benchmark should answer two separate questions: does the baseline model reproduce observed NYC traffic, and does Jev improve outcomes relative to that validated baseline under matched demand? Agreement between Jev's chosen light and an observed light is not the primary score; different actions can both be reasonable, and recordings do not reveal what would have happened under the alternative action.

The [Automated Traffic Volume Counts dataset](https://data.cityofnewyork.us/Transportation/Automated-Traffic-Volume-Counts/7ym2-wayt) provides directional counts in 15-minute bins, with dates, times and street segments. A two-row API request succeeded during this research pass. These are sampled counts, not a continuous citywide stream, and do not supply individual trajectories or all turning movements. Its published location-error attachment should be considered during site matching.

[NYC DOT's speed feeds](https://www.nyc.gov/html/dot/html/about/datafeeds.shtml) cover detector locations primarily on major arterials and highways; check coverage and timestamp availability for the exact candidate streets. They cannot be assumed to validate a small Manhattan street grid. TLC pickup/drop-off records provide another limited source of observed trip durations and origins/destinations, but zone-level taxi/FHV journeys are not individual lane trajectories or a representative sample of all road users.

Verified local signal operation is a key missing input. Seek period-specific timing sheets, phase sequences, cycle lengths, splits, offsets, pedestrian intervals, detector settings and any adaptive operating logs that exist. [NYC DOT's records-request process](https://www.nyc.gov/html/dot/html/about/foil.shtml) is a possible route; record availability is not established. Targeted field observations can verify visible timings and collect queues, turns and crossings where suitable data are unavailable. DOT's data-feed page says developer camera-feed access requires a data-sharing agreement; do not assume an unrestricted historical video archive. No records request or external message has been sent.

Recommended protocol:

1. **Select the location and period from data coverage.** Retain the planned 9–16-intersection target if observations support it; a smaller well-observed corridor is a better benchmark than a larger unverified map. Require overlapping dates for counts, travel times, geometry and signal settings. Record incidents, construction and weather where available.
2. **Reconstruct and calibrate the observed baseline.** Infer boundary demand and turning patterns, load the documented signal operation, and adjust plausible traffic parameters using development observations. Counts inside a congested network reflect the existing signals and downstream capacity; they are not automatically unrestricted external demand. Avoid fixing observed internal outflows as inputs that would prevent Jev from changing them.
3. **Validate on withheld observations.** Check time-binned flow, corridor travel times and queue buildup/dissipation on dates or observations not used to fit the model. Use the same spatial boundaries and measurement definitions as the real data. Set acceptance criteria before evaluating Jev and report residual error and natural day-to-day variation. Calibration followed by alternatives analysis is consistent with [FHWA's microsimulation workflow](https://ops.fhwa.dot.gov/publications/fhwahop18036/).
4. **Run the matched counterfactual experiment.** Freeze the calibrated model, benchmark dates and controller policies. Generate several plausible arrival/behavior realizations consistent with observed demand, because 15-minute counts do not identify exact second-by-second arrivals. Reuse each realization across the baseline, conventional adaptive controllers and Jev. After changing signals, let traffic evolve in response to each controller's own state. Include measured end-to-end Jev latency while the traffic clock advances, as specified below.
5. **Publish model fit and controller outcomes separately.** Report observed NYC values against the modeled baseline, then Jev's paired difference from that baseline, with replication uncertainty and sensitivity to demand, turns, sensing and calibration. Retain unfinished trips, entry queues and pedestrian outcomes. If the claimed advantage disappears under plausible model assumptions, it is not a robust conclusion.

The appropriate first claim is a measured improvement in a simulation validated against specified NYC observations. Public historical records alone cannot establish the real-world effect of deploying Jev. A later shadow run on live observations can measure latency, availability and proposed actions, but cannot measure their actual traffic benefit while existing lights still control the road. Demonstrating that benefit would require an agency-authorized field experiment with a suitable comparison design.

## Real time, API budget and animation

Separate the simulation clock, decision cadence and display frame rate. Compare both arms at the same simulated timestamp. **The primary experiment is paced at one simulated second per wall-clock second, with asynchronous inference. Traffic never waits for Jev.** A zero-latency or pause-for-inference run may be used only as a separately labeled diagnostic, not as the reported deployment-realistic result.

At each eligible decision, timestamp the traffic observation and dispatch a request without blocking simulation stepping. Account for observation preparation, client queuing, network round trip, provider processing, SDK retries/backoff, response validation and command delivery within the implemented system. The measured end-to-end delay includes inference; it is not a measurement of model compute alone. Additional roadside sensor or hardware delays are explicit assumptions or separate measurements, not implicitly covered by the API round trip.

A response may first affect the controller on a simulation step at or after its measured arrival time. Never backdate it to the observation time. For example, an illustrative 180 ms end-to-end delay means at least 180 ms of traffic evolution before the decision becomes available; discrete simulation steps can add further delay. Any required yellow or clearance interval occurs after the accepted command and remains part of the outcome. Select a sufficiently small simulation step and check sensitivity to its rounding of response times.

While a request is in flight, the existing signal state machine continues executing its last valid plan, including all required transitions and timing limits. Use a configured decision deadline and predetermined fallback. Revalidate a response against the current phase, admissible actions and observation age before applying it. Expired or superseded responses are discarded, not applied after a fallback has already changed the phase. Start with at most one outstanding decision request per intersection, and avoid an unbounded backlog. A slow request must not block unrelated intersections or the conventional comparison arm.

Measure observation age at application, end-to-end latency (median, p95 and p99), deadline misses, fallback duration/frequency and simulation clock drift. Measure conventional controller computation and command delays too. If the simulator cannot keep up with the wall-clock schedule, flag the run as unable to meet real time; do not silently slow traffic and give Jev extra time. Rendering runs independently so visual frame drops do not alter control outcomes.

Save trajectories, light states, observations, request/response timestamps and applied actions. **Recorded replay** can run at any viewing speed without further inference; the original run's delays and their traffic consequences remain intact. Label replay clearly. Faster-than-real-time batch experiments would need a separately validated latency model and event scheduling that preserves delay in simulated seconds; they cannot simply reuse wall-clock API duration while the traffic clock runs faster and claim equivalence to deployment.

At five-second decisions and one request per intersection, real-time request load is `12 × intersections` per minute. Accelerating a separate live batch experiment multiplies that load and can itself change latency and throttling. The currently published limit is 1,200 requests/minute, with a separate 250,000 input tokens/second limit, both subject to change. Thus 100 intersections consume the nominal request limit at real time before retries, and 16 intersections at 10× speed exceed it without batching or fewer calls. Measure actual account limits before scaling. Accelerated recorded playback has no such inference load. [TypeSafe models and limits](https://docs.typesafe.ai/models).

For an illustrative 1,000 input tokens per decision, 16 intersections over one simulated hour at five-second intervals use 11.52 million input tokens. At the currently listed $0.042/million input tokens, that is approximately $0.48 for Jev; 30 such replications are approximately $14.52. These are arithmetic estimates, not measured costs, and exclude warm-up/drain calls, longer state, retries, extra scenarios, compute and storage. Log actual usage. Batching changes the token accounting.

Use SUMO-GUI first to inspect geometry and signals. Then build a polished **2D overhead** browser comparison in TypeScript with a Canvas/WebGL renderer: matching maps, linked pan/zoom, moving cars and buses, visible crossings, queue coloring, a shared timeline and selectable baseline. This perspective keeps both sides readable and makes queues and signal changes easy to compare. Stream backend snapshots for live viewing and use the same data format for recorded replay. The viewer interpolates motion but never invents traffic outcomes. A later isometric or 3D presentation can consume the same simulation output; it is a separate rendering project and does not by itself improve the traffic model's validity.

Show waiting/delay, throughput, unfinished demand, spillback and pedestrians next to the animation. Distinguish a single run's numbers from the aggregate experiment results. Selecting an intersection should show its observed queues, available actions and the action actually applied. Jev does not generate explanatory prose: any displayed explanation must be an evidence-based code template or a clearly labeled interpretation, not an invented quotation. Avoid displaying an unmeasured improvement percentage.

## Proposed build sequence

1. **Prove the harness:** one existing SUMO intersection, credible fixed-time and actuated controllers, a conventional pressure baseline, shared demand and measured output.
2. **Integrate Jev:** bounded choices, asynchronous requests while traffic advances at real time, measured end-to-end delay, transitions, stale-response rejection, deadline behavior, fallback and complete decision logs. Run small paid tests only once server-side credentials are configured.
3. **Make the comparison visible:** two synchronized 2D overhead views, live traffic and latency metrics, and deterministic replay of recorded runs.
4. **Build the NYC patch:** select roughly 9–16 signals based on data coverage, verify geometry and document every assumed parameter. Test sensitivity to boundary conditions and demand.
5. **Evaluate and scale:** freeze policies, run paired replications, publish gains and regressions with uncertainty, then profile 50–200 signals before attempting borough scale.

The immediate next implementation milestone is a reproducible single-intersection comparison. The first substantive deliverable should be a small NYC network with honest labels on its data fidelity, four controller arms, and a side-by-side viewer backed by saved simulation output.
