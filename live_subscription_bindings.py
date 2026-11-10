"""Durable, server-owned PayPal LIVE purchase bindings.

Internal-only persistence layer. No HTTP routes and no subscriber access grants.
Only a trusted checkout worker may create and attach bindings. Browser redirect
fields, PayPal sandbox records, and user metadata must never enter this module.
"""
import re
import sqlite3
from contextlib import closing
from uuid import UUID, uuid4
from database import _connect
from membership_catalog import PLANS
from paypal_live_evidence import SUBSCRIPTION_ID, PLAN_ID

OPAQUE_ID = re.compile(r"[a-f0-9-]{36}\Z")


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("Invalid verified customer identifier") from None


def _schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS paypal_live_bindings (
        intent_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        provider_plan_id TEXT NOT NULL,
        subscription_id TEXT UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        bound_at TEXT,
        CHECK (length(intent_id) = 36),
        CHECK (plan_id IN ('scrap_radar','board_sense','family'))
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS paypal_live_by_owner ON paypal_live_bindings(customer_id, created_at)")
    db.commit()


def create_pending(customer_id, plan_id, provider_plan_id):
    """Create random server intent; no paid permission or PayPal API side effect.

    Caller must have derived customer_id from verified_customer and mapped the
    approved plan to an authenticated provider billing plan. Must not be used as
    a public form endpoint without additional checkout/idempotency controls.
    """
    owner = _uuid(customer_id)
    if not isinstance(plan_id, str) or plan_id not in PLANS:
        raise ValueError("Unapproved membership plan")
    if not isinstance(provider_plan_id, str) or not PLAN_ID.fullmatch(provider_plan_id):
        raise ValueError("Invalid PayPal plan identifier")
    intent = str(uuid4())
    with closing(_connect()) as db:
        _schema(db)
        with db:
            db.execute("""INSERT INTO paypal_live_bindings
                (intent_id, customer_id, plan_id, provider_plan_id)
                VALUES (?, ?, ?, ?)""", (intent, owner, plan_id, provider_plan_id))
    return intent


def attach_subscription(intent_id, subscription_id):
    """Bind once, atomically. A subscription can never be moved to a new owner.

    Caller must authenticate PayPal provider response before calling. This does
    NOT verify payment status, and an attached subscription grants zero access.
    """
    if not isinstance(intent_id, str) or not OPAQUE_ID.fullmatch(intent_id):
        raise ValueError("Invalid trusted intent")
    if not isinstance(subscription_id, str) or not SUBSCRIPTION_ID.fullmatch(subscription_id):
        raise ValueError("Invalid PayPal subscription identifier")
    with closing(_connect()) as db:
        _schema(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT subscription_id FROM paypal_live_bindings WHERE intent_id=?", (intent_id,)
        ).fetchone()
        if row is None:
            db.rollback()
            raise ValueError("Unknown purchase intent")
        if row[0] is not None and row[0] != subscription_id:
            db.rollback()
            raise ValueError("Purchase intent already bound")
        try:
            db.execute("""UPDATE paypal_live_bindings
                SET subscription_id=?, bound_at=COALESCE(bound_at,CURRENT_TIMESTAMP)
                WHERE intent_id=?""", (subscription_id, intent_id))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            raise ValueError("Subscription already bound elsewhere") from None


def customer_binding(customer_id, intent_id):
    """Never fetch a different customer's binding. Return None if not attached."""
    owner = _uuid(customer_id)
    if not isinstance(intent_id, str) or not OPAQUE_ID.fullmatch(intent_id):
        return None
    with closing(_connect()) as db:
        _schema(db)
        row = db.execute("""SELECT customer_id, plan_id, provider_plan_id,
                subscription_id, intent_id FROM paypal_live_bindings
                WHERE customer_id=? AND intent_id=? AND subscription_id IS NOT NULL""",
                (owner, intent_id)).fetchone()
    if not row:
        return None
    return dict(zip(("customer_id", "plan_id", "provider_plan_id",
                     "subscription_id", "custom_id"), row))
