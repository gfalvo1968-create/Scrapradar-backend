import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from membership_catalog import catalog, router, PLANS
from membership_records import register_subscription, record_reconciled_state, customer_subscriptions


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SCRAPRADAR_DB_PATH": self.temp.name+"/test.db"})
        self.env.start()

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def test_catalog_prices_and_checkout_disabled(self):
        app=FastAPI();app.include_router(router)
        result=TestClient(app).get('/api/membership-plans').json()
        self.assertEqual([p['amount_cents'] for p in result['plans']], [1995,2995,4495])
        self.assertFalse(result['checkout_enabled'])
        result['plans'][0]['modules'].append('fake')
        self.assertNotIn('fake',catalog()['plans'][0]['modules'])

    def test_customer_isolation_and_binding(self):
        register_subscription('alice','sub1','family')
        self.assertEqual(customer_subscriptions('bob'),[])
        with self.assertRaises(ValueError):register_subscription('bob','sub1','family')

    def test_rate_frozen_when_new_customer_price_changes(self):
        register_subscription('alice','sub1','family')
        with patch.dict(PLANS, {'family': {**PLANS['family'], 'amount_cents': 5495}}):
            register_subscription('bob','sub2','family')
        self.assertEqual(customer_subscriptions('alice')[0]['amount_cents'],4495)
        self.assertEqual(customer_subscriptions('bob')[0]['amount_cents'],5495)

    def test_failure_preserves_rate_without_granting_access(self):
        register_subscription('alice','sub1','family')
        record_reconciled_state('sub1','e1',1,'ACTIVE')
        result=record_reconciled_state('sub1','e2',2,'PAYMENT_FAILED')
        self.assertTrue(customer_subscriptions('alice')[0]['rate_retained'])
        self.assertFalse(result['access_granted'])

    def test_cancel_and_reactivate_does_not_restore_old_rate(self):
        register_subscription('alice','sub1','family')
        record_reconciled_state('sub1','e1',1,'CANCELLED')
        record_reconciled_state('sub1','e2',2,'ACTIVE')
        self.assertFalse(customer_subscriptions('alice')[0]['rate_retained'])

    def test_duplicate_and_delayed_events(self):
        register_subscription('alice','sub1','family')
        r=record_reconciled_state('sub1','e2',2,'ACTIVE')
        self.assertEqual(record_reconciled_state('sub1','e2',2,'ACTIVE'),r)
        self.assertFalse(record_reconciled_state('sub1','e1',1,'CANCELLED')['applied'])
        self.assertEqual(customer_subscriptions('alice')[0]['state'],'ACTIVE')
        with self.assertRaises(ValueError):record_reconciled_state('sub1','e2',2,'CANCELLED')

    def test_unbound_or_invalid_events_rejected(self):
        with self.assertRaises(ValueError):record_reconciled_state('missing','e1',1,'ACTIVE')
        with self.assertRaises(ValueError):record_reconciled_state('missing','e1',1,'FAKE')
