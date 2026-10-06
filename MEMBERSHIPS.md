# Membership foundation — October 6, 2026

Approved monthly USD offers: Scrap Radar $19.95, Board Sense $29.95, Family $44.95.

`GET /api/membership-plans` publishes the versioned offer catalog and explicitly reports checkout disabled, prelaunch availability and pending usage allowances.

`membership_records.py` is an internal SQLite ledger, with no customer-facing read or mutation endpoint. It freezes accepted prices and customer/subscription bindings. It records idempotent, monotonic reconciliations; failed payments and suspension do not alone erase the early Family rate, while cancellation/expiry ends continuity for that subscription. It does not authorize access or verify payments. The authenticated payment integration must supply trusted customer identity and verified, reconciled provider state. A local reconciliation revision is not a PayPal event field. Do not expose these functions to browser-posted identity or billing state.

Not yet implemented: login, verified email, PayPal checkout/signature verification, live subscription processing, payment-to-access enforcement, customer dashboard or admin customer management. No actual customer records or payment events were created by this release. Existing browser operating-profile credentials are not paid customer identity.

Before checkout: publish usage allowances, retry/grace policy, cancellation/refund policy; configure the business PayPal sandbox integration through server secrets; test real sandbox payments and lifecycle events end to end. Never collect credentials in chat or ship secrets in frontend code.

Tests: 24 backend checks pass, including seven new catalog/ledger tests. Payment provider sandbox tests remain outstanding.
