"""Owner-only sandbox pilot. Separate records; never grants production access."""
import hashlib
import base64
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from decimal import Decimal
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException, Response, Request as WebRequest
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from customer_accounts import verified_customer
from database import _connect
from membership_catalog import PLANS, CATALOG_VERSION
from paypal_sandbox import NoRedirect

router = APIRouter(prefix='/api/paypal/pilot', tags=['Sandbox checkout pilot'])
RETURN = 'https://gfalvo1968-create.github.io/scrap_radar_family/sandbox_checkout.html'
BASE = 'https://api-m.sandbox.paypal.com'


def pilot(customer=Depends(verified_customer)):
    if customer['email'].lower() != 'support@scrapradarfamily.com':
        raise HTTPException(403, 'Sandbox testing is currently limited to the owner account')
    if os.environ.get('PAYPAL_ENVIRONMENT') != 'sandbox':
        raise HTTPException(503, 'Sandbox mode is required')
    return customer


def read_json(req):
    try:
        with build_opener(NoRedirect()).open(req, timeout=12) as result:
            raw = result.read(262145)
        if len(raw) > 262144:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (HTTPError, URLError, OSError, ValueError):
        raise HTTPException(502, 'PayPal test service did not complete the request. Retry this same test; do not create a different purchase.') from None


def api(path, body=None, request_id=None):
    if os.environ.get('PAYPAL_ENVIRONMENT') != 'sandbox':
        raise HTTPException(503, 'Sandbox mode is required')
    client, secret = os.environ.get('PAYPAL_CLIENT_ID'), os.environ.get('PAYPAL_CLIENT_SECRET')
    if not client or not secret:
        raise HTTPException(503, 'PayPal credentials are missing')
    auth = base64.b64encode((client+':'+secret).encode()).decode()
    token = read_json(Request(BASE+'/v1/oauth2/token', data=b'grant_type=client_credentials', headers={
        'Authorization':'Basic '+auth, 'Content-Type':'application/x-www-form-urlencoded'})).get('access_token')
    if not isinstance(token,str) or not token:
        raise HTTPException(502, 'PayPal authentication failed')
    headers = {'Authorization':'Bearer '+token, 'Content-Type':'application/json', 'Accept':'application/json'}
    if request_id:
        headers['PayPal-Request-Id'] = request_id
        headers['Prefer'] = 'return=representation'
    return read_json(Request(BASE+path, data=json.dumps(body).encode() if body is not None else None, headers=headers))


def connect():
    c = _connect()
    c.row_factory = sqlite3.Row
    c.executescript('''CREATE TABLE IF NOT EXISTS paypal_pilot_catalog (
        key TEXT PRIMARY KEY, provider_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paypal_pilot_intents (
        id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, plan TEXT NOT NULL,
        created REAL NOT NULL, provider_plan TEXT NOT NULL,
        subscription TEXT, approval TEXT, state TEXT NOT NULL DEFAULT 'CREATING',
        UNIQUE(customer_id,plan));
        CREATE TABLE IF NOT EXISTS paypal_pilot_events (
        id TEXT PRIMARY KEY, digest TEXT NOT NULL, subscription TEXT,
        received REAL NOT NULL, outcome TEXT NOT NULL);''')
    # Remove the original one-attempt constraint atomically, preserving every ID.
    try:
        c.execute('BEGIN IMMEDIATE')
        schema=c.execute("SELECT sql FROM sqlite_master WHERE name='paypal_pilot_intents'").fetchone()[0]
        if 'UNIQUE(customer_id,plan)' in schema:
            c.execute("""CREATE TABLE paypal_pilot_intents_v2 (
                id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, plan TEXT NOT NULL,
                created REAL NOT NULL, provider_plan TEXT NOT NULL,
                subscription TEXT, approval TEXT, state TEXT NOT NULL DEFAULT 'CREATING')""")
            c.execute('INSERT INTO paypal_pilot_intents_v2 SELECT * FROM paypal_pilot_intents')
            c.execute('DROP TABLE paypal_pilot_intents')
            c.execute('ALTER TABLE paypal_pilot_intents_v2 RENAME TO paypal_pilot_intents')
        c.execute('CREATE INDEX IF NOT EXISTS paypal_pilot_latest ON paypal_pilot_intents(customer_id,plan,created DESC)')
        c.commit()
        return c
    except Exception:
        c.rollback()
        c.close()
        raise


