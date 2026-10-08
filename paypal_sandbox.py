"""Sandbox credential verification. Does not create payments or grant access."""
import base64
import json
import os
import time
from threading import Lock
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, Response


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


router = APIRouter(prefix='/api/paypal', tags=['PayPal sandbox'])
_lock = Lock()
_cached = {'until': 0, 'ready': False}


def check_credentials():
    # Never fall back to live mode, and never expose credentials or provider bodies.
    if os.environ.get('PAYPAL_ENVIRONMENT') != 'sandbox':
        return False, 'sandbox_environment_required'
    client = os.environ.get('PAYPAL_CLIENT_ID', '')
    secret = os.environ.get('PAYPAL_CLIENT_SECRET', '')
    if not client or not secret:
        return False, 'credentials_missing'
    with _lock:
        now = time.monotonic()
        if _cached['until'] > now:
            return _cached['ready'], _cached['reason']
        auth = base64.b64encode((client+':'+secret).encode()).decode()
        req = Request('https://api-m.sandbox.paypal.com/v1/oauth2/token',
            data=b'grant_type=client_credentials', headers={
                'Authorization': 'Basic '+auth,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'})
        ready, reason = False, 'provider_unavailable'
        try:
            with build_opener(NoRedirect()).open(req, timeout=8) as result:
                data = json.loads(result.read(65537))
            ready = (isinstance(data, dict) and data.get('token_type', '').lower() == 'bearer'
                     and isinstance(data.get('access_token'), str) and bool(data['access_token']))
            reason = 'authenticated' if ready else 'invalid_provider_response'
        except HTTPError as error:
            reason = 'credentials_rejected' if error.code in (400, 401, 403) else 'provider_unavailable'
        except (URLError, OSError, ValueError, TypeError, AttributeError):
            pass
        _cached.update(until=time.monotonic()+60, ready=ready, reason=reason)
        return ready, reason


@router.get('/sandbox-status')
def sandbox_status(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    ready, reason = check_credentials()
    return {'environment': 'sandbox', 'credentials_verified': ready, 'status': reason,
            'checkout_enabled': False, 'paid_access_enabled': False}
