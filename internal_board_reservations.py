"""Draft-only receiver for trusted Board Sense case reservations. NOT mounted.

This router is NOT included by main.py. Even if another engineer mounts it,
the default service feature switch denies requests, AND the production provider
entitlement verifier deliberately fails closed until implemented.

The existing PayPal SANDBOX pilot is not payment evidence and must NEVER be
connected to this path.
"""
from __future__ import annotations

import hmac
import os
import sqlite3
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from customer_accounts import verified_customer
from paid_board_quota import reserve_paid_board_case

router = APIRouter(prefix="/api/internal/board", tags=["Internal Board Sense"])
SERVICE_KEY_HEADER = "x-srf-board-service-key"


class CaseReservation(BaseModel):
    # UUIDs arrive over JSON as strings; strict=True would reject every valid
    # wire-format UUID before our service/payment authorization can run.
    # UUID parsing still rejects malformed identifiers; extra keys stay banned.
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


def require_board_sense_service(request: Request) -> None:
    """Authenticate this request's server, *independently* of customer auth."""
    if os.getenv("SCRAP_RADAR_INTERNAL_BOARD_RESERVATION_ENABLED", "") != "1":
        raise HTTPException(503, "Internal membership reservation is disabled")
    expected = os.getenv("SCRAP_RADAR_BOARD_SERVICE_KEY", "")
    if len(expected) < 32 or any(c.isspace() for c in expected):
        raise HTTPException(503, "Internal service authentication is not configured")
    presented = request.headers.get(SERVICE_KEY_HEADER, "")
    if not presented or not hmac.compare_digest(
        presented.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(403, "Internal service credential required")


def verify_production_paid_entitlement(customer_id: str, module: str) -> bool:
    """UNIMPLEMENTED security gate, not bypassable through config/environment.

    A future implementation must independently verify a live, non-sandbox
    provider-reconciled, authenticated customer -> subscription -> plan binding,
    and reject tampered prices, stale renewal/cancellation state, and sandbox
    subscription IDs. A locally marked ACTIVE membership is insufficient.
    """
    raise HTTPException(503, "Production payment verification is not connected")


@router.post("/cases/reserve")
def reserve_one_case(
    entry: CaseReservation,
    response: Response,
    _: None = Depends(require_board_sense_service),
    customer: dict = Depends(verified_customer),
):
    """Reserve one counted physical board case for a *verified* paid customer.

    The body accepts only a case UUID. Identity and plan cannot be supplied by
    the caller. Do not expose this operation to browsers or use as public access.
    """
    response.headers["Cache-Control"] = "no-store"
    customer_id = customer["id"]
    proof = verify_production_paid_entitlement(customer_id, "board_sense")
    if proof is not True:
        raise HTTPException(503, "Production payment verification is unavailable")

    try:
        result = reserve_paid_board_case(customer_id, str(entry.case_id))
    except (ValueError,):
        # Avoid leaking other customers' case binding details.
        raise HTTPException(409, "Case is not available") from None
    except (sqlite3.Error, RuntimeError, OSError):
        raise HTTPException(503, "Quota records are temporarily unavailable") from None

    if not result.allowed:
        if result.reason == "no_reconciled_active_plan":
            raise HTTPException(403, "Active Board Sense membership required")
        if result.reason == "daily_limit_reached":
            raise HTTPException(429, "Daily board-case allowance reached")
        raise HTTPException(409, "Case already recorded; retrieve original result")

    return {
        "allowed": True,
        "case_id": str(entry.case_id),
        "usage": {
            "used_today": result.used_today,
            "remaining": result.remaining,
            "limit": result.limit,
            "day_utc": result.day_utc,
        },
    }
