import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from live_subscription_bindings import create_pending, attach_subscription, customer_binding

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"SCRAPRADAR_DB_PATH": self.temp.name+"/test.db"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_owner_binding_and_immutable_provider_reference(self):
        intent=create_pending(ALICE,"family","P-ABCDEF123")
        self.assertIsNone(customer_binding(ALICE,intent))
        attach_subscription(intent,"I-ABCDEF123")
        binding=customer_binding(ALICE,intent)
        self.assertEqual(binding["customer_id"],ALICE)
        self.assertEqual(binding["plan_id"],"family")
        self.assertEqual(binding["custom_id"],intent)
        self.assertEqual(binding["subscription_id"],"I-ABCDEF123")
        self.assertIsNone(customer_binding(BOB,intent))
        attach_subscription(intent,"I-ABCDEF123")  # Idempotent same binding
        with self.assertRaises(ValueError):
            attach_subscription(intent,"I-DIFFERENT123")

    def test_cannot_rebind_sub_to_second_account_or_plan(self):
        first=create_pending(ALICE,"board_sense","P-ABCDEF123")
        second=create_pending(BOB,"family","P-ABCDEF123")
        attach_subscription(first,"I-ABCDEF123")
        with self.assertRaises(ValueError):
            attach_subscription(second,"I-ABCDEF123")
        self.assertIsNone(customer_binding(BOB,second))

    def test_invalid_identifiers_rejected_without_making_binding(self):
        for owner,plan,provider in [
            ("bad","family","P-ABCDEF123"),
            (ALICE,"fake","P-ABCDEF123"),
            (ALICE,"family","https://evil.invalid"),
        ]:
            with self.assertRaises(ValueError):
                create_pending(owner,plan,provider)
        intent=create_pending(ALICE,"scrap_radar","P-ABCDEF123")
        for value in ("I-../secret", "https://evil.invalid", ""):
            with self.assertRaises(ValueError):
                attach_subscription(intent,value)
        with self.assertRaises(ValueError):
            attach_subscription("00000000-0000-4000-8000-000000000000","I-ABCDEF123")
        self.assertIsNone(customer_binding(ALICE,intent))

    def test_intents_unique_and_do_not_grant_access(self):
        first=create_pending(ALICE,"family","P-ABCDEF123")
        second=create_pending(ALICE,"family","P-ABCDEF123")
        self.assertNotEqual(first,second)
        self.assertIsNone(customer_binding(ALICE,first))
        self.assertIsNone(customer_binding(ALICE,second))


if __name__ == "__main__":
    unittest.main()
