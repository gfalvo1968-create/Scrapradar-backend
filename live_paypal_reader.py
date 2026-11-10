"""Read-only PayPal LIVE API client for future trusted billing reconciliation.

NOT connected to routes, checkout, or customer entitlements. Never takes a
subscription ID from the browser. The caller must supply a durable, server-
created purchase binding, and the environment must explicitly be LIVE.
The trusted adapter is intentionally disconnected pending deployment review.
"""
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from fastapi import HTTPException
from paypal_sandbox import NoRedirect
from paypal_live_evidence import verified_live_subscription

LIVE_API = "https://api-m.paypal.com"
MAX_BODY = 262144


def _request_json(url, *, headers, data=None):
    """Hardcode the PayPal origin, forbid redirects, and bound response size."""
    if not url.startswith(LIVE_API + "/"):
        raise RuntimeError("Refusing non-PayPal origin")
    request = Request(url, data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Unexpected provider response")
            raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise RuntimeError("Oversized provider response")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError("Invalid provider response")
        return result
    except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
        # Never surface PayPal response bodies, headers, tokens, or secrets.
        raise RuntimeError("Live PayPal verification unavailable") from None


def _credentials():
    if os.environ.get("PAYPAL_ENVIRONMENT") != "live":
        raise RuntimeError("Live PayPal verification not configured")
    client = os.environ.get("PAYPAL_LIVE_CLIENT_ID")
    secret = os.environ.get("PAYPAL_LIVE_CLIENT_SECRET")
    if not client or not secret:
        raise RuntimeError("Dedicated live credentials not configured")
    return client, secret


def read_only_evidence(binding):
    """Fetch canonical subscription and plan; return verified evidence or None.

    Invoked only by a future trusted reconciliation worker after lookup of a
    server-owned binding. No HTTP route currently exposes this function.
    A missing/invalid binding is rejected before any provider call.
    """
    from paypal_live_evidence import SUBSCRIPTION_ID, PLAN_ID
    from collections.abc import Mapping
    if not isinstance(binding, Mapping):
        return None
    sub = binding.get("subscription_id")
    plan = binding.get("provider_plan_id")
    if (not isinstance(sub, str) or SUBSCRIPTION_ID.fullmatch(sub) is None
        or not isinstance(plan, str) or PLAN_ID.fullmatch(plan) is None):
        return None
    client, secret = _credentials()
    credentials = base64.b64encode((client + ":" + secret).encode("utf-8")).decode("ascii")
    token_data = _request_json(
        LIVE_API + "/v1/oauth2/token",
        headers={"Authorization": "Basic " + credentials,
                 "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        data=b"grant_type=client_credentials",
    )
    token = token_data.get("access_token")
    if (token_data.get("token_type", "").lower() != "bearer"
        or not isinstance(token, str) or not 24 <= len(token) <= 4096):
        raise RuntimeError("Invalid PayPal authentication")
    auth = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    subscription = _request_json(LIVE_API + "/v1/billing/subscriptions/" + sub, headers=auth)
    provider_plan = _request_json(LIVE_API + "/v1/billing/plans/" + plan, headers=auth)
    return verified_live_subscription(binding, subscription, provider_plan)