def provider_id(data, prefix):
    value = data.get('id','')
    if not isinstance(value,str) or not re.fullmatch(prefix+r'[A-Z0-9-]{5,80}',value):
        raise HTTPException(502, 'Invalid PayPal test identifier')
    return value


def ensure_plan(c, plan):
    key = CATALOG_VERSION+':'+plan
    row = c.execute('SELECT provider_id FROM paypal_pilot_catalog WHERE key=?',(key,)).fetchone()
    if row:
        return row[0]
    product_key = CATALOG_VERSION+':product'
    product = c.execute('SELECT provider_id FROM paypal_pilot_catalog WHERE key=?',(product_key,)).fetchone()
    if product:
        product_id = product[0]
    else:
        product_id = provider_id(api('/v1/catalogs/products',{
            'name':'Scrap Radar Family Sandbox', 'type':'SERVICE', 'category':'SOFTWARE'},
            str(uuid5(NAMESPACE_URL,RETURN+product_key))), 'PROD-')
        c.execute('INSERT INTO paypal_pilot_catalog VALUES (?,?)',(product_key,product_id))
    price = f"{PLANS[plan]['amount_cents']/100:.2f}"
    data = api('/v1/billing/plans',{'product_id':product_id,
        'name':PLANS[plan]['name']+' Sandbox', 'status':'ACTIVE',
        'billing_cycles':[{'frequency':{'interval_unit':'MONTH','interval_count':1},
            'tenure_type':'REGULAR','sequence':1,'total_cycles':0,
            'pricing_scheme':{'fixed_price':{'value':price,'currency_code':'USD'}}}],
        'payment_preferences':{'auto_bill_outstanding':False,
            'setup_fee':{'value':'0','currency_code':'USD'},
            'setup_fee_failure_action':'CANCEL','payment_failure_threshold':1}},
        str(uuid5(NAMESPACE_URL,RETURN+key)))
    result = provider_id(data,'P-')
    c.execute('INSERT INTO paypal_pilot_catalog VALUES (?,?)',(key,result))
    return result


def validate_plan(data, plan):
    try:
        cycles = data['billing_cycles']
        cycle = cycles[0]
        fixed = cycle['pricing_scheme']['fixed_price']
        valid = (data['status']=='ACTIVE' and len(cycles)==1 and cycle['tenure_type']=='REGULAR'
            and cycle['frequency']=={'interval_unit':'MONTH','interval_count':1}
            and cycle['total_cycles']==0 and fixed['currency_code']=='USD'
            and Decimal(fixed['value'])==Decimal(PLANS[plan]['amount_cents'])/100
            and not data.get('quantity_supported',False)
            and Decimal(data.get('payment_preferences',{}).get('setup_fee',{}).get('value','0'))==0
            and Decimal(data.get('taxes',{}).get('percentage','0'))==0)
    except (KeyError,ValueError,TypeError,IndexError,ArithmeticError):
        valid=False
    if not valid:
        raise HTTPException(409,'PayPal test plan does not match our approved price')


def approval_url(data):
    for link in data.get('links',[]):
        if link.get('rel')=='approve':
            value=link.get('href',''); u=urlsplit(value)
            if (u.scheme=='https' and u.netloc in ('www.sandbox.paypal.com','sandbox.paypal.com')
                and u.path=='/webapps/billing/subscriptions' and u.query):
                return value
    raise HTTPException(502,'PayPal did not return a safe sandbox approval link')


class Choice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plan: str


