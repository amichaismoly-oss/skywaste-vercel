"""
Post-flight consumption measurement — the layer that closes the loop.

When a flight lands, the returned catering trolleys are weighed against what was
uplifted. That single measurement event produces the real `kg of waste per
passenger`, which flows to THREE places:

  1. The disposal manifest   → real `measured` quantity (replaces the model estimate)
  2. The optimizer           → fed back as FlightInput.historical_waste_kg_per_pax,
                               so the next recommendation is airline/route-specific
  3. Model training          → the actual-vs-predicted delta is the training label

This module computes the derived metrics from a raw measurement. It is pure and
storage-agnostic (the API decides where the record is persisted).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

IATA_AVG_WASTE_KG_PER_PAX = 1.43  # default prediction the measurement corrects


def process_measurement(
    uplift_weight_kg: float,
    returned_waste_weight_kg: float,
    passenger_count: int,
    *,
    method: str = "trolley_scale",
    operator_id: Optional[str] = None,
    device_id: Optional[str] = None,
    captured_at_utc: Optional[str] = None,
) -> dict:
    """
    Derive consumption metrics + model-feedback from one weighing event.

    `returned_waste_weight_kg` is the measured ICW to dispose (the real number the
    regulator and the carbon record both depend on).
    """
    uplift = max(float(uplift_weight_kg), 0.0)
    returned = max(float(returned_waste_weight_kg), 0.0)
    pax = max(int(passenger_count), 1)

    consumed = round(max(uplift - returned, 0.0), 2)
    actual_per_pax = round(returned / pax, 3)
    predicted_per_pax = IATA_AVG_WASTE_KG_PER_PAX
    delta = round(actual_per_pax - predicted_per_pax, 3)
    consumption_rate_pct = round(consumed / uplift * 100, 1) if uplift > 0 else 0.0

    return {
        "captured_at_utc": captured_at_utc or datetime.now(timezone.utc).isoformat(),
        "method": method,
        "operator_id": operator_id,
        "device_id": device_id,
        "passenger_count": pax,
        "uplift_weight_kg": round(uplift, 2),
        "returned_waste_weight_kg": round(returned, 2),
        "consumed_weight_kg": consumed,
        "consumption_rate_pct": consumption_rate_pct,
        "actual_waste_kg_per_pax": actual_per_pax,
        "model_feedback": {
            "predicted_kg_per_pax": predicted_per_pax,
            "actual_kg_per_pax": actual_per_pax,
            "delta_kg_per_pax": delta,
            "direction": "below_prediction" if delta < 0 else ("above_prediction" if delta > 0 else "on_prediction"),
            "note": (
                "actual_waste_kg_per_pax becomes this airline/route's historical baseline: "
                "fed back into the optimizer (FlightInput.historical_waste_kg_per_pax) and "
                "used as the supervised training label that replaces the IATA average."
            ),
        },
    }
