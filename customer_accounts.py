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
        'usage': {'limit_per_day':25, 'used_today':None, 'enforcement':'not_connected'},
        'notice':'Membership payments and paid board access are not enabled yet.',
    }
