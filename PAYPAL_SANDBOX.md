# PayPal sandbox pilot

Owner pilot only: verified, confirmed `support@scrapradarfamily.com` customer identity.
`PAYPAL_ENVIRONMENT` must equal `sandbox`; credentials remain on Railway.

Frontend: `sandbox_checkout.html`, same existing Family customer session. Server creates product/plans from membership_catalog and binds each subscription to a durable random intent and verified customer UUID. One intent per customer/plan; retries reuse PayPal-Request-Id. An uncertain create older than 24 hours requires manual reconciliation, rather than risking another subscription. Provider approval links are restricted to sandbox PayPal. Return parameters do not grant membership; authenticated reconciliation reads PayPal directly and checks the bound subscription, plan, custom ID and approved price.

Records use separate `paypal_pilot_*` SQLite tables on the existing persistent volume. They do not populate production memberships. Paid access and public checkout stay off. One pilot subscription per plan is supported; cancel/rejoin and upgrades are not implemented in this pilot.

Validation: backend tests cover prices, identity isolation, tampered binding/plan, no live mode, retries and redirect allowlist. UI tests cover callback verification, authorization, duplicate clicks and live destination rejection. Actual owner browser approval and test-money movement still require live sandbox testing.

Before production: implement and test verified webhook handling, billing reconciliation, cancellation/rejoin, payment failure policy, support recovery, module access enforcement and board usage limits. Never enable production access based on this pilot or the browser return URL.
