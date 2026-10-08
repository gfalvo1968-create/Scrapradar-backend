# PayPal sandbox pilot

Owner pilot only: verified, confirmed `support@scrapradarfamily.com` customer identity.
`PAYPAL_ENVIRONMENT` must equal `sandbox`; credentials remain on Railway.

Frontend: `sandbox_checkout.html`, same existing Family customer session. Server creates product/plans from membership_catalog and binds each subscription to a durable random intent and verified customer UUID. One intent per customer/plan; retries reuse PayPal-Request-Id. An uncertain create older than 24 hours requires manual reconciliation, rather than risking another subscription. Provider approval links are restricted to sandbox PayPal. Return parameters do not grant membership; authenticated reconciliation reads PayPal directly and checks the bound subscription, plan, custom ID and approved price.

Records use separate `paypal_pilot_*` SQLite tables on the existing persistent volume. They do not populate production memberships. Paid access and public checkout stay off. One pilot subscription per plan is supported; cancel/rejoin and upgrades are not implemented in this pilot.

Validation: backend tests cover prices, identity isolation, tampered binding/plan, no live mode, retries and redirect allowlist. UI tests cover callback verification, authorization, duplicate clicks and live destination rejection. Owner iPad testing on October 8 verified all three prices, ACTIVE state, recorded test payment, and return to site. Family and Scrap Radar cancellation were verified by canonical API reconciliation. Board Sense cancellation was observed in the PayPal Inactive list.

Before production: implement and test verified webhook handling, billing reconciliation, cancellation/rejoin, payment failure policy, support recovery, module access enforcement and board usage limits. Never enable production access based on this pilot or the browser return URL.


## Sandbox notifications

POST `/api/paypal/pilot/webhook` requires `PAYPAL_SANDBOX_WEBHOOK_ID` from a webhook registered on the same sandbox app. Register the endpoint at `https://scrapradar-backend-production.up.railway.app/api/paypal/pilot/webhook`, subscribing to BILLING.SUBSCRIPTION.CREATED, ACTIVATED, UPDATED, SUSPENDED, CANCELLED, EXPIRED, PAYMENT.FAILED and PAYMENT.SALE.COMPLETED, REFUNDED, REVERSED (full event names as in WEBHOOK_EVENTS).

The handler bounds the request body, validates required verification headers and sandbox certificate addresses, and posts verification to PayPal with the configured webhook ID. Only SUCCESS is accepted. It never fetches a caller-supplied URL. Verified events are deduplicated durably by event ID and canonical JSON digest; failures roll back and return non-2xx for provider retry. Supported events for known pilot subscription IDs trigger the same canonical subscription/plan/custom-ID/price checks as the authenticated return path. Delayed event status never overwrites current canonical status. Unrelated subscriptions are ignored. Only test state is updated; no production entitlement is created.

PayPal simulator mock events cannot use postback signature verification. Test real sandbox deliveries; do not weaken signature validation for simulator messages. Webhook registration and real delivery verification remain pending until configured and exercised.