@router.post('/checkout')
def checkout(choice:Choice, response:Response, customer=Depends(pilot)):
    response.headers['Cache-Control']='no-store'
    if choice.plan not in PLANS:
        raise HTTPException(422,'Choose one of our three membership plans')
    try:
        with closing(connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            provider_plan=ensure_plan(c,choice.plan)
            validate_plan(api('/v1/billing/plans/'+provider_plan),choice.plan)
            row=c.execute('SELECT * FROM paypal_pilot_intents WHERE customer_id=? AND plan=? ORDER BY created DESC, rowid DESC LIMIT 1',
                (customer['id'],choice.plan)).fetchone()
            # A new attempt is allowed only after a canonical terminal state.
            # Active/pending/uncertain attempts retain their original request ID.
            if row and row['subscription']:
                _,state=refresh_subscription(c,row)
                if state in ('CANCELLED','EXPIRED'):
                    row=None
            if not row:
                intent=str(uuid4())
                c.execute('INSERT INTO paypal_pilot_intents(id,customer_id,plan,created,provider_plan) VALUES (?,?,?,?,?)',
                    (intent,customer['id'],choice.plan,time.time(),provider_plan))
            c.commit()
            # Persist the request ID before calling PayPal. Concurrent retries are serialized.
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM paypal_pilot_intents WHERE customer_id=? AND plan=? ORDER BY created DESC, rowid DESC LIMIT 1',
                (customer['id'],choice.plan)).fetchone()
            if not row['subscription']:
                if time.time()-row['created']>86400:
                    raise HTTPException(409,'This pending test needs manual reconciliation before another attempt')
                data=api('/v1/billing/subscriptions',{'plan_id':provider_plan,'custom_id':row['id'],
                    'application_context':{'brand_name':'Scrap Radar Family TEST',
                        'shipping_preference':'NO_SHIPPING','user_action':'SUBSCRIBE_NOW',
                        'return_url':RETURN+'?intent='+row['id'],
                        'cancel_url':RETURN+'?intent='+row['id']+'&cancelled=1'}}, row['id'])
                subscription=provider_id(data,'I-'); approval=approval_url(data)
                c.execute('UPDATE paypal_pilot_intents SET subscription=?,approval=?,state=? WHERE id=?',
                    (subscription,approval,'APPROVAL_PENDING',row['id']))
                c.commit()
            else:
                approval=row['approval']; c.commit()
            return {'intent':row['id'],'approval_url':approval,'environment':'sandbox','paid_access_enabled':False}
    except (sqlite3.Error,RuntimeError,OSError):
        raise HTTPException(503,'Test records are temporarily unavailable') from None


@router.get('/intents/{intent}')
def reconcile(intent:str,response:Response,customer=Depends(pilot)):
    response.headers['Cache-Control']='no-store'
    try:
        with closing(connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM paypal_pilot_intents WHERE id=? AND customer_id=?',
                (intent,customer['id'])).fetchone()
            if not row or not row['subscription']:
                raise HTTPException(404,'Test subscription not found')
            data,state=refresh_subscription(c,row)
            c.commit()
            payment=data.get('billing_info',{}).get('last_payment',{}).get('amount',{})
            return {'plan':row['plan'],'subscription_id':row['subscription'],'state':state,
                'amount_cents':PLANS[row['plan']]['amount_cents'],'currency':'USD',
                'test_payment_recorded':payment.get('currency_code')=='USD' and
                    payment.get('value')==f"{PLANS[row['plan']]['amount_cents']/100:.2f}",
                'environment':'sandbox','paid_access_enabled':False}
    except (sqlite3.Error,RuntimeError,OSError):
        raise HTTPException(503,'Test records are temporarily unavailable') from None


def refresh_subscription(c, row):
    """Caller holds a write transaction, serializing provider reads and writes."""
    data=api('/v1/billing/subscriptions/'+row['subscription'])
    if (data.get('id')!=row['subscription'] or data.get('plan_id')!=row['provider_plan']
        or data.get('custom_id')!=row['id'] or data.get('plan_overridden',False)
        or data.get('quantity','1')!='1'):
        raise HTTPException(409,'PayPal subscription details did not match this test')
    validate_plan(api('/v1/billing/plans/'+row['provider_plan']),row['plan'])
    state=data.get('status')
    if state not in ('APPROVAL_PENDING','APPROVED','ACTIVE','SUSPENDED','CANCELLED','EXPIRED'):
        raise HTTPException(502,'Unknown PayPal subscription state')
    c.execute('UPDATE paypal_pilot_intents SET state=? WHERE id=?',(state,row['id']))
    return data,state


