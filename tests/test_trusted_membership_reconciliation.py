"""Offline trust-chain tests; no secrets, no calls to the actual PayPal API."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from live_subscription_bindings import create_pending, attach_subscription
from trusted_membership_reconciliation import reconcile_customer_access

ALICE="11111111-1111-4111-8111-111111111111"
BOB="22222222-2222-4222-8222-222222222222"


def evidence(owner, plan, **overrides):
    return dict(customer_id=owner, plan_id=plan, environment="live",
        source="verified_provider_reconciliation", verified=True,
        payment_ok=True, state="ACTIVE",
        verified_at=datetime.now(timezone.utc), **overrides)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {"SCRAPRADAR_DB_PATH":self.temp.name+"/db"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def make(self, owner, plan, subscription):
        intent=create_pending(owner,plan,"P-ABCDE123")
        attach_subscription(intent,subscription)
        return intent

    def test_pending_subscription_never_grants(self):
        create_pending(ALICE,"family","P-ABCDE123")
        with patch("trusted_membership_reconciliation.read_only_evidence") as provider:
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":False,"board_sense":False})
            provider.assert_not_called()

    def test_family_unlocks_both_only_for_correct_owner(self):
        self.make(ALICE,"family","I-ABCDE123")
        with patch("trusted_membership_reconciliation.read_only_evidence",
                   return_value=evidence(ALICE,"family")) as provider:
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":True,"board_sense":True})
            self.assertEqual(reconcile_customer_access(BOB),
                             {"scrap_radar":False,"board_sense":False})
            self.assertEqual(provider.call_count,1)
            self.assertEqual(provider.call_args.args[0]["customer_id"],ALICE)

    def test_separate_purchases_unlock_only_their_modules(self):
        self.make(ALICE,"scrap_radar","I-ABCDE123")
        with patch("trusted_membership_reconciliation.read_only_evidence",
                   return_value=evidence(ALICE,"scrap_radar")):
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":True,"board_sense":False})
        self.make(ALICE,"board_sense","I-ABCDE456")
        def verified(binding):
            return evidence(ALICE,binding["plan_id"])
        with patch("trusted_membership_reconciliation.read_only_evidence",
                   side_effect=verified):
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":True,"board_sense":True})

    def test_wrong_customer_and_cancelled_status_denied(self):
        self.make(ALICE,"family","I-ABCDE123")
        for bad in (evidence(BOB,"family"),
                    dict(evidence(ALICE,"family"),state="CANCELLED"),
                    dict(evidence(ALICE,"family"),payment_ok=False),
                    dict(evidence(ALICE,"family"),environment="sandbox")):
            with patch("trusted_membership_reconciliation.read_only_evidence",
                       return_value=bad):
                self.assertEqual(reconcile_customer_access(ALICE),
                                 {"scrap_radar":False,"board_sense":False})

    def test_provider_error_and_invalid_customer_fail_closed(self):
        self.make(ALICE,"family","I-ABCDE123")
        with patch("trusted_membership_reconciliation.read_only_evidence",
                   side_effect=RuntimeError("provider unavailable")):
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":False,"board_sense":False})
        self.assertEqual(reconcile_customer_access("attacker"),
                         {"scrap_radar":False,"board_sense":False})

    def test_one_bad_subscription_does_not_override_another(self):
        self.make(ALICE,"family","I-ABCDE123")
        self.make(ALICE,"scrap_radar","I-ABCDE456")
        def maybe(binding):
            if binding["plan_id"]=="family":
                raise RuntimeError("provider timeout")
            return evidence(ALICE,"scrap_radar")
        with patch("trusted_membership_reconciliation.read_only_evidence",
                   side_effect=maybe):
            self.assertEqual(reconcile_customer_access(ALICE),
                             {"scrap_radar":True,"board_sense":False})


if __name__ == "__main__":
    unittest.main()
