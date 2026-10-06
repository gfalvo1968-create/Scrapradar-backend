"""Approved offers; prices are integer USD cents and checkout stays disabled."""
from copy import deepcopy
from fastapi import APIRouter

CATALOG_VERSION = "2026-10-06-v1"
PLANS = {
    "scrap_radar": {"name": "Scrap Radar", "amount_cents": 1995,
                   "modules": ["scrap_radar"], "future_family_modules": False},
    "board_sense": {"name": "Board Sense", "amount_cents": 2995,
                   "modules": ["board_sense"], "future_family_modules": False},
    "family": {"name": "Scrap Radar Family", "amount_cents": 4495,
              "modules": ["scrap_radar", "board_sense"], "future_family_modules": True},
}


def catalog():
    return {
        "version": CATALOG_VERSION, "currency": "USD", "interval": "MONTH",
        "checkout_enabled": False,
        "availability": "prelaunch",
        "usage_allowances": {"status": "pending", "unlimited": False},
        "plans": [{"id": key, **deepcopy(value)} for key, value in PLANS.items()],
        "family_rate_policy": {
            "rate_retained_while_subscription_active": True,
            "cancel_and_rejoin_uses_current_offer": True,
            "payment_failure_alone_removes_rate": False,
            "payment_retry_grace_period": None,
            "scope": "One account; current and future Family software modules; published usage allowances apply.",
        },
    }


router = APIRouter(prefix="/api", tags=["Membership offers"])


@router.get("/membership-plans")
def membership_plans():
    return catalog()
