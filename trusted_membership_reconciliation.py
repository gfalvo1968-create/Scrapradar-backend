"""Internal customer-scoped membership reconciliation; NO public API or checkout.

The only trusted data path is: authenticated customer UUID -> durable server
bindings -> canonical PayPal LIVE fetch -> verified entitlement policy.
This service is intentionally not wired to /api/member-access until production
billing controls, lifecycle handling and cross-service enforcement are approved.
"""
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from uuid import UUID

from database import _connect
from entitlement_policy import allowed
from live_paypal_reader import read_only_evidence
from live_subscription_bindings import _schema


def _customer_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _bindings_for_customer(customer_id):
    """Read only that customer's server-generated, attached subscription IDs."""
    with closing(_connect()) as db:
        _schema(db)
        rows = db.execute("""SELECT customer_id, plan_id, provider_plan_id,
                       subscription_id, intent_id
                       FROM paypal_live_bindings
                       WHERE customer_id=? AND subscription_id IS NOT NULL
                       ORDER BY created_at DESC, intent_id DESC
                       LIMIT 50""", (customer_id,)).fetchall()
    columns = ("customer_id", "plan_id", "provider_plan_id",
               "subscription_id", "custom_id")
    return [dict(zip(columns, row)) for row in rows]


def reconcile_customer_access(customer_id):
    """Verify each subscribed module from durable bindings, or deny it.

    Caller MUST use a server-verified customer UUID (e.g. verified_customer).
    Browser-supplied customer, intent, plan or subscription IDs are never used.
    Provider errors are fail-closed. No ledger state or webhook is overwritten.
    """
    result = {"scrap_radar": False, "board_sense": False}
    owner = _customer_id(customer_id)
    if owner is None:
        return result
    try:
        bindings = _bindings_for_customer(owner)
    except (sqlite3.Error, RuntimeError, OSError):
        return result
    for binding in bindings:
        if all(result.values()):
            break
        try:
            snapshot = read_only_evidence(binding)
        except (RuntimeError, sqlite3.Error, OSError, ValueError):
            continue
        if not isinstance(snapshot, Mapping):
            continue
        for module in result:
            if not result[module] and allowed(owner, module, snapshot):
                result[module] = True
    return result
