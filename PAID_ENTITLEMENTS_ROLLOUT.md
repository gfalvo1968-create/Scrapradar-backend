# Paid member access and board quota: safe foundation (draft)

**Status: branch-only, internal implementation, NOT DEPLOYED.**
Keep checkout disabled and paid app access off. The PayPal owner sandbox pilot is
separate from production subscriptions and MUST NOT confer real entitlements.

## Implemented on this branch

`paid_board_quota.py` is a server-internal engine, not a FastAPI router.

- Looks up the currently ACTIVE plan in the **trusted** `membership_records`
  ledger. Board Sense members and Family members qualify; Scrap Radar-only
  members do not. Other/private modules are not accessible simply because a
  Family plan promises future software.
- Atomically reserves one slot per **physical board case** (not per photo).
  Repeated requests using the *same trusted, server-generated case UUID* are
  idempotently rejected for repeat processing: a duplicate request must
  retrieve/poll the original case result rather than run a second free scan.
  A case UUID from yesterday cannot be reused today. A 2–6-photo analysis
  of one physical board must keep the same ID.
- Enforces **25 board cases per customer per UTC day** in a persistent SQLite
  transaction, tracked by authenticated customer UUID.
- Finalizes successful cases and permits server-controlled release of *failed*
  reservations. A completed case cannot be refunded, and a released ID cannot
  be reused. The accounting remains stable across concurrent API replicas
  using the shared persistent database.
- Checks that an existing case ID belongs to the same authenticated customer.
  Ignores arbitrary user metadata and browser assertions about payment status.
- Includes offline regression tests for plan coverage, denied unverified access,
  cross-customer isolation, duplicate analysis prevention, old case reuse,
  36 simultaneous quota requests (exactly 25 accepted), UTC reset,
  cancellation, failed-payment denial and failure-credit idempotency.

## Critical prerequisites before connecting to public Board Sense

1. **Production verification**: Implement a *separate* production PayPal
   reconciliation worker which validates signature, canonical subscription
   ID, verified customer binding, frozen offer and actual plan price before
   updating `membership_records`. No such path exists yet. The existing
   `paypal_pilot_*` tables **must never** migrate to production entitlements.
   A member ledger marked ACTIVE is *not alone* proof of provider payment until
   this verification step is completed. Keep the free sampler separate.
2. **Cross-service authentication**: Board Sense and Scrap Radar API run on
   different servers. Authenticate the actual customer's token online, verify
   the exact entitlement on the trusted backend and use server-to-server
   authorization with secret material that browsers cannot read. Never accept
   a posted user ID, plan name, quota reset, or client-generated paid status.
   Quota reservation must occur just once after image validation and before
   potentially expensive analysis, including 2–6-photo cases.
3. **Failure boundary**: If the usage database or provider verification is
   unavailable, fail closed without reverting to the anonymous free-account
   limit or unrestricted access. Define exactly which errors warrant a
   restored credit (server failures) versus a spent case (completed analyses).
   Never use a user-triggered release endpoint. Confirm the outcome under
   concurrent requests, mid-analysis crashes and midnight UTC rollover.
4. **Owner decisions**: UTC midnight is a proposed reset boundary; obtain
   approval or change to an explicitly supported timezone. Specify refunds,
   failed-renewal grace period and founder-rate retention independently from
   the temporary ability to use a program. Preserve active subscribers'
   grandfathered Family offer, including future published software modules,
   within the published usage allowances.
5. **Production rollout**: Add account portal and quota visibility only after
   server access controls are verified. Test real PayPal signed webhooks,
   cancellations, suspension/rejoin, event replay, duplicate requests, quota
   contention, separate accounts and recovery from provider outages. Then use
   staged deployment and a controlled *live* owner transaction only with
   explicit approval. Keep public paid checkout disabled until signoff.

## Important design boundary

This file is **not a billing integration**. Do not import the quota module
into any public route to grant access on the strength of a Sandbox event,
client-side return page, or a raw `state='ACTIVE'` test fixture.
PayPal sandbox cancellation tests and real signed sandbox webhook deliveries
have already been completed; the remaining work is production validation and
server-enforced access.

## Internal receiver contract (added in this draft, NOT MOUNTED)

`internal_board_reservations.py` defines the previously missing receiving
route `POST /api/internal/board/cases/reserve` with a strict
`{"case_id":"<uuid>"}` request body. This router is **not imported into
`main.py`** and is therefore unreachable on the deployed app. It requires:

- Explicit internal feature switch plus a high-entropy `X-SRF-Board-Service-Key`
  supplied by Board Sense (constant-time comparison).
- A genuine **customer token independently checked** by the existing managed
  Auth service using `verified_customer`, without trusting a caller-supplied
  account UUID, plan, or price.
- A **separate production payment verifier** that is currently intentionally
  unimplemented and always raises **HTTP 503**. Even an internal test database
  containing an ACTIVE subscription cannot defeat this security gate.
- A trusted active plan in the membership ledger before any atomic reservation.

Expected responses in *isolated mocked tests*: 200 and same case UUID/remaining
quota if all trusted gates pass; 401 for missing customer identity; 403 for
invalid server credential or inactive plan; 429 for daily exhaustion; 409 for
duplicate/cross-account case; 503 for disabled service, payment verifier
unavailability or database failure. No bearer tokens, credential values or
payments are logged or returned.

**Do not wire this router into production or Board Sense until production
reconciliation exists and the staging integration is tested end to end.**
