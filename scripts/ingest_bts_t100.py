#!/usr/bin/env python3
"""
Ingest a BTS T-100 Segment CSV into the bundled `bts_routes.json` the app serves.

BTS publishes no live API for granular T-100 data — you download the CSV once from
TranStats (free), then run this script. It aggregates the raw per-carrier/per-month
segment rows into clean per-route records (avg passengers/flight, distance, dominant
aircraft) that feed the optimization engine.

USAGE
-----
1. Download the T-100 Segment CSV from TranStats (see README "BTS ingest" section):
     https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GED&QO_fu146_anzr=Nv4%20Pn44vr45
   Pick these columns: PASSENGERS, DEPARTURES_PERFORMED, DISTANCE, ORIGIN, DEST,
   AIRCRAFT_TYPE, UNIQUE_CARRIER, YEAR, MONTH  → download → unzip the CSV.

2. Run:
     python scripts/ingest_bts_t100.py path/to/T_T100_SEGMENT.csv
   Options:  --top 40   --min-departures 50   --us-only

The output is written to:
     skywaste/optimization/data/bts_routes.json
and is served at GET /api/bts/routes.

No pandas required — pure stdlib so it runs anywhere.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

MILES_TO_KM = 1.60934

# Output path (bundled into the serverless function via vercel.json includeFiles).
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skywaste", "optimization", "data", "bts_routes.json",
)

# Common BTS T-100 aircraft type codes → readable label. Unknown codes fall back
# to "Type {code}". This is purely cosmetic (the engine math ignores aircraft type).
AIRCRAFT_CODES = {
    "612": "A319", "614": "A320", "613": "A321", "616": "A330-200", "617": "A330-300",
    "622": "A350", "626": "A220", "630": "B717", "634": "B737-700", "637": "B737-800",
    "638": "B737-900", "645": "B737 MAX 8", "658": "B747-400", "655": "B747",
    "664": "B757-200", "665": "B757-300", "667": "B767-300", "669": "B767-400",
    "673": "B777-200", "674": "B777-300", "675": "B777", "676": "B777-200LR",
    "677": "B777-300ER", "679": "B787-8", "680": "B787-9", "681": "B787-10",
    "694": "E170", "695": "E175", "696": "E190", "698": "CRJ-200", "699": "CRJ-700",
    "700": "CRJ-900", "461": "ATR-72", "473": "Dash-8",
}

# Header aliases — T-100 column names vary slightly by how you export from TranStats.
ALIASES = {
    "origin": ["ORIGIN", "origin"],
    "dest": ["DEST", "DESTINATION", "dest"],
    "passengers": ["PASSENGERS", "passengers"],
    "departures": ["DEPARTURES_PERFORMED", "DEPARTURES", "departures_performed"],
    "distance": ["DISTANCE", "distance"],
    "aircraft": ["AIRCRAFT_TYPE", "AIRCRAFT", "aircraft_type"],
    "carrier": ["UNIQUE_CARRIER", "CARRIER", "OP_UNIQUE_CARRIER", "unique_carrier"],
    "year": ["YEAR", "year"],
    "month": ["MONTH", "month"],
}


def _pick(header_map, key):
    for name in ALIASES[key]:
        if name in header_map:
            return header_map[name]
    return None


def _num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def ingest(csv_path, out_path, top, min_departures, us_only):
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        header_map = {h.strip(): i for h, i in zip(header, range(len(header)))}

        idx = {k: _pick(header_map, k) for k in ALIASES}
        missing = [k for k in ("origin", "dest", "passengers", "departures") if idx[k] is None]
        if missing:
            sys.exit(f"ERROR: CSV missing required columns for: {missing}\nFound headers: {list(header_map)}")

        routes = defaultdict(lambda: {
            "passengers": 0.0, "departures": 0.0, "distance_mi": 0.0,
            "aircraft_counts": defaultdict(float), "carriers": set(),
            "year": None, "month": None,
        })

        rows = 0
        for row in reader:
            if not row or idx["origin"] >= len(row):
                continue
            o = row[idx["origin"]].strip().upper()
            d = row[idx["dest"]].strip().upper()
            if len(o) != 3 or len(d) != 3:
                continue
            pax = _num(row[idx["passengers"]])
            dep = _num(row[idx["departures"]])
            if dep <= 0:
                continue
            r = routes[(o, d)]
            r["passengers"] += pax
            r["departures"] += dep
            if idx["distance"] is not None:
                r["distance_mi"] = max(r["distance_mi"], _num(row[idx["distance"]]))
            if idx["aircraft"] is not None:
                r["aircraft_counts"][row[idx["aircraft"]].strip()] += dep
            if idx["carrier"] is not None:
                r["carriers"].add(row[idx["carrier"]].strip().upper())
            if idx["year"] is not None and r["year"] is None:
                r["year"] = row[idx["year"]].strip()
            if idx["month"] is not None and r["month"] is None:
                r["month"] = row[idx["month"]].strip()
            rows += 1

    out = []
    for (o, d), r in routes.items():
        if r["passengers"] <= 0 or r["departures"] < min_departures:
            continue
        avg_pax = round(r["passengers"] / r["departures"])
        if avg_pax <= 0:
            continue
        # Dominant aircraft by departures.
        ac_code = ""
        if r["aircraft_counts"]:
            ac_code = max(r["aircraft_counts"].items(), key=lambda kv: kv[1])[0]
        out.append({
            "origin": o,
            "dest": d,
            "avg_pax": avg_pax,
            "distance_km": round((r["distance_mi"] or 0) * MILES_TO_KM, 1),
            "aircraft_code": ac_code,
            "aircraft": AIRCRAFT_CODES.get(ac_code, f"Type {ac_code}" if ac_code else "Unknown"),
            "carrier": sorted(r["carriers"])[0] if r["carriers"] else "",
            "total_passengers": int(r["passengers"]),
            "total_departures": int(r["departures"]),
            "year": r["year"],
            "month": r["month"],
        })

    out.sort(key=lambda x: x["total_passengers"], reverse=True)
    out = out[:top]

    payload = {
        "source": "BTS T-100 Segment (TranStats)",
        "ingested": True,
        "ingested_from": os.path.basename(csv_path),
        "route_count": len(out),
        "rows_processed": rows,
        "note": "Avg passengers/flight = total passengers ÷ departures performed.",
        "routes": out,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"[ok] Ingested {rows:,} segment rows -> {len(out)} routes")
    print(f"[ok] Wrote {out_path}")
    if out:
        top3 = ", ".join(f"{r['origin']}-{r['dest']} ({r['avg_pax']} pax)" for r in out[:3])
        print(f"  Top routes: {top3}")


def main():
    ap = argparse.ArgumentParser(description="Ingest BTS T-100 Segment CSV → bts_routes.json")
    ap.add_argument("csv_path", help="Path to the T-100 Segment CSV from TranStats")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output JSON path")
    ap.add_argument("--top", type=int, default=40, help="Keep the top N routes by passengers")
    ap.add_argument("--min-departures", type=int, default=50, help="Skip routes with fewer departures")
    ap.add_argument("--us-only", action="store_true", help="(reserved) keep US-only routes")
    args = ap.parse_args()

    if not os.path.exists(args.csv_path):
        sys.exit(f"ERROR: file not found: {args.csv_path}")
    ingest(args.csv_path, args.out, args.top, args.min_departures, args.us_only)


if __name__ == "__main__":
    main()