WEBHOOK_EVENTS = frozenset({
    'BILLING.SUBSCRIPTION.CREATED', 'BILLING.SUBSCRIPTION.ACTIVATED',
    'BILLING.SUBSCRIPTION.UPDATED', 'BILLING.SUBSCRIPTION.SUSPENDED',
    'BILLING.SUBSCRIPTION.CANCELLED', 'BILLING.SUBSCRIPTION.EXPIRED',
    'BILLING.SUBSCRIPTION.PAYMENT.FAILED', 'PAYMENT.SALE.COMPLETED',
    'PAYMENT.SALE.REFUNDED', 'PAYMENT.SALE.REVERSED'})


def process_webhook(raw, headers):
    if os.environ.get('PAYPAL_ENVIRONMENT') != 'sandbox':
        raise HTTPException(503,'Sandbox mode is required')
    webhook_id=os.environ.get('PAYPAL_SANDBOX_WEBHOOK_ID','')
    if not re.fullmatch(r'[A-Z0-9-]{5,80}',webhook_id):
        raise HTTPException(503,'Sandbox webhook is not configured')
    try:
        event=json.loads(raw)
        if not isinstance(event,dict): raise ValueError()
        event_id=event.get('id','')
        if not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9-]{5,100}',event_id): raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(400,'Invalid webhook message') from None
    fields={key:headers.get('paypal-'+key.replace('_','-'),'') for key in
        ('transmission_id','transmission_time','cert_url','auth_algo','transmission_sig')}
    if any(not value or len(value)>4096 for value in fields.values()):
        raise HTTPException(400,'Missing or invalid webhook verification headers')
    cert=urlsplit(fields['cert_url'])
    if (cert.scheme!='https' or cert.netloc not in ('api.sandbox.paypal.com','api-m.sandbox.paypal.com')
        or not cert.path.startswith('/v1/notifications/certs/') or cert.query or cert.fragment):
        raise HTTPException(400,'Invalid webhook certificate address')
    # PayPal verifies against the configured app webhook ID. Never fetch a caller URL.
    result=api('/v1/notifications/verify-webhook-signature',dict(fields,
        webhook_id=webhook_id,webhook_event=event))
    if result.get('verification_status')!='SUCCESS':
        raise HTTPException(403,'Webhook verification failed')
    digest=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    kind=event.get('event_type')
    if not isinstance(kind,str): raise HTTPException(400,'Invalid webhook event type')
    resource=event.get('resource',{})
    subscription=None
    if kind in WEBHOOK_EVENTS and isinstance(resource,dict):
        subscription=resource.get('id') if kind.startswith('BILLING.SUBSCRIPTION.') else resource.get('billing_agreement_id')
    if subscription is not None and (not isinstance(subscription,str) or not re.fullmatch(r'I-[A-Z0-9-]{5,80}',subscription)):
        raise HTTPException(400,'Invalid subscription identifier')
    try:
        with closing(connect()) as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT digest FROM paypal_pilot_events WHERE id=?',(event_id,)).fetchone()
            if prior:
                if prior['digest']!=digest: raise HTTPException(409,'Webhook event ID collision')
                return {'received':True,'duplicate':True,'paid_access_enabled':False}
            row=c.execute('SELECT * FROM paypal_pilot_intents WHERE subscription=?',(subscription,)).fetchone() if subscription else None
            outcome='ignored'
            if row:
                # Use canonical current state, not an old or out-of-order event status.
                refresh_subscription(c,row)
                outcome='reconciled'
            c.execute('INSERT INTO paypal_pilot_events VALUES (?,?,?,?,?)',
                (event_id,digest,subscription,time.time(),outcome))
            c.commit()
            return {'received':True,'outcome':outcome,'paid_access_enabled':False}
    except (sqlite3.Error,RuntimeError,OSError):
        raise HTTPException(503,'Test records are temporarily unavailable') from None


@router.post('/webhook')
async def webhook(request:WebRequest, response:Response):
    response.headers['Cache-Control']='no-store'
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>262144: raise HTTPException(413,'Webhook message is too large')
    return await run_in_threadpool(process_webhook,bytes(raw),request.headers)
