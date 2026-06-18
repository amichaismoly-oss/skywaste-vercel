"""
ICW chain-of-custody manifest generator.

Builds a structured disposal manifest for International Catering Waste (ICW)
derived from an OptimizationResult. The manifest models the chain of custody an
ABP Category-1 disposal must document (carrier -> approved transporter ->
approved incineration facility) plus a carbon record and a tamper-evident hash
chain.

IMPORTANT — this is a STRUCTURAL TEMPLATE, not a certified legal document. The
exact mandatory fields under EU ABP Regulation (EC) 1069/2009 + 142/2011 (and
each destination's national rules) must be validated with a regulatory advisor
before any operational use. Fields we cannot yet source from real measurement
(measured leftover weight, partner signatures) are explicitly marked `modeled`
or `pending` — the generator never fabricates "measured" provenance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, List, Optional

JET_FUEL_CO2_FACTOR = 3.16  # kg CO2 per kg jet fuel (mirror of engine constant)

# ICW category code -> ABP numeric category.
_CATEGORY_NUM = {"cat1": 1, "cat2": 2, "cat3": 3, "unknown": 1}


def _normalize_numbers(o: Any) -> Any:
    """
    Normalize integer-valued floats to ints so the hash is stable across a JSON
    round-trip. JavaScript's JSON.stringify renders 9100.0 as "9100" (no trailing
    .0), so a manifest that passes through the browser would otherwise hash
    differently than the server-built one. Non-integer floats round-trip
    identically in both Python and JS (shortest-repr), so they're left as-is.
    """
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        return int(o) if o.is_integer() else o
    if isinstance(o, dict):
        return {k: _normalize_numbers(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_normalize_numbers(v) for v in o]
    return o


def _canonical_hash(obj: Any) -> str:
    """Deterministic SHA-256 over a JSON-canonical form (sorted keys, normalized numbers)."""
    canon = json.dumps(_normalize_numbers(obj), sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _dump(o: Any) -> Any:
    """Best-effort dict for pydantic models / plain objects."""
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "dict"):
        return o.dict()
    return o


def build_manifest(
    flight: Any,
    result: Any,
    previous_manifest_hash: Optional[str] = None,
    custody_chain: Optional[List[dict]] = None,
    generated_at: Optional[str] = None,
    measurement: Optional[dict] = None,
) -> dict:
    """
    Build an ICW disposal manifest from a FlightInput + OptimizationResult.

    `previous_manifest_hash` links this manifest to the prior one (the tamper-
    evident chain). `custody_chain`, when provided, carries real signed handover
    steps; otherwise the chain is left empty and flagged `pending`.
    """
    arr = result.destination_airport
    dep = result.origin_airport
    date_str = result.departure_date.isoformat()
    cat_num = _CATEGORY_NUM.get(result.icw_category, 1)
    fuel_saved_kg = round(result.co2_saved_kg / JET_FUEL_CO2_FACTOR, 2) if result.co2_saved_kg else 0.0

    if measurement:
        # Real weighing event: measured provenance replaces the model estimate.
        quantity = {
            "uplift_weight_kg": measurement["uplift_weight_kg"],
            "returned_waste_weight_kg": measurement["returned_waste_weight_kg"],
            "consumed_weight_kg": measurement["consumed_weight_kg"],
            "disposal_weight_kg": measurement["returned_waste_weight_kg"],
            "waste_per_pax_kg": measurement["actual_waste_kg_per_pax"],
            "measurement_method": measurement.get("method", "trolley_scale"),
            "measurement_confidence": "measured",
            "measured_by": measurement.get("operator_id"),
            "device_id": measurement.get("device_id"),
            "captured_at_utc": measurement.get("captured_at_utc"),
        }
    else:
        quantity = {
            "uplift_weight_kg": result.current_buffer_kg,
            "recommended_disposal_weight_kg": result.optimized_buffer_kg,
            "buffer_reduction_kg": result.buffer_reduction_kg,
            "waste_per_pax_kg": result.waste_per_pax_kg,
            "measurement_method": "model_estimate",
            "measurement_confidence": "modeled",
            "_note": (
                "Operational manifests must replace this with measured trolley-differential "
                "weights (uplift vs. returned)."
            ),
        }

    manifest = {
        "manifest_id": f"ICW-{arr}-{date_str.replace('-', '')}-{flight.flight_number}-001",
        "manifest_version": "1.0",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
        "regulatory_regime": result.abp_regime or "UNSPECIFIED",
        "regulatory_status": (
            "DRAFT — structural template. Mandatory fields must be validated against the "
            "destination competent authority (EU ABP 1069/2009 + 142/2011 or national equivalent) "
            "before operational use."
        ),
        "source": {
            "flight_number": flight.flight_number,
            "aircraft_type": flight.aircraft_type,
            "origin_airport_iata": dep,
            "destination_airport_iata": arr,
            "destination_country": result.destination_country,
            "departure_date": date_str,
        },
        "waste_classification": {
            "abp_category": cat_num,
            "icw_category_code": result.icw_category,
            "category_justification": (
                f"International catering waste containing products of animal origin; "
                f"destination {result.destination_country} under {result.abp_regime}."
            ),
            "contains_animal_products": True,
            "regulatory_risk_level": result.regulatory_risk_level,
            "active_outbreaks": [_dump(o) for o in (result.active_outbreaks or [])],
        },
        "quantity": quantity,
        "custody_chain": custody_chain or [],
        "custody_chain_status": "provided" if custody_chain else "pending",
        "carbon_record": {
            "weight_reduction_kg": result.buffer_reduction_kg,
            "methodology": "ICAO_fuel_burn_per_kg_payload",
            "route_distance_km": flight.route_distance_km,
            "fuel_saved_kg": fuel_saved_kg,
            "co2_saved_kg": result.co2_saved_kg,
            "co2_saved_tons": result.co2_saved_tons,
            "corsia_reportable": True,
        },
        "audit": {
            "data_sources": list(result.data_sources or []),
            "generated_by": "SkyWaste Engine v1.0",
            "confidence_level": result.confidence_level,
            "previous_manifest_hash": previous_manifest_hash,
        },
    }

    # Tamper-evident hash covers the entire manifest as composed above.
    manifest["audit"]["tamper_evident_hash"] = _canonical_hash(manifest)
    return manifest


def verify_manifest(manifest: dict) -> dict:
    """
    Recompute the tamper-evident hash and report whether the manifest is intact.
    Returns {valid: bool, expected_hash, stored_hash}.
    """
    m = json.loads(json.dumps(manifest))  # deep copy
    stored = m.get("audit", {}).pop("tamper_evident_hash", None)
    expected = _canonical_hash(m)
    return {"valid": stored == expected, "expected_hash": expected, "stored_hash": stored}
