"""
SkyWaste Optimization API — Vercel serverless entrypoint.

Exposes the ICW buffer optimization engine as a REST API. Vercel's Python
runtime auto-detects the ASGI `app` object below and routes every /api/* request
to it (see vercel.json rewrite).

Routes are prefixed with /api so they sit behind the same origin as the static
frontend in /public — no CORS, mobile-friendly.

    GET  /api/health             liveness
    GET  /api/airports           reference airports + disposal costs
    POST /api/optimize/flight    single-flight buffer recommendation
    POST /api/optimize/route     aggregate + annualised savings
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from typing import List, Optional

# Make the repo-root `skywaste` package importable when running as a Vercel
# function (this file lives in /var/task/api/index.py → root is one level up).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from skywaste.compliance import build_manifest, verify_manifest
from skywaste.db import DBClient
from skywaste.optimization import (
    FlightInput,
    OptimizationEngine,
    OptimizationResult,
    RouteOptimizationSummary,
)

app = FastAPI(
    title="SkyWaste Optimization API",
    description="Per-flight International Catering Waste (ICW) buffer calculator.",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One engine per warm container (stateless calculator; DBClient is None on Vercel).
_engine = OptimizationEngine(DBClient())


# ── Request models ──────────────────────────────────────────────────────────

class FlightRequest(BaseModel):
    flight_number: str = Field(..., examples=["LY001"])
    origin_airport: str = Field(..., min_length=3, max_length=3, examples=["TLV"])
    destination_airport: str = Field(..., min_length=3, max_length=3, examples=["JFK"])
    departure_date: date = Field(..., examples=["2026-06-15"])
    aircraft_type: str = Field(..., examples=["B789"])
    passenger_count: int = Field(..., gt=0, examples=[280])
    route_distance_km: float = Field(..., gt=0, examples=[9100.0])
    historical_waste_kg_per_pax: Optional[float] = Field(default=None, examples=[1.35])

    def to_input(self) -> FlightInput:
        return FlightInput(
            flight_number=self.flight_number,
            origin_airport=self.origin_airport,
            destination_airport=self.destination_airport,
            departure_date=self.departure_date,
            aircraft_type=self.aircraft_type,
            passenger_count=self.passenger_count,
            route_distance_km=self.route_distance_km,
            historical_waste_kg_per_pax=self.historical_waste_kg_per_pax,
        )


class RouteRequest(BaseModel):
    origin_airport: str = Field(..., min_length=3, max_length=3)
    destination_airport: str = Field(..., min_length=3, max_length=3)
    flights: List[FlightRequest] = Field(..., min_length=1)


class ManifestRequest(BaseModel):
    flight: FlightRequest
    previous_manifest_hash: Optional[str] = None
    custody_chain: Optional[List[dict]] = None


class ManifestVerifyRequest(BaseModel):
    manifest: dict


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "service": "skywaste-optimization-api",
        "version": "1.0.0",
        "mode": "supabase" if _engine.db.client else "stateless",
    }


@app.get("/api/airports", tags=["Reference"])
async def list_airports():
    airports = {
        "JFK": {"country": "US", "disposal_cost_usd_per_ton": 500.0, "abp_regime": "USDA APHIS Cat1"},
        "LHR": {"country": "GB", "disposal_cost_usd_per_ton": 400.0, "abp_regime": "UK DEFRA Cat1"},
        "CDG": {"country": "FR", "disposal_cost_usd_per_ton": 350.0, "abp_regime": "EU ABP 1069/2009"},
        "FRA": {"country": "DE", "disposal_cost_usd_per_ton": 330.0, "abp_regime": "EU ABP 1069/2009"},
        "AMS": {"country": "NL", "disposal_cost_usd_per_ton": 125.0, "abp_regime": "EU ABP 1069/2009"},
        "TLV": {"country": "IL", "disposal_cost_usd_per_ton": 280.0, "abp_regime": "Israeli MOA Cat1"},
        "DXB": {"country": "AE", "disposal_cost_usd_per_ton": 195.0, "abp_regime": "MOCCAE"},
        "SIN": {"country": "SG", "disposal_cost_usd_per_ton": 360.0, "abp_regime": "AVA Cat1"},
        "ORD": {"country": "US", "disposal_cost_usd_per_ton": 500.0, "abp_regime": "USDA APHIS Cat1"},
    }
    return {"airports": airports, "count": len(airports)}


@app.get("/api/bts/routes", tags=["Reference"])
async def bts_routes():
    """
    Real route stats ingested from the BTS T-100 Segment dataset (TranStats).

    Returns avg passengers/flight, distance, and dominant aircraft per route, ready
    to feed POST /api/optimize/flight. Until a CSV is ingested (see
    scripts/ingest_bts_t100.py) this returns an empty list with ingested=false.
    """
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "skywaste", "optimization", "data", "bts_routes.json",
    )
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"source": "BTS T-100 Segment", "ingested": False, "route_count": 0, "routes": []}


@app.post("/api/optimize/flight", response_model=OptimizationResult, tags=["Optimization"])
async def optimize_flight(req: FlightRequest) -> OptimizationResult:
    try:
        return await _engine.optimize_flight(req.to_input())
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/optimize/route", response_model=RouteOptimizationSummary, tags=["Optimization"])
async def optimize_route(req: RouteRequest) -> RouteOptimizationSummary:
    try:
        return await _engine.optimize_route(
            origin=req.origin_airport,
            destination=req.destination_airport,
            sample_flights=[f.to_input() for f in req.flights],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manifest/flight", tags=["Compliance"])
async def manifest_flight(req: ManifestRequest):
    """
    Generate an ICW chain-of-custody disposal manifest for a flight.

    Runs the optimization engine, then composes a structured ABP Category-1
    disposal manifest (classification, quantity, custody chain, carbon record)
    with a tamper-evident SHA-256 hash that chains to `previous_manifest_hash`.

    NOTE: structural template — validate mandatory fields with a regulatory
    advisor before operational use. Modeled/pending fields are flagged as such.
    """
    flight_input = req.flight.to_input()
    try:
        result = await _engine.optimize_flight(flight_input)
        return build_manifest(
            flight_input,
            result,
            previous_manifest_hash=req.previous_manifest_hash,
            custody_chain=req.custody_chain,
        )
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manifest/verify", tags=["Compliance"])
async def manifest_verify(req: ManifestVerifyRequest):
    """Recompute the tamper-evident hash and report whether a manifest is intact."""
    return verify_manifest(req.manifest)
