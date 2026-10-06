"""Saved costs and explicit recovered-metal scenarios. No grade-to-yield guesses."""
import hashlib
import math
import re
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database import get_user_profile, save_user_profile

LB_GRAMS = 453.59237
TROY_GRAMS = 31.1034768


def _d(value):
    return Decimal(str(value))


def _money(value):
    return float(_d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class InputModel(BaseModel):
    class Config:
        extra = "forbid"
        allow_inf_nan = False


class ProfileUpdate(InputModel):
    fuel_cost_per_mile: Optional[float] = Field(None, ge=0, le=1000)
    target_hourly_wage: Optional[float] = Field(None, ge=0, le=1000000)
    chemical_cost_per_lb: Optional[float] = Field(None, ge=0, le=1000000)


class ScrapData(InputModel):
    category: str = Field(max_length=64)
    subcategory: str = Field(max_length=64)
    grade_type: str = Field(max_length=64)
    gross_weight_lbs: float = Field(gt=0, le=100000000)


class RecoveredMetal(InputModel):
    metal: Literal["gold", "silver", "copper", "platinum", "palladium"]
    recovered_grams: float = Field(ge=0, le=1000000000)
    buyer_pay_percent: Optional[float] = Field(None, ge=0, le=100)


class RecoveryRequest(InputModel):
    scrap_data: ScrapData
    yield_basis: Literal["assumed", "measured"] = "assumed"
    recovered_metals: List[RecoveredMetal] = Field(default_factory=list, max_length=5)
    # Always one-way miles. Blank is unknown; an explicit zero means no trip.
    distance_miles: Optional[float] = Field(None, ge=0, le=1000000)
    labor_hours_invested: Optional[float] = Field(None, ge=0, le=1000000)
    # Material actually processed, not an assumed percentage of the load.
    processing_weight_lbs: Optional[float] = Field(None, ge=0, le=100000000)
    other_costs: Optional[float] = Field(None, ge=0, le=1000000000)


def profile_owner(request: Request):
    value = request.headers.get("authorization", "")
    if not re.fullmatch(r"Bearer srp_[0-9a-f]{64}", value):
        raise HTTPException(401, "A private browser profile credential is required")
    return hashlib.sha256(value[7:].encode("ascii")).hexdigest()


def _profile_read(owner):
    try:
        return get_user_profile(owner)
    except (OSError, sqlite3.Error, RuntimeError):
        raise HTTPException(503, "Saved profile storage is temporarily unavailable")


def overhead(payload, profile):
    missing, components = [], {}
    rates = profile or {}
    for name, quantity, rate, factor in (
        ("travel", payload.distance_miles, "fuel_cost_per_mile", 2),
        ("labor", payload.labor_hours_invested, "target_hourly_wage", 1),
        ("processing", payload.processing_weight_lbs, "chemical_cost_per_lb", 1),
    ):
        if quantity == 0:
            components[name] = Decimal(0)
        elif quantity is None or rates.get(rate) is None:
            components[name] = None
            missing.append(name)
        else:
            components[name] = _d(quantity) * _d(rates[rate]) * factor
    components["other"] = _d(payload.other_costs) if payload.other_costs is not None else None
    if payload.other_costs is None:
        missing.append("other_costs")
    total = sum(components.values()) if not missing else None
    return components, total, missing


def calculate_recovery(payload, profile, market):
    rows = payload.recovered_metals
    if len({row.metal for row in rows}) != len(rows):
        raise HTTPException(422, "Each recovered metal may be entered only once")
    if sum(row.recovered_grams for row in rows) > payload.scrap_data.gross_weight_lbs * LB_GRAMS + 1e-9:
        raise HTTPException(422, "Recovered metal weight exceeds the load weight")
    if payload.processing_weight_lbs is not None and payload.processing_weight_lbs > payload.scrap_data.gross_weight_lbs:
        raise HTTPException(422, "Processing weight exceeds the load weight")
    costs, total_costs, missing_costs = overhead(payload, profile)
    missing, stale, results, gross, payout = [], [], [], Decimal(0), Decimal(0)
    for row in rows:
        quote = (market.get("metals") or {}).get(row.metal) or {}
        price, unit = quote.get("price"), quote.get("unit")
        value = None
        if row.recovered_grams == 0:
            value = Decimal(0)
        elif quote.get("available") and isinstance(price, (int, float)) and math.isfinite(price) and price > 0:
            factor = {"g": 1.0, "troy_oz": TROY_GRAMS, "lb": LB_GRAMS,
                      "kg": 1000.0, "metric_ton": 1000000.0}.get(unit)
            if factor:
                value = _d(row.recovered_grams) / _d(factor) * _d(price)
        if value is None:
            missing.append(row.metal + "_price")
        else:
            gross += value
            if value != 0 and row.buyer_pay_percent is None:
                missing.append(row.metal + "_buyer_terms")
            else:
                payout += value * _d(row.buyer_pay_percent or 0) / 100
        if row.recovered_grams > 0 and (quote.get("stale") or not quote.get("source_price_date")):
            stale.append(row.metal)
        results.append({"metal": row.metal, "recovered_grams": row.recovered_grams,
                        "gross_metal_value": _money(value) if value is not None else None,
                        "price_unit": unit, "source_price_date": quote.get("source_price_date"),
                        "stale": bool(quote.get("stale")), "buyer_pay_percent": row.buyer_pay_percent})
    complete = bool(rows) and not missing and not stale and total_costs is not None
    return {
        "status": "needs_yields" if not rows else "complete_scenario" if complete else "incomplete_scenario",
        "yield_basis": payload.yield_basis,
        "materials": results,
        "cost_breakdown": {name: _money(value) if value is not None else None for name, value in costs.items()},
        "missing_inputs": (["recovered_metals"] if not rows else []) + missing + missing_costs,
        "stale_metals": stale,
        "financial_summary": {
            "gross_commodity_value": _money(gross) if rows and not any(x.endswith("_price") for x in missing) else None,
            "total_overhead_deductions": _money(total_costs) if total_costs is not None else None,
            "estimated_net_after_entered_costs": _money(payout - _d(total_costs)) if complete else None,
        },
        "note": "Only explicitly entered recovered fine-metal quantities are valued. Prices are sourced market references, not buyer offers. Saved rates multiply entered one-way distance (round trip), labor hours and processing weight. Other material and missing costs are excluded; no sell/hold forecast is generated.",
    }


def build_profile_router(price_provider):
    router = APIRouter(prefix="/api", tags=["Operating profiles"])

    @router.get("/profile")
    def read_profile(owner: str = Depends(profile_owner)):
        profile = _profile_read(owner)
        return {"status": "success", "saved": profile is not None, "profile": profile}

    @router.post("/update-profile")
    def update_profile(payload: ProfileUpdate, owner: str = Depends(profile_owner)):
        try:
            data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
            profile = save_user_profile(owner, data)
        except (OSError, sqlite3.Error, RuntimeError):
            raise HTTPException(503, "Saved profile storage is temporarily unavailable")
        return {"status": "profile_updated_successfully", "saved": profile is not None, "profile": profile}

    @router.post("/calculate-yield")
    def process_field_scrap(payload: RecoveryRequest, owner: str = Depends(profile_owner)):
        profile = _profile_read(owner)
        market = price_provider() if payload.recovered_metals else {}
        return calculate_recovery(payload, profile, market)

    return router
