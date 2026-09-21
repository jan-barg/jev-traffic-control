# NYC benchmark: location and data audit

Audited 21 September 2026. This is a data-feasibility result. No controller experiment has been run and no traffic improvement has been measured.

## Recommendation

Build the first NYC scenario around **Sixth and Seventh Avenues, West 25th–West 30th Streets: 12 controlled intersections**. Use the Midtown South Mixed-Use Plan FEIS's existing-condition network, associated with its **June 2024 collection campaign**, as the initial historical demand reference. Start with weekday 08:00–09:00. Keep noon, evening and Saturday scenarios for broader evaluation once the baseline is reconstructed.

This is the strongest contiguous small grid found in this audit, not a claim that it is the best-observed location anywhere in NYC. It has published turning volumes and neighboring intersections that make coordination and spillback meaningful. The controlling area is two avenues by six cross streets; the simulated map must extend beyond it. Do not clip the road network at the outermost traffic lights.

**Ready now:** a SUMO scenario informed by observed NYC counts, with explicit assumptions. **Not ready yet:** a simulation independently validated against observed travel times/queues and verified historical signal operation. The missing information is specific enough to request or collect; it should not be silently invented.

## What the audit actually checked

- Downloaded and read transportation chapters and appendices for Midtown South and Atlantic Avenue from NYC Planning's public ZAP records. Inspected the AM turning-volume maps visually.
- Queried the official Automated Traffic Volume Counts API: 448 location/year aggregate rows across all boroughs from 2022 onward, and 3,249 aggregate rows across all available years for Manhattan, Brooklyn and Queens. These are **grouped records, not 448 sensors or vehicle totals**.
- Downloaded a live Midtown in Motion local-street travel-time snapshot: 351 link rows, 213 with positive sample count, time and aggregation window. The remaining 138 rows had zero samples. Availability in one snapshot is not a reliability estimate.
- Examined a 2,000-row sample of the other DOT traffic-speed dataset. Its 125 distinct links are an incomplete sample. A full grouped link-inventory request timed out; this sample is not used to assert that a street has no coverage.
- Screened the older East Harlem study as an alternative. Its chapter download was blocked by the server; it was not audited as deeply as the two downloaded studies.

## Candidate comparison

| Candidate | Evidence retrieved | Main limitations | Decision |
| --- | --- | --- | --- |
| Sixth/Seventh, W25–W30 | Midtown South FEIS lists all 12 signals and turning volumes for four periods; June 2024 collection campaign | Actual timing sheets and independent historical travel times/queues not retrieved; local speed links had no samples in our snapshot | **Preferred initial grid** |
| Atlantic Avenue, Vanderbilt–Nostrand | Atlantic Avenue FEIS lists seven successive signalized intersections, turning volumes and December 2023 collection | Full baseline timing sheets not retrieved; live speed links found west of this core, not on the seven-signal corridor | **Strong second scenario**, useful two-way arterial |
| Sixth/Seventh, W34–W42 corridor | Live local-street links returned positive samples; Midtown South study covers several intersections near its southern end | Longer links span roads beyond the counted subset; counts, timing plans and travel times must be aligned to the same period | Candidate if fresh observed travel times become the priority |
| East Harlem / 116th–125th area | Official 2017 FEIS identified; recent ATR rows at E116/First–Pleasant and Pleasant/E116–117 | Older study, sparse recent count locations in this screen, full chapter retrieval blocked | Defer; no verified complete benchmark package |

Long Island City was considered during source discovery but was not audited to the same depth. No comparative claim about its suitability is made.

