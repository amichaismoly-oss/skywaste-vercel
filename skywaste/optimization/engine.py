"""
OptimizationEngine — core per-flight ICW buffer calculator.

For every flight it:
  1. Pulls destination airport data (disposal cost, ABP regime) from the DB
  2. Pulls active disease outbreaks at the destination country from the DB
  3. Pulls the strictest regulatory rule that applies to the destination
  4. Calculates the optimal buffer vs the airline's current 10% uniform buffer
  5. Returns full savings breakdown + revenue share
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from skywaste.db import DBClient
from skywaste.observability.logging import get_logger
from skywaste.optimization.data.airports import get_airport_info
from skywaste.optimization.data.disposal_costs import get_disposal_cost, get_abp_regime
from skywaste.optimization.data.wahis_live import get_live_outbreaks
from skywaste.optimization.models import (
    ABP_REGULATORY_OVERHEAD,
    AIRLINE_DEFAULT_BUFFER_RATE,
    CORSIA_CARBON_PRICE_USD_PER_TON,
    DEFAULT_FUEL_COST_USD_PER_KG,
    FUEL_BURN_KG_PER_PAX_PER_KM,
    IATA_AVG_WASTE_KG_PER_PAX,
    JET_FUEL_CO2_FACTOR,
    OUTBREAK_BUFFER_OVERHEAD,
    REVENUE_SHARE_RATE,
    FlightInput,
    OptimizationResult,
    OutbreakSummary,
    RouteOptimizationSummary,
    SavingsBreakdown,
)

logger = get_logger("OptimizationEngine")


class OptimizationEngine:
    """
    Stateless calculator — all DB I/O goes through the injected DBClient.
    Can be used from the CLI, the FastAPI endpoint, or tests.
    """

    def __init__(self, db: DBClient):
        self.db = db

    # ──────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────

    async def optimize_flight(self, flight: FlightInput) -> OptimizationResult:
        """Calculate the optimal ICW buffer and savings for a single flight."""
        logger.info(
            f"[Engine] Optimizing {flight.flight_number}: "
            f"{flight.origin_airport}->{flight.destination_airport} "
            f"({flight.passenger_count} pax)"
        )

        # 1. Fetch destination airport data
        airport_data   = await self._get_airport(flight.destination_airport)
        country_code   = airport_data.get("country_code", "??").upper()
        disposal_cost  = self._cents_to_usd(airport_data.get("disposal_cost_cents_per_ton") or 0)
        abp_regime     = airport_data.get("abp_regime")
        data_sources: List[str] = []

        # Determine data source and confidence
        _src = airport_data.get("_source", "")
        if self.db.client and airport_data.get("disposal_cost_cents_per_ton"):
            confidence = "verified"
            data_sources.append(f"disposal_cost:{flight.destination_airport}:supabase")
        elif "ourairports" in _src:
            cost_conf = _src.split(":")[-1] if ":" in _src else "estimated"
            confidence = cost_conf       # 'researched' | 'regional_estimate'
            data_sources.append(f"disposal_cost:{country_code}:OurAirports+costDB")
        elif disposal_cost > 0:
            confidence = "verified"
            data_sources.append(f"disposal_cost:{flight.destination_airport}:benchmark")
        else:
            # No cost found → global average fallback
            disposal_cost = 312.5
            confidence    = "inferred"
            data_sources.append("disposal_cost:global_average_fallback")

        # 2. Determine ABP category (strictest rule that applies)
        icw_category = await self._get_icw_category(country_code)
        icw_source   = "supabase" if self.db.client else "costDB"
        data_sources.append(f"icw_category:{country_code}:{icw_source}")

        # 3. Active outbreaks at destination
        outbreaks, max_severity = await self._get_outbreaks(country_code)
        outbreak_source = "supabase" if self.db.client else "WAHIS-live"
        if outbreaks:
            data_sources.append(f"outbreaks:{country_code}:{outbreak_source}")
        else:
            data_sources.append(f"outbreaks:{country_code}:{outbreak_source}:none")

        # 4. Baseline waste
        waste_per_pax = flight.historical_waste_kg_per_pax or IATA_AVG_WASTE_KG_PER_PAX
        base_waste_kg = waste_per_pax * flight.passenger_count

        # 5. Buffers
        current_buffer_kg   = base_waste_kg * (1 + AIRLINE_DEFAULT_BUFFER_RATE)
        optimized_buffer_kg = self._calc_optimized_buffer(
            base_waste_kg, icw_category, max_severity
        )

        # Ensure we never recommend less than base waste (floor = 100% of base)
        optimized_buffer_kg = max(optimized_buffer_kg, base_waste_kg)

        reduction_kg  = current_buffer_kg - optimized_buffer_kg
        reduction_pct = (reduction_kg / current_buffer_kg * 100) if current_buffer_kg > 0 else 0.0

        # 6. Savings
        savings = self._calc_savings(
            reduction_kg, disposal_cost, flight.route_distance_km, flight.passenger_count
        )

        # 7. Revenue split
        revenue_share      = savings.total_savings_usd * REVENUE_SHARE_RATE
        airline_net_saving = savings.total_savings_usd - revenue_share

        # 8. ESG
        fuel_saved_kg  = self._fuel_saved_kg(reduction_kg, flight.route_distance_km, flight.passenger_count)
        co2_saved_kg   = fuel_saved_kg * JET_FUEL_CO2_FACTOR

        # 9. Regulatory risk level (for the result card)
        reg_risk = self._regulatory_risk(icw_category, max_severity)

        result = OptimizationResult(
            flight_number          = flight.flight_number,
            origin_airport         = flight.origin_airport.upper(),
            destination_airport    = flight.destination_airport.upper(),
            departure_date         = flight.departure_date,
            waste_per_pax_kg       = waste_per_pax,
            current_buffer_kg      = round(current_buffer_kg, 2),
            optimized_buffer_kg    = round(optimized_buffer_kg, 2),
            buffer_reduction_kg    = round(reduction_kg, 2),
            buffer_reduction_pct   = round(reduction_pct, 1),
            disposal_cost_per_ton_usd = round(disposal_cost, 2),
            savings                = SavingsBreakdown(
                disposal_savings_usd = round(savings.disposal_savings_usd, 2),
                fuel_savings_usd     = round(savings.fuel_savings_usd, 2),
                corsia_savings_usd   = round(savings.corsia_savings_usd, 2),
                total_savings_usd    = round(savings.total_savings_usd, 2),
            ),
            revenue_share_usd      = round(revenue_share, 2),
            airline_net_saving_usd = round(airline_net_saving, 2),
            destination_country    = country_code,
            icw_category           = icw_category,
            abp_regime             = abp_regime,
            active_outbreaks       = outbreaks,
            max_outbreak_severity  = max_severity,
            regulatory_risk_level  = reg_risk,
            co2_saved_kg           = round(co2_saved_kg, 2),
            co2_saved_tons         = round(co2_saved_kg / 1000, 4),
            confidence_level       = confidence,
            data_sources           = data_sources,
            calculated_at          = datetime.now(timezone.utc),
        )

        logger.info(
            f"[Engine] {flight.flight_number}: save {reduction_kg:.1f} kg | "
            f"${savings.total_savings_usd:.0f} total | "
            f"${revenue_share:.0f} revenue share"
        )
        return result

    async def optimize_route(
        self,
        origin: str,
        destination: str,
        sample_flights: List[FlightInput],
    ) -> RouteOptimizationSummary:
        """
        Aggregate optimization across multiple flights on the same route.
        Pass a list of representative flights (e.g. one per day for 7 days)
        and get annualised projections.
        """
        results = []
        for f in sample_flights:
            results.append(await self.optimize_flight(f))

        n = len(results)
        if n == 0:
            raise ValueError("No flights provided for route optimisation.")

        total_savings      = sum(r.savings.total_savings_usd for r in results)
        total_rev_share    = sum(r.revenue_share_usd for r in results)
        avg_reduction_pct  = sum(r.buffer_reduction_pct for r in results) / n
        total_co2          = sum(r.co2_saved_tons for r in results)

        # Annualise: assume route runs once per day (365 days)
        days_per_year       = 365
        days_in_sample      = n
        daily_avg_savings   = total_savings / days_in_sample
        daily_avg_rev_share = total_rev_share / days_in_sample

        return RouteOptimizationSummary(
            origin_airport               = origin.upper(),
            destination_airport          = destination.upper(),
            flights_analyzed             = n,
            total_savings_usd            = round(total_savings, 2),
            revenue_share_usd            = round(total_rev_share, 2),
            avg_buffer_reduction_pct     = round(avg_reduction_pct, 1),
            total_co2_saved_tons         = round(total_co2, 4),
            annualized_savings_usd       = round(daily_avg_savings * days_per_year, 0),
            annualized_revenue_share_usd = round(daily_avg_rev_share * days_per_year, 0),
            results                      = results,
        )

    # ──────────────────────────────────────────────────────
    #  Private helpers
    # ──────────────────────────────────────────────────────

    async def _get_airport(self, airport_code: str) -> dict:
        """
        Fetch airport data.
        Priority:
          1. Supabase DB (when connected)
          2. OurAirports open dataset (90k+ airports) + country cost table
          3. Hard-coded fallback for 8 benchmark airports
        """
        code = airport_code.upper()

        # ── 1. Supabase ─────────────────────────────────────────────────────
        if self.db.client:
            resp = self.db.client.table("airports").select("*").eq("airport_code", code).execute()
            if resp.data:
                return resp.data[0]

        # ── 2. OurAirports + country cost table ─────────────────────────────
        try:
            info = await get_airport_info(code)
            if info and info.get("country_code") and info["country_code"] != "??":
                country = info["country_code"]
                continent = info.get("continent", "")
                cost_usd, cost_confidence = get_disposal_cost(country, continent)
                icw_cat, regime_name = get_abp_regime(country)
                return {
                    "country_code":               country,
                    "continent":                  continent,
                    "disposal_cost_cents_per_ton": int(cost_usd * 100),
                    "abp_regime":                 regime_name,
                    "cost_currency":              "USD",
                    "_source":                    f"ourairports+costs:{cost_confidence}",
                }
        except Exception as e:
            logger.warning(f"[Engine] OurAirports lookup failed for {code}: {e}")

        # ── 3. Hard-coded benchmark fallback ────────────────────────────────
        BENCHMARK: dict[str, dict] = {
            "JFK": {"country_code": "US", "disposal_cost_cents_per_ton": 50000, "abp_regime": "USDA APHIS 7 CFR 330",    "cost_currency": "USD"},
            "LHR": {"country_code": "GB", "disposal_cost_cents_per_ton": 40000, "abp_regime": "UK DEFRA ABP Regs 2013",  "cost_currency": "USD"},
            "CDG": {"country_code": "FR", "disposal_cost_cents_per_ton": 35000, "abp_regime": "EU Regulation 1069/2009", "cost_currency": "USD"},
            "TLV": {"country_code": "IL", "disposal_cost_cents_per_ton": 28000, "abp_regime": "Israeli MOA Ordinance",   "cost_currency": "USD"},
            "EWR": {"country_code": "US", "disposal_cost_cents_per_ton": 48000, "abp_regime": "USDA APHIS 7 CFR 330",    "cost_currency": "USD"},
            "YYZ": {"country_code": "CA", "disposal_cost_cents_per_ton": 32000, "abp_regime": "CFIA Health of Animals Act","cost_currency": "USD"},
            "FRA": {"country_code": "DE", "disposal_cost_cents_per_ton": 33000, "abp_regime": "EU Regulation 1069/2009", "cost_currency": "USD"},
            "AMS": {"country_code": "NL", "disposal_cost_cents_per_ton": 12500, "abp_regime": "EU Regulation 1069/2009", "cost_currency": "USD"},
        }
        return BENCHMARK.get(code, {
            "country_code": "??",
            "disposal_cost_cents_per_ton": None,
            "abp_regime": None,
            "cost_currency": "USD",
        })

    async def _get_icw_category(self, country_code: str) -> str:
        """
        Return the strictest ABP category that applies to the destination country.
        Priority: Supabase DB → country cost table → 'cat1' conservative default.
        """
        # ── Supabase ──────────────────────────────────────────────────────
        if self.db.client:
            resp = (
                self.db.client.table("regulatory_rules")
                .select("abp_category")
                .order("abp_category", desc=False)
                .execute()
            )
            if resp.data:
                return resp.data[0]["abp_category"]

        # ── Country table ──────────────────────────────────────────────────
        try:
            icw_cat, _ = get_abp_regime(country_code)
            return icw_cat
        except Exception:
            pass

        return "cat1"  # fail-safe: most restrictive

    async def _get_outbreaks(self, country_code: str):
        """
        Return active outbreaks at the destination country.
        Priority: Supabase DB → WAHIS live API → empty list.
        """
        # ── Supabase ──────────────────────────────────────────────────────
        if self.db.client:
            resp = (
                self.db.client.table("outbreaks")
                .select("disease,severity,country,status")
                .eq("country", country_code)
                .eq("status", "active")
                .execute()
            )
            rows = resp.data or []
            outbreaks = [
                OutbreakSummary(
                    disease  = r.get("disease", "Unknown"),
                    severity = r.get("severity", "low"),
                    country  = r.get("country", country_code),
                )
                for r in rows
            ]
        else:
            # ── WAHIS live API ─────────────────────────────────────────────
            outbreaks, _ = await get_live_outbreaks(country_code)

        severity_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
        max_severity  = "none"
        for ob in outbreaks:
            if severity_rank.get(ob.severity, 0) > severity_rank.get(max_severity, 0):
                max_severity = ob.severity

        return outbreaks, max_severity

    def _calc_optimized_buffer(
        self,
        base_waste_kg: float,
        icw_category: str,
        max_outbreak_severity: str,
    ) -> float:
        """
        Optimal buffer = base waste × (1 + regulatory_overhead + outbreak_overhead).
        Never exceeds the current 10% buffer (otherwise we'd recommend loading MORE).
        """
        reg_overhead      = ABP_REGULATORY_OVERHEAD.get(icw_category, ABP_REGULATORY_OVERHEAD["unknown"])
        outbreak_overhead = OUTBREAK_BUFFER_OVERHEAD.get(max_outbreak_severity, 0.0)
        rate              = 1.0 + reg_overhead + outbreak_overhead

        # Cap: never recommend more than the airline currently loads
        max_rate = 1.0 + AIRLINE_DEFAULT_BUFFER_RATE
        rate     = min(rate, max_rate)

        return base_waste_kg * rate

    def _calc_savings(
        self,
        reduction_kg: float,
        disposal_cost_usd_per_ton: float,
        route_distance_km: float,
        passenger_count: int,
    ) -> SavingsBreakdown:
        """Calculate three sources of savings from carrying less waste."""
        # 1. Disposal cost reduction
        disposal_savings = (reduction_kg / 1000) * disposal_cost_usd_per_ton

        # 2. Fuel savings — carrying less weight = burning less fuel
        fuel_saved_kg   = self._fuel_saved_kg(reduction_kg, route_distance_km, passenger_count)
        fuel_savings    = fuel_saved_kg * DEFAULT_FUEL_COST_USD_PER_KG

        # 3. CORSIA carbon savings
        co2_saved_kg     = fuel_saved_kg * JET_FUEL_CO2_FACTOR
        corsia_savings   = (co2_saved_kg / 1000) * CORSIA_CARBON_PRICE_USD_PER_TON

        return SavingsBreakdown(
            disposal_savings_usd = disposal_savings,
            fuel_savings_usd     = fuel_savings,
            corsia_savings_usd   = corsia_savings,
            total_savings_usd    = disposal_savings + fuel_savings + corsia_savings,
        )

    @staticmethod
    def _fuel_saved_kg(reduction_kg: float, distance_km: float, pax: int) -> float:
        """
        Fuel saving from carrying `reduction_kg` less over `distance_km`.
        We scale by pax because fuel burn per kg varies with total aircraft weight.
        """
        return reduction_kg * FUEL_BURN_KG_PER_PAX_PER_KM * distance_km

    @staticmethod
    def _regulatory_risk(icw_category: str, max_severity: str) -> str:
        score = {"cat1": 3, "cat2": 2, "cat3": 1, "unknown": 3}.get(icw_category, 3)
        score += {"high": 3, "medium": 2, "low": 1, "none": 0}.get(max_severity, 0)
        if score >= 5: return "high"
        if score >= 3: return "medium"
        return "low"

    @staticmethod
    def _cents_to_usd(cents: Optional[int]) -> float:
        """Convert integer cents to USD float. 0 if None."""
        if cents is None:
            return 0.0
        return cents / 100.0
