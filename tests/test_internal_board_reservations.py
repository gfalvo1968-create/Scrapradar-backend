"""Offline tests for unmounted internal reservation receiver: no real payments."""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

import internal_board_reservations as internal
from customer_accounts import verified_customer
from membership_records import register_subscription, record_reconciled_state
from paid_board_quota import paid_board_usage

KEY = "srv-" + "K" * 48


class InternalBoardReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "SCRAPRADAR_DB_PATH": self.tmp.name + "/database.db",
            "SCRAP_RADAR_INTERNAL_BOARD_RESERVATION_ENABLED": "1",
            "SCRAP_RADAR_BOARD_SERVICE_KEY": KEY,
        })
        self.env.start()
        self.alice, self.bob = str(uuid4()), str(uuid4())
        self.app = FastAPI()
        # Mounted ONLY in the offline test application, not production main.py.
        self.app.include_router(internal.router)
        self.client = TestClient(self.app)
        self.auth_ok(self.alice)
        self.headers = {
            "X-SRF-Board-Service-Key": KEY,
            "Authorization": "Bearer " + "X" * 40,
        }
        self.url = "/api/internal/board/cases/reserve"
        self.verifier = patch.object(internal, "verify_production_paid_entitlement", return_value=True)
        self.verifier.start()

    def tearDown(self):
        self.verifier.stop()
        self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    def auth_ok(self, customer_id):
        self.app.dependency_overrides[verified_customer] = lambda: {"id": customer_id, "email": "verified@example.invalid"}

    def member(self, customer_id=None, plan="family", state="ACTIVE"):
        customer_id = customer_id or self.alice
        sub = str(uuid4())
        register_subscription(customer_id, sub, plan)
        record_reconciled_state(sub, str(uuid4()), 1, state)
        return sub

    def post(self, body=None, headers=None):
        return self.client.post(self.url, json=body or {"case_id": str(uuid4())}, headers=self.headers if headers is None else headers)

    def test_disabled_by_default_even_with_paid_fixture(self):
        self.member()
        with patch.dict(os.environ, {"SCRAP_RADAR_INTERNAL_BOARD_RESERVATION_ENABLED": ""}):
            r = self.post()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(paid_board_usage(self.alice).used_today, 0)

    def test_invalid_service_credential_denied_before_customer_lookup(self):
        for key in ("", "other-key", "bad\nkey"):
            headers = dict(self.headers, **{"X-SRF-Board-Service-Key": key})
            with self.subTest(key=key):
                self.assertEqual(self.post(headers=headers).status_code, 403)
        self.assertEqual(paid_board_usage(self.alice).used_today, 0)

    def test_short_server_config_fails_closed(self):
        for key in ("", "too-short", "a" * 40 + " "):
            with self.subTest(length=len(key)), patch.dict(os.environ, {"SCRAP_RADAR_BOARD_SERVICE_KEY": key}):
                self.assertEqual(self.post().status_code, 503)

    def test_customer_identity_must_be_verified_on_backend(self):
        self.app.dependency_overrides.clear()
        self.member()
        # The actual verified_customer dependency requires a bearer token
        # accepted by the Auth service, not a caller-posted user ID.
        r = self.post(headers={"X-SRF-Board-Service-Key": KEY})
        self.assertEqual(r.status_code, 401)

    def test_real_production_payment_verifier_is_unimplemented_and_closed(self):
        self.verifier.stop()
        self.member()
        try:
            r = self.post()
            self.assertEqual(r.status_code, 503, r.text)
            self.assertEqual(paid_board_usage(self.alice).used_today, 0)
        finally:
            self.verifier.start()

    def test_false_payment_proof_cannot_unlock_even_with_active_membership(self):
        self.member()
        with patch.object(internal, "verify_production_paid_entitlement", return_value=False):
            r = self.post()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(paid_board_usage(self.alice).used_today, 0)

    def test_mock_provider_verified_family_can_reserve_once(self):
        self.member()
        case_id = str(uuid4())
        r = self.post({"case_id": case_id})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["case_id"], case_id)
        self.assertTrue(data["allowed"])
        self.assertEqual(data["usage"]["limit"], 25)
        self.assertEqual(data["usage"]["remaining"], 24)
        self.assertEqual(r.headers["cache-control"], "no-store")
        duplicate = self.post({"case_id": case_id})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(paid_board_usage(self.alice).used_today, 1)

    def test_no_entitlement_or_scrap_radar_only_is_denied(self):
        self.assertEqual(self.post().status_code, 403)
        self.member(plan="scrap_radar")
        self.assertEqual(self.post().status_code, 403)

    def test_cancelled_member_cannot_start_new_case(self):
        self.member(state="CANCELLED")
        self.assertEqual(self.post().status_code, 403)

    def test_25_allowed_then_26th_denied(self):
        self.member(plan="board_sense")
        for i in range(25):
            r = self.post()
            self.assertEqual(r.status_code, 200, f"Case {i+1}: {r.text}")
        self.assertEqual(self.post().status_code, 429)

    def test_browser_posted_plan_customer_or_quota_is_rejected(self):
        self.member()
        for extra in ({"customer_id": self.bob}, {"plan": "family"}, {"limit": 10000}, {"paid": True}):
            with self.subTest(extra=extra):
                self.assertEqual(self.post(dict({"case_id": str(uuid4())}, **extra)).status_code, 422)
        self.assertEqual(paid_board_usage(self.alice).used_today, 0)

    def test_case_id_validation(self):
        self.member()
        for entry in ("arbitrary", None, 123, "", "malformed-id"):
            with self.subTest(entry=entry):
                self.assertEqual(self.post({"case_id": entry}).status_code, 422)
        self.assertEqual(paid_board_usage(self.alice).used_today, 0)

    def test_cross_customer_case_reuse_denied(self):
        self.member()
        self.member(self.bob)
        id = str(uuid4())
        self.assertEqual(self.post({"case_id": id}).status_code, 200)
        self.auth_ok(self.bob)
        self.assertEqual(self.post({"case_id": id}).status_code, 409)
        self.assertEqual(paid_board_usage(self.bob).used_today, 0)

    def test_database_outage_does_not_enable_access(self):
        self.member()
        with patch.object(internal, "reserve_paid_board_case", side_effect=sqlite3.OperationalError("offline")):
            r = self.post()
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("offline", r.text)


if __name__ == "__main__":
    unittest.main()
