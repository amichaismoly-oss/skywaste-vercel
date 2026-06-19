"""
Live El Al flight board.

Pulls El Al (LY) flights for TLV from a third-party flight-data API when a key is
configured, and falls back to a clearly-labelled demo set so the board is always
visible.

Provider priority (set ONE as a Vercel env var):
  AVIATION_EDGE_API_KEY   -> aviation-edge.com  (the configured provider)
  AERODATABOX_API_KEY     -> aerodatabox.p.rapidapi.com  (alternative)

El Al has no public API of its own; these providers track its flights. None of
them expose passenger counts or meals — that is the catering partner's unique
data, merged in on the frontend.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

_RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
_AE_BASE = "https://aviation-edge.com/v2/public"


def _demo_flights() -> dict:
    """Clearly-labelled sample board so the UI works without an API key."""
    flights = [
        {"flight_number": "LY001", "direction": "departure", "origin": "TLV", "destination": "JFK", "scheduled": "08:40", "status": "Scheduled", "aircraft": "B789"},
        {"flight_number": "LY315", "direction": "departure", "origin": "TLV", "destination": "LHR", "scheduled": "09:15", "status": "Boarding", "aircraft": "B739"},
        {"flight_number": "LY8",   "direction": "departure", "origin": "TLV", "destination": "EWR", "scheduled": "11:05", "status": "Scheduled", "aircraft": "B789"},
        {"flight_number": "LY5102","direction": "departure", "origin": "TLV", "destination": "CDG", "scheduled": "06:30", "status": "Departed", "aircraft": "B739"},
        {"flight_number": "LY28",  "direction": "arrival",   "origin": "JFK", "destination": "TLV", "scheduled": "16:20", "status": "En Route", "aircraft": "B789"},
        {"flight_number": "LY386", "direction": "arrival",   "origin": "BKK", "destination": "TLV", "scheduled": "17:45", "status": "Scheduled", "aircraft": "B788"},
    ]
    return {"source": "demo", "airport": "TLV", "count": len(flights), "flights": flights}


def _hhmm(ts: Optional[str]) -> str:
    if not ts:
        return ""
    return ts[11:16] if len(ts) >= 16 else ts


# ── Aviation Edge ────────────────────────────────────────────────────────────

def _ae_normalize(row: dict) -> Optional[dict]:
    """Map an aviation-edge timetable row to our shape; None if not El Al."""
    airline = row.get("airline") or {}
    if (airline.get("iataCode") or "").upper() != "LY":
        return None

    direction = (row.get("type") or "departure").lower()
    dep = row.get("departure") or {}
    arr = row.get("arrival") or {}
    flight = row.get("flight") or {}
    aircraft = row.get("aircraft") or {}

    dep_iata = (dep.get("iataCode") or "").upper()
    arr_iata = (arr.get("iataCode") or "").upper()
    number = (flight.get("iataNumber") or flight.get("number") or "").upper()
    if number and not number.startswith("LY"):
        number = "LY" + number.lstrip("LY")

    sched = dep.get("scheduledTime") if direction == "departure" else arr.get("scheduledTime")

    return {
        "flight_number": number or "LY—",
        "direction": direction,
        "origin": dep_iata or "—",
        "destination": arr_iata or "—",
        "scheduled": _hhmm(sched),
        "status": (row.get("status") or "scheduled").capitalize(),
        "aircraft": aircraft.get("modelCode") or aircraft.get("iataCode") or "—",
    }


async def _fetch_aviation_edge(key: str) -> dict:
    import httpx  # lazy import

    out: List[dict] = []
    async with httpx.AsyncClient(timeout=12.0) as client:
        for kind in ("departure", "arrival"):
            params = {"key": key, "iataCode": "TLV", "type": kind, "airline_iata": "LY"}
            r = await client.get(f"{_AE_BASE}/timetable", params=params)
            if r.status_code != 200:
                continue
            data = r.json()
            if not isinstance(data, list):  # error object {"error": ...}
                continue
            for row in data:
                n = _ae_normalize(row)
                if n:
                    out.append(n)

    if not out:
        d = _demo_flights()
        d["note"] = "Aviation Edge returned no El Al flights for the window — showing demo"
        return d
    return {"source": "live", "provider": "aviation-edge", "airport": "TLV", "count": len(out), "flights": out}


# ── AeroDataBox (alternative) ────────────────────────────────────────────────

def _adb_normalize(raw: dict, direction: str) -> Optional[dict]:
    airline = raw.get("airline") or {}
    number = (raw.get("number") or "").replace(" ", "")
    if (airline.get("iata") or "").upper() != "LY" and not number.upper().startswith("LY"):
        return None
    movement = raw.get("movement") or {}
    counterpart = movement.get("airport") or {}
    sched = movement.get("scheduledTime") or {}
    aircraft = raw.get("aircraft") or {}
    other = (counterpart.get("iata") or counterpart.get("icao") or "—")
    origin, dest = ("TLV", other) if direction == "departure" else (other, "TLV")
    return {
        "flight_number": number,
        "direction": direction,
        "origin": origin,
        "destination": dest,
        "scheduled": _hhmm(sched.get("local") or sched.get("utc")),
        "status": raw.get("status") or "Scheduled",
        "aircraft": aircraft.get("model") or aircraft.get("reg") or "—",
    }


async def _fetch_aerodatabox(key: str) -> dict:
    import httpx

    host = os.getenv("AERODATABOX_HOST", _RAPIDAPI_HOST)
    now = datetime.now(timezone.utc)
    frm = now.strftime("%Y-%m-%dT%H:%M")
    to = (now + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M")
    url = f"https://{host}/flights/airports/iata/TLV/{frm}/{to}"
    params = {"direction": "Both", "withLeg": "true", "withCancelled": "true"}
    headers = {"x-rapidapi-key": key, "x-rapidapi-host": host}
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(url, params=params, headers=headers)
        if r.status_code != 200:
            d = _demo_flights()
            d["note"] = f"AeroDataBox HTTP {r.status_code} — showing demo"
            return d
        data = r.json()
    out: List[dict] = []
    for f in data.get("departures") or []:
        n = _adb_normalize(f, "departure")
        if n:
            out.append(n)
    for f in data.get("arrivals") or []:
        n = _adb_normalize(f, "arrival")
        if n:
            out.append(n)
    return {"source": "live", "provider": "aerodatabox", "airport": "TLV", "count": len(out), "flights": out}


async def get_elal_flights() -> dict:
    ae_key = os.getenv("AVIATION_EDGE_API_KEY")
    adb_key = os.getenv("AERODATABOX_API_KEY")
    try:
        if ae_key:
            return await _fetch_aviation_edge(ae_key)
        if adb_key:
            return await _fetch_aerodatabox(adb_key)
        return _demo_flights()
    except Exception as e:  # pragma: no cover
        d = _demo_flights()
        d["note"] = f"flight API error ({e}) — showing demo"
        return d
