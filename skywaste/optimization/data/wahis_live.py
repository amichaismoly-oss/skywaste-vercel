"""
WAHIS live outbreak feed — serverless build.

The full project calls the WOAH WAHIS 4 public API at request time (8s timeout
per endpoint, two endpoints). On Vercel that risks blowing the function time
budget on a cold start, so live polling is DISABLED by default here and the
engine simply sees "no active outbreaks" (max_severity = "none").

To enable live polling on Vercel, set the env var  SKYWASTE_ENABLE_WAHIS=1
(and be mindful of the function maxDuration in vercel.json).

Same public surface as the full module: `async def get_live_outbreaks(country)`.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from skywaste.observability.logging import get_logger
from skywaste.optimization.models import OutbreakSummary

logger = get_logger("WAHIS-Live")

_WAHIS_BASE = "https://wahis.woah.org/api/v1"

_HIGH_RISK_DISEASES = {
    "african swine fever", "asf",
    "foot and mouth disease", "fmd",
    "highly pathogenic avian influenza", "hpai", "avian influenza",
    "newcastle disease", "classical swine fever", "csf",
    "rinderpest", "lumpy skin disease",
    "peste des petits ruminants", "ppr", "swine vesicular disease",
}


def _enabled() -> bool:
    return os.getenv("SKYWASTE_ENABLE_WAHIS", "0").lower() in ("1", "true", "yes")


def _classify_severity(disease_name: str) -> str:
    name_lc = (disease_name or "").lower()
    if any(k in name_lc for k in _HIGH_RISK_DISEASES):
        return "high"
    if any(k in name_lc for k in ("influenza", "fever", "plague", "pox")):
        return "medium"
    return "low"


def _max_severity(severities: List[str]) -> str:
    rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    best = "none"
    for s in severities:
        if rank.get(s, 0) > rank.get(best, 0):
            best = s
    return best


async def get_live_outbreaks(country_code: str) -> Tuple[List[OutbreakSummary], str]:
    """
    Return (outbreaks, max_severity). Disabled by default → ([], "none").
    Never raises: any failure degrades gracefully to no-outbreaks.
    """
    code = (country_code or "").upper().strip()
    if not code or code == "??" or not _enabled():
        return [], "none"

    try:
        import httpx  # imported lazily so the dep is optional

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=180)
        url = f"{_WAHIS_BASE}/public/event/country/{code}"
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                params={"pageSize": 50},
                headers={"Accept": "application/json", "User-Agent": "SkyWaste-AI/1.0"},
            )
            if r.status_code != 200:
                return [], "none"
            data = r.json()
            rows = data.get("data") if isinstance(data, dict) else (data or [])
            outbreaks: List[OutbreakSummary] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                d = row.get("disease") or row.get("diseaseName") or row.get("name") or {}
                name = d.get("nameClear") or d.get("name") if isinstance(d, dict) else str(d)
                name = name or "Unknown Disease"
                outbreaks.append(
                    OutbreakSummary(disease=name, severity=_classify_severity(name), country=code)
                )
            return outbreaks, _max_severity([o.severity for o in outbreaks])
    except Exception as e:
        logger.debug(f"[WAHIS-Live] disabled/failed for {country_code}: {e}")
        return [], "none"
