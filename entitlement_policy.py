"""Fail-closed membership decision policy for a future trusted billing reconciler.

This is NOT a payment verifier, login system, or public endpoint. The caller MUST
supply a server-verified, fresh PayPal LIVE subscription snapshot, never browser
JSON, a redirect query, a sandbox pilot row, or an unverified local ledger row.
Not wired into the public APIs until billing reconciliation is implemented.
"""
from datetime import datetime, timezone, timedelta
from typing import Mapping
from uuid import UUID

MODULES = {
    "scrap_radar": frozenset({"scrap_radar"}),
    "board_sense": frozenset({"board_sense"}),
    "family": frozenset({"scrap_radar", "board_sense"}),
}
MAX_VERIFICATION_AGE = timedelta(minutes=15)


def allowed(customer_id: str, module: str, snapshot: Mapping | None,
            now: datetime | None = None) -> bool:
    """Deny unless every required property of a trusted snapshot checks out.

    A future backend adapter must obtain the snapshot from PayPal's canonical
    API or verified live webhook reconciliation, verify the subscription's
    bound customer, plan, price, currency, and payment standing, and never
    accept user-submitted fields as that snapshot.
    """
    if module not in ("scrap_radar", "board_sense") or not isinstance(snapshot, Mapping):
        return False
    try:
        owner = str(UUID(str(customer_id)))
        bound = str(UUID(str(snapshot.get("customer_id", ""))))
    except (ValueError, AttributeError, TypeError):
        return False
    if owner != bound:
        return False
    if (snapshot.get("environment") != "live"
        or snapshot.get("source") != "verified_provider_reconciliation"
        or snapshot.get("verified") is not True
        or snapshot.get("payment_ok") is not True
        or snapshot.get("state") != "ACTIVE"):
        return False
    plan = snapshot.get("plan_id")
    if plan not in MODULES or module not in MODULES[plan]:
        return False
    # The timestamp must originate from trusted server reconciliation. Stale
    # payment status fails closed rather than extending a lapsed subscription.
    checked = snapshot.get("verified_at")
    if not isinstance(checked, datetime) or checked.tzinfo is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return False
    age = current - checked
    if not timedelta(0) <= age <= MAX_VERIFICATION_AGE:
        return False
    return True
