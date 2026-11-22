"""Offline regression tests for internal (not live) paid quota foundation."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import paid_board_quota as quota
from membership_records import register_subscription, record_reconciled_state


class PaidBoardQuotaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SCRAPRADAR_DB_PATH": self.temp.name + "/db.sqlite"})
        self.env.start()
        self.alice = str(uuid4())
        self.bob = str(uuid4())
        self.at = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
        self.subscriptions = []

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def activate(self, customer, plan):
        sub = str(uuid4())
        register_subscription(customer, sub, plan)
        record_reconciled_state(sub, str(uuid4()), 1, "ACTIVE")
        self.subscriptions.append(sub)
        return sub

    def case(self):
        return str(uuid4())

    def test_no_subscription_and_scrap_radar_only_do_not_get_board_quota(self):
        case_id = self.case()
        self.assertFalse(quota.reserve_paid_board_case(self.alice, case_id, now=self.at).allowed)
        self.activate(self.alice, "scrap_radar")
        result = quota.reserve_paid_board_case(self.alice, case_id, now=self.at)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "no_reconciled_active_plan")
        self.assertTrue(quota.has_reconciled_module(self.alice, "scrap_radar"))
        self.assertFalse(quota.has_reconciled_module(self.alice, "board_sense"))
        self.assertEqual(result.used_today, 0)

    def test_board_and_family_enable_only_registered_modules(self):
        self.activate(self.alice, "board_sense")
        self.assertTrue(quota.has_reconciled_module(self.alice, "board_sense"))
        self.assertFalse(quota.has_reconciled_module(self.alice, "scrap_radar"))
        self.activate(self.bob, "family")
        for module in ("scrap_radar", "board_sense"):
            self.assertTrue(quota.has_reconciled_module(self.bob, module))
        self.assertFalse(quota.has_reconciled_module(self.bob, "admin"))
        self.assertFalse(quota.has_reconciled_module(self.bob, "unreleased_private_module"))

    def test_one_case_many_photos_and_idempotent_retry_count_once(self):
        self.activate(self.alice, "family")
        case_id = self.case()
        a = quota.reserve_paid_board_case(self.alice, case_id, now=self.at)
        b = quota.reserve_paid_board_case(self.alice, case_id, now=self.at)
        self.assertTrue(a.allowed and b.allowed)
        self.assertEqual(a.reason, "reserved")
        self.assertEqual(b.reason, "already_counted")
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).used_today, 1)
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).remaining, 24)
        self.assertTrue(quota.finish_paid_board_case(self.alice, case_id))
        self.assertTrue(quota.finish_paid_board_case(self.alice, case_id))
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).used_today, 1)

    def test_25_case_limit_and_utc_reset(self):
        self.activate(self.alice, "board_sense")
        for _ in range(25):
            self.assertTrue(quota.reserve_paid_board_case(self.alice, self.case(), now=self.at).allowed)
        blocked = quota.reserve_paid_board_case(self.alice, self.case(), now=self.at)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.reason, "daily_limit_reached")
        self.assertEqual(blocked.used_today, 25)
        self.assertEqual(blocked.remaining, 0)
        tomorrow = self.at + timedelta(days=1)
        self.assertEqual(quota.paid_board_usage(self.alice, now=tomorrow).used_today, 0)
        self.assertTrue(quota.reserve_paid_board_case(self.alice, self.case(), now=tomorrow).allowed)

    def test_release_on_trusted_failure_reclaims_one_credit_but_cannot_reuse_id(self):
        self.activate(self.alice, "family")
        case_id = self.case()
        self.assertTrue(quota.reserve_paid_board_case(self.alice, case_id, now=self.at).allowed)
        self.assertTrue(quota.release_failed_paid_board_case(self.alice, case_id))
        self.assertTrue(quota.release_failed_paid_board_case(self.alice, case_id))
        self.assertFalse(quota.finish_paid_board_case(self.alice, case_id))
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).used_today, 0)
        repeated = quota.reserve_paid_board_case(self.alice, case_id, now=self.at)
        self.assertFalse(repeated.allowed)
        self.assertEqual(repeated.reason, "case_released")
        self.assertTrue(quota.reserve_paid_board_case(self.alice, self.case(), now=self.at).allowed)

    def test_completed_case_cannot_be_released_to_game_limit(self):
        self.activate(self.alice, "board_sense")
        case_id = self.case()
        self.assertTrue(quota.reserve_paid_board_case(self.alice, case_id, now=self.at).allowed)
        self.assertTrue(quota.finish_paid_board_case(self.alice, case_id))
        self.assertFalse(quota.release_failed_paid_board_case(self.alice, case_id))
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).used_today, 1)

    def test_cancelled_and_expired_subscriptions_cannot_reserve_new_cases(self):
        sub = self.activate(self.alice, "family")
        self.assertTrue(quota.reserve_paid_board_case(self.alice, self.case(), now=self.at).allowed)
        record_reconciled_state(sub, str(uuid4()), 2, "CANCELLED")
        self.assertFalse(quota.reserve_paid_board_case(self.alice, self.case(), now=self.at).allowed)
        self.assertFalse(quota.has_reconciled_module(self.alice, "scrap_radar"))
        self.assertEqual(quota.paid_board_usage(self.alice, now=self.at).used_today, 1)

    def test_customer_isolation_and_case_binding(self):
        self.activate(self.alice, "family")
        self.activate(self.bob, "family")
        case_id = self.case()
        self.assertTrue(quota.reserve_paid_board_case(self.alice, case_id, now=self.at).allowed)
        self.assertEqual(quota.paid_board_usage(self.bob, now=self.at).used_today, 0)
        with self.assertRaisesRegex(ValueError, "bound to another account"):
            quota.reserve_paid_board_case(self.bob, case_id, now=self.at)
        self.assertFalse(quota.finish_paid_board_case(self.bob, case_id))
        self.assertFalse(quota.release_failed_paid_board_case(self.bob, case_id))

    def test_rejects_invalid_ids_and_naive_dates(self):
        self.activate(self.alice, "board_sense")
        with self.assertRaises(ValueError):
            quota.reserve_paid_board_case(self.alice, "caller-chosen", now=self.at)
        with self.assertRaises(ValueError):
            quota.reserve_paid_board_case("bad-account", self.case(), now=self.at)
        with self.assertRaises(ValueError):
            quota.reserve_paid_board_case(self.alice, self.case(), now=datetime(2026, 11, 22))


if __name__ == "__main__":
    unittest.main()
