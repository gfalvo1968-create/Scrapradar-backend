"""Offline assertions only: no payment provider, tokens, or production traffic."""
import unittest
from datetime import datetime, timezone, timedelta
from entitlement_policy import allowed

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 11, 9, 16, 0, tzinfo=timezone.utc)


def good(plan="family"):
    return dict(customer_id=ALICE, environment="live",
        source="verified_provider_reconciliation", verified=True,
        payment_ok=True, state="ACTIVE", plan_id=plan, verified_at=NOW)


class EntitlementTests(unittest.TestCase):
    def test_family_and_single_app_scope(self):
        for module in ("board_sense", "scrap_radar"):
            self.assertTrue(allowed(ALICE, module, good(), NOW))
        self.assertFalse(allowed(ALICE, "board_sense", good("scrap_radar"), NOW))
        self.assertFalse(allowed(ALICE, "scrap_radar", good("board_sense"), NOW))
        self.assertTrue(allowed(ALICE, "board_sense", good("board_sense"), NOW))
        self.assertFalse(allowed(ALICE, "future_unreleased_module", good(), NOW))

    def test_missing_or_wrong_owner_denied(self):
        self.assertFalse(allowed(ALICE, "board_sense", None, NOW))
        self.assertFalse(allowed(BOB, "board_sense", good(), NOW))
        self.assertFalse(allowed("attacker", "board_sense", good(), NOW))

    def test_sandbox_redirect_and_unverified_state_denied(self):
        for key, value in (("environment", "sandbox"), ("source", "browser_callback"),
                           ("verified", False), ("verified", "true"),
                           ("payment_ok", False), ("state", "APPROVED"),
                           ("state", "CANCELLED"), ("state", "SUSPENDED"),
                           ("state", "PAYMENT_FAILED"), ("plan_id", "unknown")):
            record = good(); record[key] = value
            self.assertFalse(allowed(ALICE, "board_sense", record, NOW), key)

    def test_stale_future_naive_and_missing_time_denied(self):
        for stamp in (NOW-timedelta(minutes=16), NOW+timedelta(seconds=1),
                      NOW.replace(tzinfo=None), None):
            record=good(); record["verified_at"]=stamp
            self.assertFalse(allowed(ALICE, "board_sense", record, NOW))

    def test_no_entitlement_when_unverified_even_if_active(self):
        record=good();record.pop("verified")
        self.assertFalse(allowed(ALICE, "board_sense", record, NOW))


if __name__ == "__main__":
    unittest.main()
