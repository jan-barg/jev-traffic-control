#!/usr/bin/env python3
"""Inspect cached NYC benchmark sources; optionally fetch one named source.

Default execution is offline and uses only the Python standard library.
Example: python3 scripts/audit_nyc_data.py --fetch mim_speed_snapshot
"""
import argparse
import collections
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nyc_audit"
GROUP = "boro,street,fromst,tost,segmentid,wktgeom,yr"


def socrata(dataset, **params):
    return f"https://data.cityofnewyork.us/resource/{dataset}.json?" + urlencode(
        {"$" + key: value for key, value in params.items()}
    )


SOURCES = {
    "atr_locations_2022_onward": {
        "file": "atr_locations_2022_onward.json",
        "url": socrata("7ym2-wayt", select=GROUP + ",count(*) as records",
                        where="yr>=2022", group=GROUP, order="boro,street,yr", limit=50000),
        "meaning": "All-borough location/year aggregates; records are source rows, not vehicles.",
        "limit": 50000,
    },
    "atr_locations_all_years": {
        "file": "atr_locations_all_years.json",
        "url": socrata("7ym2-wayt", select=GROUP + ",count(*) as records",
                        where="boro in('Manhattan','Brooklyn','Queens')", group=GROUP,
                        order="boro,street,yr", limit=50000),
        "meaning": "Location/year aggregates for Manhattan, Brooklyn and Queens only.",
        "limit": 50000,
    },
    "speed_snapshot": {
        "file": "speed_snapshot.json",
        "url": socrata("i4gi-tjb9", limit=2000),
        "meaning": "Unordered 2,000-row sample; incomplete and unsuitable for proving absent coverage.",
    },
    "speed_links": {
        "file": "speed_links.json",
        "url": socrata("i4gi-tjb9", select="link_id,link_name,borough,link_points,encoded_poly_line",
                        group="link_id,link_name,borough,link_points,encoded_poly_line", limit=5000),
        "meaning": "Attempted distinct link inventory; an absent file indicates failed retrieval.",
        "limit": 5000,
    },
    "mim_speed_snapshot": {
        "file": "mim_speed_snapshot.csv",
        "url": "https://linkdata.nyctmc.org/data/mim_data_opendata.csv",
        "catalog": "https://data.cityofnewyork.us/d/ume6-8kxp",
        "meaning": "One live local-street snapshot, not a historical archive; speed unit is ft/s.",
    },
    "midtown_south_transportation": {
        "file": "midtown_south_transportation.pdf",
        "url": "https://zap-api-production.herokuapp.com/document/artifact/01QY2C5KMDOTP3PCPCOJAKKQIYDVOBY22D",
        "catalog": "https://zap.planning.nyc.gov/projects/2024M0142",
        "meaning": "24DCP094M FEIS chapter 13; June 2024 data collection, with overlapping-study inputs.",
    },
    "midtown_south_transportation_appendix": {
        "file": "midtown_south_transportation_appendix.pdf",
        "url": "https://zap-api-production.herokuapp.com/document/artifact/01QY2C5KME4ERQCUMD3FCYAGN46RVN2RZA",
        "catalog": "https://zap.planning.nyc.gov/projects/2024M0142",
        "meaning": "24DCP094M FEIS Appendix E: transportation planning material, not full timing sheets.",
    },
    "atlantic_avenue_transportation": {
        "file": "atlantic_avenue_transportation.pdf",
        "url": "https://zap-api-production.herokuapp.com/document/artifact/01QY2C5KKERTGMSNAJAFB26CR2FVVKZOZR",
        "catalog": "https://zap.planning.nyc.gov/projects/2022K0436",
        "meaning": "24DCP019K FEIS chapter 13; December 2023 data collection.",
    },
    "atlantic_avenue_transportation_appendix": {
        "file": "atlantic_avenue_transportation_appendix.pdf",
        "url": "https://zap-api-production.herokuapp.com/document/artifact/01QY2C5KOEM45ESKNTGRGKVFLEY7M4P5J4",
        "catalog": "https://zap.planning.nyc.gov/projects/2022K0436",
        "meaning": "24DCP019K FEIS Appendix E: transportation planning material.",
    },
}


