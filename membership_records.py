"""Internal subscription ledger foundation, not authentication or billing.

No HTTP mutation route is exposed. A future integration must authenticate the
customer and verify/reconcile provider state before calling these functions.
The ledger records rate eligibility, not proof of paid access.
"""
from contextlib import closing
import json
import sqlite3
from database import _connect
from membership_catalog import CATALOG_VERSION, PLANS

STATES = frozenset({"ACTIVE", "PAYMENT_FAILED", "SUSPENDED", "CANCELLED", "EXPIRED"})


def connect():
    conn = _connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS membership_records (
        subscription_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        catalog_version TEXT NOT NULL,
        amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
        currency TEXT NOT NULL,
        state TEXT NOT NULL,
        early_family_rate INTEGER NOT NULL,
        rate_retained INTEGER NOT NULL,
        latest_revision INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS membership_events (
        event_id TEXT PRIMARY KEY,
        subscription_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        state TEXT NOT NULL,
        result TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


def register_subscription(customer_id, subscription_id, plan_id):
    """Freeze the accepted offer. Caller must supply trusted account identity."""
    if not customer_id or not subscription_id or plan_id not in PLANS:
        raise ValueError("Valid trusted customer, subscription and plan are required")
    plan = PLANS[plan_id]
    with closing(connect()) as conn, conn:
        existing = conn.execute("SELECT customer_id,plan_id FROM membership_records WHERE subscription_id=?", (subscription_id,)).fetchone()
        if existing:
            if existing != (customer_id, plan_id):
                raise ValueError("Subscription is already bound to another customer or plan")
            return
        family = int(plan_id == "family")
        # No payment or activation is implied by registering an offer.
        conn.execute("INSERT INTO membership_records VALUES (?,?,?,?,?,?,?, ?,?,0)",
                     (subscription_id, customer_id, plan_id, CATALOG_VERSION,
                      plan["amount_cents"], "USD", "SUSPENDED", family, family))


def record_reconciled_state(subscription_id, event_id, revision, state):
    """Record trusted reconciled state with a monotonic local revision.

Revision is allocated by the future reconciliation worker, NOT taken from a
posted browser value or assumed to be a PayPal event ordering field.
Duplicate notifications are harmless; older reconciliations cannot undo newer
ones. Cancellation/expiry permanently ends this subscription's early rate.
"""
    if not event_id or type(revision) is not int or revision <= 0 or state not in STATES:
        raise ValueError("Invalid reconciled event")
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT subscription_id,revision,state,result FROM membership_events WHERE event_id=?", (event_id,)).fetchone()
        if previous:
            if previous[:3] != (subscription_id, revision, state):
                raise ValueError("Event ID reused with different content")
            return json.loads(previous[3])
        row = conn.execute("SELECT latest_revision,rate_retained FROM membership_records WHERE subscription_id=?", (subscription_id,)).fetchone()
        if row is None:
            raise ValueError("Subscription is not bound to a customer")
        applied = revision > row[0]
        if applied:
            retained = bool(row[1]) and state not in {"CANCELLED", "EXPIRED"}
            conn.execute("UPDATE membership_records SET state=?,rate_retained=?,latest_revision=? WHERE subscription_id=?", (state, int(retained), revision, subscription_id))
        result = {"applied": applied, "access_granted": False}
        conn.execute("INSERT INTO membership_events(event_id,subscription_id,revision,state,result) VALUES (?,?,?,?,?)", (event_id, subscription_id, revision, state, json.dumps(result)))
        return result


def customer_subscriptions(customer_id):
    """Internal read. Future route must derive customer_id from verified login."""
    with closing(connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM membership_records WHERE customer_id=?", (customer_id,)).fetchall()
        return [dict(row) for row in rows]
