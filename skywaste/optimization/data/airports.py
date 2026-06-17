"""
Static airport → (country, continent) map for the serverless build.

The full project streams the ~90,000-row OurAirports CSV on first use and caches
it on disk. That pattern is a poor fit for Vercel functions (read-only FS, slow
cold starts, multi-MB download per cold container), so this build ships a curated
map of the major international airports instead.

Same public surface as the full module: `async def get_airport_info(iata)`.
Unknown codes return None, which makes the engine fall back to its hard-coded
benchmark set and then to the global-average disposal cost — exactly as before.

Continent codes follow the OurAirports convention: AF, AN, AS, EU, NA, OC, SA.
To extend coverage, add rows here (or set SUPABASE_* env vars to use the live DB).
"""
from __future__ import annotations

from typing import Optional

# IATA → (ISO-3166 alpha-2 country, continent)
_AIRPORTS: dict[str, tuple[str, str]] = {
    # ── North America (US) ──────────────────────────────────────────────
    "JFK": ("US", "NA"), "EWR": ("US", "NA"), "LGA": ("US", "NA"),
    "ORD": ("US", "NA"), "LAX": ("US", "NA"), "SFO": ("US", "NA"),
    "MIA": ("US", "NA"), "ATL": ("US", "NA"), "BOS": ("US", "NA"),
    "IAD": ("US", "NA"), "DFW": ("US", "NA"), "SEA": ("US", "NA"),
    "DEN": ("US", "NA"), "IAH": ("US", "NA"),
    "LAS": ("US", "NA"), "PHX": ("US", "NA"), "MCO": ("US", "NA"),
    "CLT": ("US", "NA"), "MSP": ("US", "NA"), "DTW": ("US", "NA"),
    "PHL": ("US", "NA"), "BWI": ("US", "NA"), "SLC": ("US", "NA"),
    "SAN": ("US", "NA"), "TPA": ("US", "NA"), "HNL": ("US", "NA"),
    "FLL": ("US", "NA"), "DCA": ("US", "NA"), "MDW": ("US", "NA"),
    "PDX": ("US", "NA"), "STL": ("US", "NA"), "AUS": ("US", "NA"),
    # ── North America (Canada / Mexico) ─────────────────────────────────
    "YYZ": ("CA", "NA"), "YVR": ("CA", "NA"), "YUL": ("CA", "NA"),
    "MEX": ("MX", "NA"), "CUN": ("MX", "NA"),
    # ── United Kingdom & Ireland ────────────────────────────────────────
    "LHR": ("GB", "EU"), "LGW": ("GB", "EU"), "MAN": ("GB", "EU"),
    "DUB": ("IE", "EU"),
    # ── European Union & EFTA ───────────────────────────────────────────
    "CDG": ("FR", "EU"), "ORY": ("FR", "EU"),
    "FRA": ("DE", "EU"), "MUC": ("DE", "EU"),
    "AMS": ("NL", "EU"), "BRU": ("BE", "EU"),
    "MAD": ("ES", "EU"), "BCN": ("ES", "EU"),
    "FCO": ("IT", "EU"), "MXP": ("IT", "EU"),
    "ZRH": ("CH", "EU"), "GVA": ("CH", "EU"),
    "VIE": ("AT", "EU"), "CPH": ("DK", "EU"),
    "ARN": ("SE", "EU"), "OSL": ("NO", "EU"),
    "HEL": ("FI", "EU"), "LIS": ("PT", "EU"),
    "ATH": ("GR", "EU"), "WAW": ("PL", "EU"), "PRG": ("CZ", "EU"),
    # ── Middle East ─────────────────────────────────────────────────────
    "TLV": ("IL", "AS"), "DXB": ("AE", "AS"), "AUH": ("AE", "AS"),
    "DOH": ("QA", "AS"), "RUH": ("SA", "AS"), "JED": ("SA", "AS"),
    "KWI": ("KW", "AS"), "BAH": ("BH", "AS"), "AMM": ("JO", "AS"),
    "IST": ("TR", "AS"),
    # ── Asia Pacific ────────────────────────────────────────────────────
    "SIN": ("SG", "AS"), "HKG": ("HK", "AS"),
    "NRT": ("JP", "AS"), "HND": ("JP", "AS"),
    "ICN": ("KR", "AS"), "TPE": ("TW", "AS"),
    "PEK": ("CN", "AS"), "PVG": ("CN", "AS"), "CAN": ("CN", "AS"),
    "BKK": ("TH", "AS"), "KUL": ("MY", "AS"),
    "CGK": ("ID", "AS"), "MNL": ("PH", "AS"),
    "DEL": ("IN", "AS"), "BOM": ("IN", "AS"),
    # ── Oceania ─────────────────────────────────────────────────────────
    "SYD": ("AU", "OC"), "MEL": ("AU", "OC"), "BNE": ("AU", "OC"),
    "AKL": ("NZ", "OC"),
    # ── South America ───────────────────────────────────────────────────
    "GRU": ("BR", "SA"), "GIG": ("BR", "SA"),
    "EZE": ("AR", "SA"), "SCL": ("CL", "SA"),
    "BOG": ("CO", "SA"), "LIM": ("PE", "SA"),
    # ── Africa ──────────────────────────────────────────────────────────
    "JNB": ("ZA", "AF"), "CPT": ("ZA", "AF"),
    "CAI": ("EG", "AF"), "LOS": ("NG", "AF"),
    "NBO": ("KE", "AF"), "CMN": ("MA", "AF"), "ADD": ("ET", "AF"),
}


async def get_airport_info(iata_code: str) -> Optional[dict]:
    """Return {country_code, continent} for a known IATA code, else None."""
    code = (iata_code or "").strip().upper()
    row = _AIRPORTS.get(code)
    if not row:
        return None
    country, continent = row
    return {
        "country_code": country,
        "continent": continent,
        "name": code,
        "municipality": "",
        "type": "large_airport",
    }


def cache_status() -> dict:
    """Parity with the full module's debug helper."""
    return {
        "loaded": True,
        "airport_count": len(_AIRPORTS),
        "source": "static-bundled",
    }
