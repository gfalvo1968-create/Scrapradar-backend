"""Mocked test of read-only canonical billing adapter; no network, no live charge."""
import os
import unittest
from unittest.mock import patch
import live_paypal_reader as reader
from test_paypal_live_evidence import fixture


class LiveReaderTests(unittest.TestCase):
    def test_disabled_in_sandbox_and_without_explicit_live_credentials(self):
        binding, subscription, plan = fixture()
        with patch.dict(os.environ, {"PAYPAL_ENVIRONMENT": "sandbox",
                                     "PAYPAL_LIVE_CLIENT_ID": "test-client",
                                     "PAYPAL_LIVE_CLIENT_SECRET": "test-secret"}):
            with self.assertRaises(RuntimeError):
                reader.read_only_evidence(binding)
        with patch.dict(os.environ, {"PAYPAL_ENVIRONMENT": "live",
                                     "PAYPAL_LIVE_CLIENT_ID": "", "PAYPAL_LIVE_CLIENT_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                reader.read_only_evidence(binding)

    def test_malformed_untrusted_ids_never_fetch(self):
        binding, subscription, plan = fixture()
        binding["subscription_id"] = "https://attacker.invalid/"
        with patch.object(reader, "_request_json") as http:
            self.assertIsNone(reader.read_only_evidence(binding))
            http.assert_not_called()

    def test_still_denies_unverified_or_bad_plan(self):
        binding, subscription, plan = fixture()
        subscription["plan_id"] = "P-WRONG123"
        responses = [{"access_token": "x" * 32, "token_type": "Bearer"}, subscription, plan]
        with patch.dict(os.environ, {"PAYPAL_ENVIRONMENT": "live",
                                     "PAYPAL_LIVE_CLIENT_ID": "mock-client",
                                     "PAYPAL_LIVE_CLIENT_SECRET": "mock-secret"}):
            with patch.object(reader, "_request_json", side_effect=responses) as http:
                self.assertIsNone(reader.read_only_evidence(binding))
                self.assertEqual(http.call_count, 3)
                urls = [item.args[0] for item in http.call_args_list]
                self.assertTrue(all(u.startswith(reader.LIVE_API + "/") for u in urls))

    def test_provider_failure_denies(self):
        binding, subscription, plan = fixture()
        with patch.dict(os.environ, {"PAYPAL_ENVIRONMENT": "live",
                                     "PAYPAL_LIVE_CLIENT_ID": "mock-client",
                                     "PAYPAL_LIVE_CLIENT_SECRET": "mock-secret"}):
            with patch.object(reader, "_request_json", side_effect=RuntimeError("provider unavailable")):
                with self.assertRaises(RuntimeError):
                    reader.read_only_evidence(binding)


if __name__ == "__main__":
    unittest.main()