Primary records: [Midtown South ZAP](https://zap.planning.nyc.gov/projects/2024M0142), [Atlantic Avenue ZAP](https://zap.planning.nyc.gov/projects/2022K0436), [East Harlem FEIS notice](https://www.nyc.gov/assets/planning/download/pdf/applicants/env-review/east-harlem/noc_feis.pdf).

## Exact first scenario

These are the study's intersection identifiers, **not SUMO or DOT controller IDs**:

| Cross street | Sixth Avenue FEIS ID | Seventh Avenue FEIS ID |
| --- | ---: | ---: |
| W30 | 9 | 23 |
| W29 | 10 | 24 |
| W28 | 11 | 25 |
| W27 | 12 | 26 |
| W26 | 13 | 27 |
| W25 | 14 | 28 |

Verify these against Figure 13-6 and Table 13-20 when constructing the network. The table has apparent street-label typos such as “W 28th Ave”; the map and street grid resolve these to W28th Street. Do not copy such labels as new roads.

The FEIS provides existing volumes for weekday **08:00–09:00, 12:00–13:00, 17:00–18:00**, and Saturday **13:00–14:00**. References within the downloaded chapter:

| PDF page(s), counted from 1 | Evidence |
| --- | --- |
| 28 | Analysis peak-hour windows |
| 30 | HCM/Synchro analysis methodology |
| 42, printed 13-34 | June 2024 counts, June/July inventory, DOT-supplied timing plans, incorporation of overlapping Western Rail Yard study inputs |
| 44–47, Figures 13-6a–d | Existing turning-volume maps |
| 48–50, Table 13-20 | Signalized intersection list and **modeled** lane-group delay/LOS |
| 50–51 | Congestion-pricing caveat and future network changes |

The published network is a study reconstruction, not an identified single-day trajectory recording. Exact dates and provenance of reused counts need confirmation. Do not combine these historical counts with today's geometry or today's speeds and call the result a validation. The study explicitly says its pre-congestion-pricing transportation data were not adjusted for the program.

Current OSM geometry is a starting point only. Check lane allocations, permitted turns, cycle lanes, crossings, bus stops and signal locations against period-specific inventories. Include upstream/downstream blocks and intermediate signals; increase the buffer until the comparison is insensitive to the boundary. For the feed's 23rd–34th Street travel-time segments, the eventual simulated measurement path must span those exact endpoints, even though only 12 central signals are experimental controls.

## What the travel-time feed adds

The [official local-street feed](https://data.cityofnewyork.us/d/ume6-8kxp) points to [this public CSV](https://linkdata.nyctmc.org/data/mim_data_opendata.csv). It downloaded successfully. Fields include link geometry, length in feet, sample count, aggregation window, calculation timestamp, median travel time in seconds and median speed in feet/second.

The downloaded snapshot's timestamp is `9/21/2026 11:21:24`, with no timezone suffix. Preserve it as supplied until the timezone is confirmed. Rows with observations use a 900-second aggregation window in this snapshot; a catalog refresh cadence of five minutes does not make them independent five-minute observations.

| Link ID | Measurement segment | Samples in snapshot | Interpretation |
| --- | --- | ---: | --- |
| 047023 | Sixth Avenue northbound, 23rd–34th | 0 | Geographical coverage exists; no usable observation in this snapshot |
| 060106 | Seventh Avenue southbound, 34th–23rd | 0 | Same limitation |
| 023017 | Sixth Avenue northbound, 34th–42nd | 26 | Usable positive-sample live row; different spatial extent |
| 059060 | Seventh Avenue southbound, 42nd–34th | 11 | Usable positive-sample live row; different spatial extent |
| 071201 | Atlantic eastbound, Flatbush–Carlton | 47 | West of the proposed Vanderbilt–Nostrand backup |
| 201071 | Atlantic westbound, Carlton–Flatbush | 54 | West of the proposed backup |

**Zero samples means missing data.** It does not mean zero traffic, an empty road, zero travel time or permanently broken equipment. No continuous collection job has been started. No June 2024 archive has been verified. If collecting a new campaign, retain timestamped snapshots, sample counts and missingness; account for overlapping aggregation windows and the E-ZPass sample's representativeness. Compare equivalent simulated segment medians, not network-wide mean delay.

## The three remaining evidence gaps

1. **Historical signal operation.** The FEIS states DOT supplied plans, but the retrieved chapter/Appendix E do not expose a complete usable set of cycle lengths, phases, splits, offsets, pedestrian clearance and time-of-day schedules. Obtain the plans and relevant adaptive/override logs for the collection period. Until then, label our baseline “assumed conventional control,” never “actual NYC control.” A citywide adaptive program is not proof of adaptive operation at these particular 12 nodes.
2. **Raw demand and geometry.** Obtain date-specific 15-minute turns, classifications, pedestrian/cycle counts, ATR time series, inventory drawings and study model files. Peak-hour diagrams constrain a model but do not identify arrival bursts, routes, queues or unrestricted entry demand. Published counts may be rounded or balanced; retain that uncertainty. The ATR archive has W26 and W29 counts between Sixth/Seventh in 2019, which are not a contemporaneous substitute for June 2024 turns.
3. **Independent validation observations.** Obtain same-period corridor travel times and queues, ideally on multiple dates with held-out observations. The FEIS's Synchro delay/LOS figures are predictions from another model. They are useful cross-checks, not measured ground truth. If historical observations cannot be obtained, perform a new synchronized counts/timings/travel-time campaign and label it as a new scenario.

A [precise draft data request](NYC_DATA_REQUEST_DRAFT.md) is included. It has **not been sent**. This audit does not establish that the requested records will be available or releasable.

## Benchmark design and implementation decision

Proceed with **SUMO + a Python experiment harness + a synchronized 2D browser viewer**. The TypeSafe skill remains the integration guide. First prove phase transitions, deterministic demand and latency handling on a small existing SUMO example, then construct the 12-signal NYC patch. The data gaps do not block this engineering prototype.

Run four arms: documented local operation when obtained (otherwise an honestly labeled conventional plan), conventional actuated control, max-pressure, and Jev. Apply equivalent sensing and signal constraints. Preserve pedestrian timing, minimum green, yellow/all-red intervals and maximum service gaps in a deterministic wrapper. Jev chooses among admissible actions using compact text/JSON observations; code handles arithmetic and execution.

The primary run uses **one simulated second per wall-clock second**. Inference is asynchronous while traffic and the current plan continue. An answer can affect a future simulation step only after its measured end-to-end arrival; expired or invalid answers trigger the predefined fallback. Log decision age, p50/p95/p99 latency, deadline misses, fallbacks and clock drift. Presentation can replay recorded outcomes faster afterward.

Reconstruct boundary demand and turning shares from the counts, then generate stochastic arrivals within the observations' resolution. Do not freeze internal observed flows as externally imposed demand after changing controllers. Use matched departure schedules, routes, incidents and driver draws across arms, and keep all unfinished trips and entry queues in reporting. Tune on development scenarios and freeze policies before held-out evaluation.

Report two results separately:

- **Baseline fidelity:** observed versus simulated volume, segment travel time and queue behavior, with missingness and held-out errors. Do not grade fit on the same observations used to tune it.
- **Controller effect:** paired differences in delay, throughput, queues, unfinished demand, pedestrian/bus outcomes and reliability, across independent replications and plausible calibration variants.

The permissible first result is “Jev improved this specified NYC-informed simulation under these assumptions.” After independent validation, it can become “Jev improved a simulation validated against these NYC observations.” Real-world deployment benefit requires an actual intervention study; shadow decisions cannot establish it.

## Reproducibility

Run `python3 scripts/audit_nyc_data.py` from the repository to validate cached formats, generate SHA-256 source hashes and rebuild the coverage summary. `--fetch SOURCE_NAME` refreshes one public source; it changes the snapshot and its derived results. See [data notes](../data/nyc_audit/README.md). No credentials or paid APIs are required for this audit.
