# Scrapradar-backend
Scrapradar finds best prices 

## Saved operating rates

`GET /api/profile` and `POST /api/update-profile` store cost per vehicle mile,
hourly target and processing cost per pound. All three rates start unknown.
The frontend offers labeled opt-in examples; they are not automatic defaults.
Requests use a private 256-bit browser bearer credential (`srp_` plus 64 hex
characters). Only its SHA-256 hash is stored as the profile owner key; a posted
`user_id` cannot select another profile. This is a browser profile, not account
sign-in or cross-device synchronization. Never log or put credentials in URLs.

SQLite uses `SCRAPRADAR_DB_PATH`, or `RAILWAY_VOLUME_MOUNT_PATH/scrapradar.db`.
Railway deployments without persistent storage fail profile requests with 503
instead of silently saving into an ephemeral container. Market routes remain
available. The browser retains a local copy when the profile service is offline.
Local development defaults to `data/scrapradar.db`; do not commit that database.

`POST /api/calculate-yield` accepts scrap metadata and an explicit
`recovered_metals` list of fine-metal grams and buyer percentages. Category or
grade never manufactures a yield. It uses the existing sourced market provider.
One-way `distance_miles` is doubled, labor is entered in hours and
`processing_weight_lbs` is the material actually processed. Unknown quantities
or rates stay unknown; enter zero explicitly where an expense does not apply.
Additional costs are entered once as `other_costs`. Net proceeds require all
applicable buyer terms and costs and current dated benchmarks. The result is a
scenario, not a guaranteed profit, assay or sell/hold forecast.

Run the isolated profile checks with:

```sh
python -m unittest discover -s tests -p 'test_operating_profiles.py'
```
