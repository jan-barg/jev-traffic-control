# NYC audit source cache

Retrieved 21 September 2026. Source URLs, cache modification times, sizes and SHA-256 hashes are generated in `derived/source_manifest.json` by `scripts/audit_nyc_data.py`. Observation dates differ from retrieval dates.

- `raw/`: unmodified API responses and source PDFs. PDFs were downloaded through links visible in the official NYC Planning ZAP project records.
- `derived/*_pages.json`: pypdf text extraction with one-based PDF page numbers. Extraction can contain table-order errors or source typos; the relevant AM maps were visually inspected.
- `derived/coverage_summary.json`: machine-readable, reproducible feed checks. It is not a calibrated traffic model.
- `derived/midtown_south_intersections.json`: manually verified study-intersection inventory. IDs belong to the FEIS, not an imported simulation network.

`atr_locations_2022_onward.json` includes all boroughs; `atr_locations_all_years.json` includes only Manhattan, Brooklyn and Queens. Both group by borough, street, endpoints, segment ID, geometry and year. `records` is the number of underlying rows, not a vehicle count. The 50,000-result limits were not reached. We did not transform WKT coordinates or claim a complete GIS spatial join; street names and the study's maps were used for the shortlist.

`speed_snapshot.json` is capped at 2,000 rows and cannot establish total coverage. A separate full distinct-link query timed out during this audit. No negative coverage inference is drawn from that failure.

`mim_speed_snapshot.csv` is one snapshot of aggregate local-street measurements. IDs retain leading zeroes. Zero-sample rows are missing observations. `median_speed_fps` is feet per second; it is not mph. A catalog update interval is not the same as the row's aggregation window. Timestamp timezone and historical archive availability were not verified.

PDF study values labeled existing conditions can still be reconstructed/balanced inputs or modeled outputs. In particular, Synchro delay/LOS is **not observed delay**. Future scenarios in the same PDFs are not baseline observations.

Reproduce the offline checks:

```sh
python3 scripts/audit_nyc_data.py
```

Refresh one source, preserving a retrieval timestamp sidecar (requires network):

```sh
python3 scripts/audit_nyc_data.py --fetch mim_speed_snapshot
```

Refreshing overwrites that named cache file and changes the coverage summary. Archive a benchmark's frozen data before refreshing. The original audit report describes the initial snapshot, not later refreshes.

These are NYC agency sources, not project-authored measurements. Preserve provenance and consult the [NYC DOT data-feed reuse/disclaimer information](https://www.nyc.gov/html/dot/html/about/datafeeds.shtml) before redistributing a public package. No public redistribution or external publication was performed in this audit.
