"""
Meal-based flight data intake.

The catering partner reports two numbers per flight — passengers boarded and
meals prepared — and (later) a third: meals returned/uneaten. This module bridges
those COUNTS into the kg-based world the engine works in, and derives the
operational signals:

  * with 2 numbers (boarded + prepared): meals/pax, prepared weight, and — once
    the engine recommendation is known — the over-preparation gap.
  * with the 3rd number (returned): actual waste/pax (the real ICW), consumption
    rate, and the model-feedback delta that closes the loop.

`kg_per_meal` defaults to 1.2 kg/tray (the ratio used across the project).
"""
from __future__ import annotations

from typing import Optional

KG_PER_MEAL = 1.2
IATA_AVG_WASTE_KG_PER_PAX = 1.43


def process_flight_record(
    passengers_boarded: int,
    meals_prepared: int,
    meals_returned: Optional[int] = None,
    kg_per_meal: float = KG_PER_MEAL,
) -> dict:
    pax = max(int(passengers_boarded), 1)
    prepared = max(int(meals_prepared), 0)

    rec: dict = {
        "passengers_boarded": pax,
        "meals_prepared": prepared,
        "meals_per_pax": round(prepared / pax, 2),
        "prepared_weight_kg": round(prepared * kg_per_meal, 1),
        "kg_per_meal": kg_per_meal,
        "loop_closed": False,
    }

    if meals_returned is not None:
        returned = max(int(meals_returned), 0)
        consumed = max(prepared - returned, 0)
        returned_kg = round(returned * kg_per_meal, 1)
        actual_per_pax = round(returned_kg / pax, 3)
        rec.update({
            "meals_returned": returned,
            "meals_consumed": consumed,
            "consumption_rate_pct": round(consumed / prepared * 100, 1) if prepared else 0.0,
            "returned_waste_weight_kg": returned_kg,
            "actual_waste_kg_per_pax": actual_per_pax,
            "loop_closed": True,
            "model_feedback": {
                "predicted_kg_per_pax": IATA_AVG_WASTE_KG_PER_PAX,
                "actual_kg_per_pax": actual_per_pax,
                "delta_kg_per_pax": round(actual_per_pax - IATA_AVG_WASTE_KG_PER_PAX, 3),
            },
        })

    return rec


def record_to_measurement(rec: dict) -> Optional[dict]:
    """Adapt a loop-closed flight record into the measurement dict build_manifest expects."""
    if not rec.get("loop_closed"):
        return None
    return {
        "uplift_weight_kg": rec["prepared_weight_kg"],
        "returned_waste_weight_kg": rec["returned_waste_weight_kg"],
        "consumed_weight_kg": round(rec["prepared_weight_kg"] - rec["returned_waste_weight_kg"], 1),
        "actual_waste_kg_per_pax": rec["actual_waste_kg_per_pax"],
        "method": "meal_count_reconciliation",
        "operator_id": None,
        "device_id": None,
        "captured_at_utc": None,
    }