def decode_source(name, body):
    ext = Path(SOURCES[name]["file"]).suffix
    if ext == ".json":
        value = json.loads(body)
        if not isinstance(value, list):
            raise ValueError(f"{name}: expected rows, received an API error or other object")
        cap = SOURCES[name].get("limit")
        if cap and len(value) >= cap:
            raise ValueError(f"{name}: query limit reached; completeness is unverified")
        return value
    if ext == ".csv":
        value = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
        required = {"sid", "link_name", "n_samples", "median_tt_sec", "median_speed_fps",
                    "aggregation_period_sec", "median_calculation_timestamp"}
        if not value or not required <= value[0].keys():
            raise ValueError(f"{name}: missing expected feed columns")
        return value
    if not body.startswith(b"%PDF-"):
        raise ValueError(f"{name}: response is not a PDF")
    return None


def fetch(name):
    source = SOURCES[name]
    # subprocess arguments are not interpreted by a shell.
    body = subprocess.check_output([
        "curl", "-sS", "--fail", "--connect-timeout", "15", "--max-time", "120", source["url"]
    ])
    decode_source(name, body)
    path = DATA / "raw" / source["file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(body)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".retrieval.json").write_text(json.dumps({
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "url": source["url"]
    }, indent=2) + "\n")


def audit():
    manifest, cached = {}, {}
    for name, source in SOURCES.items():
        entry = dict(source)
        path = DATA / "raw" / source["file"]
        entry["status"] = "missing"
        if path.exists():
            body = path.read_bytes()
            cached[name] = decode_source(name, body)
            entry.update(status="cached", bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            entry["cache_file_modified_at_utc"] = datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).isoformat()
            entry["timestamp_note"] = "File modification time is a download-time proxy, not observation time."
            if cached[name] is not None:
                entry["rows"] = len(cached[name])
        manifest[name] = entry

    summary = {"audit_generated_at_utc": datetime.now(timezone.utc).isoformat()}
    for name in ["atr_locations_2022_onward", "atr_locations_all_years"]:
        if name not in cached:
            continue
        rows = cached[name]
        summary[name] = {
            "location_year_rows": len(rows),
            "by_borough": dict(collections.Counter(r["boro"] for r in rows)),
            "by_year": dict(sorted(collections.Counter(r["yr"] for r in rows).items())),
            "note": "Aggregates are not unique sites, dates, vehicle counts or a spatial coverage proof.",
        }
    if "mim_speed_snapshot" in cached:
        rows = cached["mim_speed_snapshot"]
        usable = [r for r in rows if int(r["n_samples"]) > 0 and float(r["median_tt_sec"]) > 0
                  and int(r["aggregation_period_sec"]) > 0]
        target_ids = {"047023", "060106", "071201", "201071", "023017", "059060"}
        summary["mim"] = {
            "rows": len(rows), "rows_with_positive_samples_time_and_window": len(usable),
            "by_borough": dict(collections.Counter(r["borough"] for r in rows)),
            "aggregation_period_seconds": dict(collections.Counter(r["aggregation_period_sec"] for r in rows)),
            "feed_timestamps_as_supplied": sorted({r["median_calculation_timestamp"] for r in rows}),
            "target_links": [r for r in rows if r["sid"] in target_ids],
            "note": "Zero-sample rows are missing observations, not zero traffic or zero travel time. "
                    "The feed timestamp has no timezone suffix; none is inferred here.",
        }
    if "speed_snapshot" in cached:
        rows = cached["speed_snapshot"]
        summary["dot_speed_sample"] = {
            "rows": len(rows), "distinct_link_ids": len({r["link_id"] for r in rows}),
            "complete_inventory": False,
        }

    derived = DATA / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    (derived / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (derived / "coverage_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"cached_sources": sum(v["status"] == "cached" for v in manifest.values()),
                      "missing_sources": [k for k,v in manifest.items() if v["status"] == "missing"],
                      "outputs": [str(derived / "source_manifest.json"), str(derived / "coverage_summary.json")]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", choices=SOURCES, help="Refresh one source before auditing cached files")
    args = parser.parse_args()
    if args.fetch:
        fetch(args.fetch)
    audit()
