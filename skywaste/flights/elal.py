"""
Live El Al flight board.

Pulls El Al (LY) flights for TLV from AeroDataBox (a third-party flight-data API)
when an API key is configured, and falls back to a clearly-labelled demo set so
the board is always visible.

El Al has no public API of its own; third-party providers track its flights.
None of them expose passenger counts or meals — that is the catering partner's
unique data, merged in on the frontend.

Config (Vercel env vars):
  AERODATABOX_API_KEY   RapidAPI key for aerodatabox.p.rapidapi.com
  AERODATABOX_HOST      optional host override (default RapidAPI host)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List

_RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"


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


def _normalize(raw: dict, direction: str) -> dict | None:
    """Map an AeroDataBox flight object to our shape; None if not El Al."""
    airline = (raw.get("airline") or {})
    number = (raw.get("number") or "").replace(" ", "")
    iata = (airline.get("iata") or "").upper()
    if iata != "LY" and not number.upper().startswith("LY"):
        return None

    movement = raw.get("movement") or {}
    counterpart = (movement.get("airport") or {})
    sched = movement.get("scheduledTime") or {}
    sched_str = sched.get("local") or sched.get("utc") or ""
    # Keep just HH:MM if a full timestamp is present.
    hhmm = sched_str[11:16] if len(sched_str) >= 16 else sched_str

    aircraft = (raw.get("aircraft") or {})
    other_iata = (counterpart.get("iata") or counterpart.get("icao") or "—")

    if direction == "departure":
        origin, dest = "TLV", other_iata
    else:
        origin, dest = other_iata, "TLV"

    return {
        "flight_number": number,
        "direction": direction,
        "origin": origin,
        "destination": dest,
        "scheduled": hhmm,
        "status": raw.get("status") or "Scheduled",
        "aircraft": aircraft.get("model") or aircraft.get("reg") or "—",
    }


async def get_elal_flights() -> dict:
    key = os.getenv("AERODATABOX_API_KEY")
    if not key:
        return _demo_flights()

    host = os.getenv("AERODATABOX_HOST", _RAPIDAPI_HOST)
    try:
        import httpx  # lazy import

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
            n = _normalize(f, "departure")
            if n:
                out.append(n)
        for f in data.get("arrivals") or []:
            n = _normalize(f, "arrival")
            if n:
                out.append(n)
        return {"source": "live", "airport": "TLV", "count": len(out), "flights": out}
    except Exception as e:  # pragma: no cover
        d = _demo_flights()
        d["note"] = f"flight API error ({e}) — showing demo"
        return d
