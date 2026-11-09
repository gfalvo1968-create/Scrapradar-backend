"""Validate canonical PayPal LIVE subscription and plan responses.

Pure validation only. No network calls, browser inputs, or access grants.
A future trusted billing worker MUST fetch both responses from PayPal's LIVE
API with server-held credentials, load the server-created binding from durable
storage, and pass only this function's output to entitlement_policy.allowed.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping
from uuid import UUID
import re

from membership_catalog import PLANS

SUBSCRIPTION_ID = re.compile(r"I-[A-Z0-9-]{5,80}\Z")
PLAN_ID = re.compile(r"P-[A-Z0-9-]{5,80}\Z")


def _money(amount):
    try:
        if not isinstance(amount, str):
            return None
        v = Decimal(amount)
        return v if v.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def verified_live_subscription(binding: Mapping, subscription: Mapping,
                               provider_plan: Mapping, now: datetime | None = None):
    """Return entitlement evidence or None; never trust a mere ACTIVE flag.

    binding is a trusted, previously persisted server-side checkout intent with
    customer_id, plan_id, subscription_id, provider_plan_id and custom_id.
    No endpoint currently creates these live bindings.
    """
    if not all(isinstance(obj, Mapping) for obj in
               (binding, subscription, provider_plan)):
        return None
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        return None
    try:
        customer_id = str(UUID(str(binding.get("customer_id", ""))))
    except (TypeError, ValueError, AttributeError):
        return None
    plan_id = binding.get("plan_id")
    if not isinstance(plan_id, str) or plan_id not in PLANS:
        return None
    subscription_id = binding.get("subscription_id")
    provider_plan_id = binding.get("provider_plan_id")
    custom_id = binding.get("custom_id")
    if (not isinstance(subscription_id, str) or not SUBSCRIPTION_ID.fullmatch(subscription_id)
        or not isinstance(provider_plan_id, str) or not PLAN_ID.fullmatch(provider_plan_id)
        or not isinstance(custom_id, str) or not 16 <= len(custom_id) <= 128):
        return None
    if (subscription.get("id") != subscription_id
        or subscription.get("plan_id") != provider_plan_id
        or subscription.get("custom_id") != custom_id
        or subscription.get("status") != "ACTIVE"
        or subscription.get("plan_overridden") is not False
        or subscription.get("quantity", "1") != "1"):
        return None

    # Confirm the catalog price for the server-created plan; never accept price
    # chosen by a client, a browser redirect or a PayPal plan with an override.
    try:
        cycles = provider_plan["billing_cycles"]
        cycle = cycles[0]
        price = cycle["pricing_scheme"]["fixed_price"]
        preferences = provider_plan["payment_preferences"]
        valid = (
            provider_plan.get("id") == provider_plan_id
            and provider_plan.get("status") == "ACTIVE"
            and isinstance(cycles, list) and len(cycles) == 1
            and cycle["tenure_type"] == "REGULAR"
            and cycle["frequency"] == {"interval_unit": "MONTH", "interval_count": 1}
            and cycle["total_cycles"] == 0
            and price["currency_code"] == "USD"
            and _money(price["value"]) == Decimal(PLANS[plan_id]["amount_cents"]) / 100
            and _money(preferences["setup_fee"]["value"]) == Decimal(0)
            and preferences["setup_fee"]["currency_code"] == "USD"
            and provider_plan.get("quantity_supported") is not True
            and not provider_plan.get("taxes")
        )
    except (KeyError, IndexError, TypeError):
        return None
    if not valid:
        return None

    # Last successful payment must be for this amount, be plausibly recent,
    # and exist in a billing record fetched from the provider. The period is a
    # provisional conservative maximum; upcoming recurring billing can require
    # renewal-aware reconciliation. NO live access is wired to it yet.
    try:
        billing = subscription["billing_info"]
        last = billing["last_payment"]
        amount = last["amount"]
        last_time = datetime.fromisoformat(last["time"].replace("Z", "+00:00"))
        valid_payment = (
            amount["currency_code"] == "USD"
            and _money(amount["value"]) == Decimal(PLANS[plan_id]["amount_cents"]) / 100
            and last_time.tzinfo is not None
            and timedelta(0) <= current - last_time <= timedelta(days=32)
            and _money(billing.get("outstanding_balance", {}).get("value", "0")) == 0
            and billing.get("failed_payments_count", 0) == 0
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not valid_payment:
        return None
    return {
        "customer_id": customer_id,
        "plan_id": plan_id,
        "environment": "live",
        "source": "verified_provider_reconciliation",
        "verified": True,
        "payment_ok": True,
        "state": "ACTIVE",
        "verified_at": current,
    }
