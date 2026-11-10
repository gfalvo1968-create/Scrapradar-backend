"""Customer identity is verified online by the project's managed Auth service."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from database import _connect
from membership_records import customer_subscriptions
from entitlement_policy import allowed

CONFIG = json.loads(Path(__file__).with_name('customer_auth_config.json').read_text())


def verified_customer(request: Request):
    header = request.headers.get('authorization', '')
    if not header.startswith('Bearer ') or not 20 <= len(header[7:]) <= 8192:
        raise HTTPException(401, 'Sign in to your customer account')
    token = header[7:]
    req = URLRequest(CONFIG['url']+'/auth/v1/user', headers={
        'apikey': CONFIG['publishable_key'], 'Authorization': 'Bearer '+token})
    try:
        with urlopen(req, timeout=8) as result:
            user = json.load(result)
    except HTTPError as error:
        if error.code in (400,401,403):
            raise HTTPException(401, 'Your sign-in has expired or is invalid') from None
        raise HTTPException(503, 'Account verification is temporarily unavailable') from None
    except (URLError, TimeoutError, ValueError, OSError):
        raise HTTPException(503, 'Account verification is temporarily unavailable') from None
    try:
        identity = str(UUID(user['id']))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(401, 'Invalid customer identity') from None
    if user.get('is_anonymous') or user.get('role') != 'authenticated' or not user.get('email') or not user.get('email_confirmed_at'):
        raise HTTPException(403, 'A confirmed email account is required')
    # Ignore user_metadata for authorization, plan and customer identity.
    return {'id': identity, 'email': user['email']}


router = APIRouter(prefix='/api', tags=['Customer account'])


def _trusted_live_snapshot(customer_id):
    """No live PayPal reconciler is connected yet. Never accept client claims.

    Replace this adapter only after server-side canonical billing verification
    and customer-plan-price binding have been implemented and tested.
    """
    return None


def paid_modules(customer_id):
    snapshot = _trusted_live_snapshot(customer_id)
    return {
        'scrap_radar': allowed(customer_id, 'scrap_radar', snapshot),
        'board_sense': allowed(customer_id, 'board_sense', snapshot),
    }


@router.get('/member-access')
def member_access(response: Response, customer: dict = Depends(verified_customer)):
    """Read-only membership access decision; cannot set billing status."""
    response.headers['Cache-Control'] = 'no-store'
    modules = paid_modules(customer['id'])
    return {
        'modules': modules,
        'paid_access_enabled': any(modules.values()),
        'billing_verification': 'not_connected',
        'notice': 'Paid memberships are not enabled yet.',
    }


@router.get('/account')
def account(response: Response, customer: dict = Depends(verified_customer)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        with closing(_connect()) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS customer_accounts (
                customer_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.execute('INSERT OR IGNORE INTO customer_accounts(customer_id) VALUES (?)',(customer['id'],))
            created = conn.execute('SELECT created_at FROM customer_accounts WHERE customer_id=?',(customer['id'],)).fetchone()[0]
        subscriptions = customer_subscriptions(customer['id'])
    except (sqlite3.Error, RuntimeError, OSError):
        raise HTTPException(503, 'Your account records are temporarily unavailable') from None
    return {
        'customer': {'id': customer['id'], 'email': customer['email'], 'created_at': created},
        'subscriptions': [{k:r[k] for k in ('plan_id','amount_cents','currency','state','rate_retained')} for r in subscriptions],
        'checkout_enabled': False,
        'paid_access_enabled': False,
        'module_access': paid_modules(customer['id']),
        'usage': {'limit_per_day':25, 'used_today':None, 'enforcement':'not_connected'},
        'notice':'Membership payments and paid board access are not enabled yet.',
    }
