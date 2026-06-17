"""
Pydantic models for the optimization engine.

FlightInput  → what the caller provides per flight
OptimizationResult → what the engine returns
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────
#  Constants (IATA / industry benchmarks)
# ──────────────────────────────────────────────────────────

IATA_AVG_WASTE_KG_PER_PAX: float = 1.43          # kg of ICW per passenger
AIRLINE_DEFAULT_BUFFER_RATE: float = 0.10         # 10% uniform buffer airlines use today
DEFAULT_FUEL_COST_USD_PER_KG: float = 0.82        # Jet-A average 2024 USD/kg
FUEL_BURN_KG_PER_PAX_PER_KM: float = 0.000045    # kg fuel to carry 1 kg of cargo 1 km
CORSIA_CARBON_PRICE_USD_PER_TON: float = 23.0     # CORSIA Phase 1 ~$23/tCO2
JET_FUEL_CO2_FACTOR: float = 3.16                 # kg CO2 per kg jet fuel burned
REVENUE_SHARE_RATE: float = 0.275                 # 27.5% midpoint of 25-30%

# ABP category → minimum regulatory overhead we must keep above bare waste weight
ABP_REGULATORY_OVERHEAD: Dict[str, float] = {
    "cat1": 0.05,   # Highest-risk material — keep 5% safety margin
    "cat2": 0.03,
    "cat3": 0.02,
    "unknown": 0.06,  # Fail-safe: assume worst-case
}

# Outbreak severity at destination → extra buffer we must carry
OUTBREAK_BUFFER_OVERHEAD: Dict[str, float] = {
    "high":   0.08,
    "medium": 0.04,
    "low":    0.01,
    "none":   0.00,
}


# ──────────────────────────────────────────────────────────
#  Input
# ──────────────────────────────────────────────────────────

class CabinBreakdown(BaseModel):
    """Passenger count per cabin class."""
    economy:  int = 0
    business: int = 0
    first:    int = 0

    @property
    def total(self) -> int:
        return self.economy + self.business + self.first


class FlightInput(BaseModel):
    """Everything the caller must provide for a single flight optimisation."""
    flight_number:      str
    origin_airport:     str = Field(..., min_length=3, max_length=3, description="IATA 3-letter origin code")
    destination_airport: str = Field(..., min_length=3, max_length=3, description="IATA 3-letter destination code")
    departure_date:     date
    aircraft_type:      str = Field(..., description="e.g. B737, A320, B777")
    passenger_count:    int = Field(..., gt=0)
    route_distance_km:  float = Field(..., gt=0)
    cabin_breakdown:    Optional[CabinBreakdown] = None
    # Optional: override the IATA average if the airline has its own history
    historical_waste_kg_per_pax: Optional[float] = Field(
        default=None,
        description="Airline-specific historical average. Falls back to IATA 1.43 kg if not provided."
    )


# ──────────────────────────────────────────────────────────
#  Output
# ──────────────────────────────────────────────────────────

class OutbreakSummary(BaseModel):
    disease:  str
    severity: str
    country:  str


class SavingsBreakdown(BaseModel):
    """Line-item breakdown of where the savings come from."""
    disposal_savings_usd: float = Field(description="Less waste to dispose at destination")
    fuel_savings_usd:     float = Field(description="Less fuel burned carrying excess weight")
    corsia_savings_usd:   float = Field(description="CORSIA carbon credit value of fuel saved")
    total_savings_usd:    float


class OptimizationResult(BaseModel):
    """Full result for a single flight optimisation."""

    # ── Identification ──────────────────────────────────────
    flight_number:       str
    origin_airport:      str
    destination_airport: str
    departure_date:      date

    # ── Buffer recommendations ───────────────────────────────
    waste_per_pax_kg:      float = Field(description="Baseline waste per passenger used")
    current_buffer_kg:     float = Field(description="What the airline currently loads (10% buffer)")
    optimized_buffer_kg:   float = Field(description="Our recommended buffer")
    buffer_reduction_kg:   float = Field(description="Reduction vs current practice")
    buffer_reduction_pct:  float = Field(description="Reduction as % of current buffer")

    # ── Financial ───────────────────────────────────────────
    disposal_cost_per_ton_usd: float
    savings:               SavingsBreakdown
    revenue_share_usd:     float = Field(description="Platform fee at 27.5% of total savings")
    airline_net_saving_usd: float = Field(description="Airline keeps 72.5% of total savings")

    # ── Regulatory & Risk ────────────────────────────────────
    destination_country:   str
    icw_category:          str          # cat1 / cat2 / cat3 / unknown
    abp_regime:            Optional[str]
    active_outbreaks:      List[OutbreakSummary] = []
    max_outbreak_severity: str = "none"  # none / low / medium / high
    regulatory_risk_level: str           # low / medium / high

    # ── ESG ─────────────────────────────────────────────────
    co2_saved_kg:          float
    co2_saved_tons:        float

    # ── Metadata ─────────────────────────────────────────────
    confidence_level:      str           # verified / inferred / stale
    data_sources:          List[str]
    calculated_at:         datetime


class RouteOptimizationSummary(BaseModel):
    """Aggregate result for an entire route (multiple flights)."""
    origin_airport:      str
    destination_airport: str
    flights_analyzed:    int
    total_savings_usd:   float
    revenue_share_usd:   float
    avg_buffer_reduction_pct: float
    total_co2_saved_tons: float
    annualized_savings_usd: float   # projected savings if route runs daily for 365 days
    annualized_revenue_share_usd: float
    results:             List[OptimizationResult]
