# PayPal sandbox pilot

Owner pilot only: verified, confirmed `support@scrapradarfamily.com` customer identity.
`PAYPAL_ENVIRONMENT` must equal `sandbox`; credentials remain on Railway.

Frontend: `sandbox_checkout.html`, same existing Family customer session. Server creates product/plans from membership_catalog and binds each subscription to a durable random intent and verified customer UUID. One current attempt per customer/plan; retries reuse PayPal-Request-Id. An uncertain create older than 24 hours requires manual reconciliation, rather than risking another subscription. Provider approval links are restricted to sandbox PayPal. Return parameters do not grant membership; authenticated reconciliation reads PayPal directly and checks the bound subscription, plan, custom ID and approved price.

Records use separate `paypal_pilot_*` SQLite tables on the existing persistent volume. They do not populate production memberships. Paid access and public checkout stay off. A fresh owner test can be started only after PayPal confirms the latest subscription is CANCELLED or EXPIRED. Earlier intents and subscription IDs are retained for reconciliation and late webhooks. Active, suspended, pending and uncertain attempts are reused; upgrades and production rejoin policy are not implemented. The original one-attempt database constraint is migrated atomically without deleting records.

Validation: backend tests cover prices, identity isolation, tampered binding/plan, no live mode, retries and redirect allowlist. UI tests cover callback verification, authorization, duplicate clicks and live destination rejection. Owner iPad testing on October 8 verified all three prices, ACTIVE state, recorded test payment, and return to site. Family and Scrap Radar cancellation were verified by canonical API reconciliation. Board Sense cancellation was observed in the PayPal Inactive list.

Before production: implement and test verified webhook handling, billing reconciliation, cancellation/rejoin, payment failure policy, support recovery, module access enforcement and board usage limits. Never enable production access based on this pilot or the browser return URL.


## Sandbox notifications

POST `/api/paypal/pilot/webhook` requires `PAYPAL_SANDBOX_WEBHOOK_ID` from a webhook registered on the same sandbox app. Register the endpoint at `https://scrapradar-backend-production.up.railway.app/api/paypal/pilot/webhook`, subscribing to BILLING.SUBSCRIPTION.CREATED, ACTIVATED, UPDATED, SUSPENDED, CANCELLED, EXPIRED, PAYMENT.FAILED and PAYMENT.SALE.COMPLETED, REFUNDED, REVERSED (full event names as in WEBHOOK_EVENTS).

The handler bounds the request body, validates required verification headers and sandbox certificate addresses, and posts verification to PayPal with the configured webhook ID. Only SUCCESS is accepted. It never fetches a caller-supplied URL. Verified events are deduplicated durably by event ID and canonical JSON digest; failures roll back and return non-2xx for provider retry. Supported events for known pilot subscription IDs trigger the same canonical subscription/plan/custom-ID/price checks as the authenticated return path. Delayed event status never overwrites current canonical status. Unrelated subscriptions are ignored. Only test state is updated; no production entitlement is created.

PayPal simulator mock events cannot use postback signature verification. Test real sandbox deliveries; do not weaken signature validation for simulator messages. The sandbox webhook was registered on October 10 with the seven BILLING.SUBSCRIPTION events above and PAYMENT.SALE.COMPLETED. PAYMENT.SALE.REFUNDED and REVERSED are supported by the handler but were not offered in the dashboard selection and are not registered. The webhook ID is configured on Railway. Real signed delivery verification remains pending.

## November 22, 2026: signed sandbox delivery acceptance runbook

**Observed today:** Railway service `Scrapradar-backend` is online with one healthy replica and a persistent volume. The environment includes variable names `PAYPAL_ENVIRONMENT`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_SANDBOX_WEBHOOK_ID`; connector access redacts their values, so this observation does not independently verify correctness or that `PAYPAL_ENVIRONMENT=sandbox`. The repo has offline tests `tests/test_paypal_webhook.py` for signature rejection, duplicates, canonical reconciliation, unknown IDs and provider failure; these unit tests mock PayPal and **are not proof of a real signed delivery**. Historical Railway log query contained no matching webhook requests in retained results; that is not proof of zero events.

**Official PayPal provider guidance:**
- Event dashboard: https://developer.paypal.com/api/rest/webhooks/events-dashboard/ (choose **Sandbox Webhooks Events**, not Live). Dashboard searches cover **the last 30 days**, and existing events can be **Resent**.
- Real signed provider delivery must use the same Sandbox PayPal REST app that created the subscription and the configured webhook ID. The Webhooks simulator creates mock events that **cannot pass** PayPal's `verify-webhook-signature` postback check. Do not disable signature validation to accommodate a simulator.

### Owner-safe end-to-end test, no real money

1. In PayPal Developer, open **Sandbox Webhooks Events** and choose the app associated with our sandbox test subscription. Never choose Live. Review any legitimate recent event, its type, target and delivery status. Do not paste client secrets, account passwords, full bearer tokens or card information into notes/screenshots.
2. If there is a real recent event, use **Resend** **once** for a supported event, such as `BILLING.SUBSCRIPTION.CANCELLED` on an existing sandbox test subscription. Resending must **not** create or charge a new subscription. If no recent event exists, this step is **BLOCKED** until an owner-authorized new sandbox-only test creates an event. PayPal event dashboard filters are limited to 30 days.
3. Inspect the delivery result at the provider and correlate its time with Railway `POST /api/paypal/pilot/webhook` proxy logs (expect HTTP 2xx). A 403 denotes failed signature verification, 400 malformed headers/message, 502 upstream PayPal or canonical provider trouble, 503 missing sandbox config/database; do not replace fail-closed behavior with blind HTTP 200.
4. Verify persistent `paypal_pilot_events` storage in the authorized sandbox test environment: same event ID/digest and `reconciled` or `ignored` outcome. For known subscriptions confirm the `paypal_pilot_intents.state` matches **fresh canonical PayPal state**, not stale event payload. The current webhook has no admin audit read endpoint, so an HTTP 200 alone proves reception/handler success but not an independently reviewed ledger row. Use authorized server-side test/inspection, never expose the ledger to unauthenticated browsers.
5. Resend the **same** verified event once after confirming the first. It should return HTTP 2xx, classify as **duplicate**, and create no second ledger row, paid entitlement, or additional subscription. If the dashboard marks delivery failed, inspect the reason rather than retrying checkout and risking a duplicate charge.
6. Run signed sandbox tests for an activated payment and cancelled/expired/failed payment case, plus out-of-order and invalid-signature cases. Verify every provider/ledger/entitlement transition before approving live billing. Never use a returned browser URL to grant paid access.

**Exit criterion:** a real signed sandbox notification has been delivered, signature postback returned SUCCESS, storage proved idempotent, canonical subscription state matched PayPal, and retry/rollback controls checked. Until then, set result **NEEDS REAL PROVIDER DELIVERY**; checkout and paid entitlement remain disabled. Keep test records and callbacks entirely separate from live customer records.
