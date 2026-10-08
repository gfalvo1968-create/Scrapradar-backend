import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import paypal_sandbox as paypal


class SandboxTests(unittest.TestCase):
    def setUp(self):
        paypal._cached['until'] = 0
        self.env = patch.dict(os.environ, {'PAYPAL_ENVIRONMENT':'sandbox',
            'PAYPAL_CLIENT_ID':'test-client', 'PAYPAL_CLIENT_SECRET':'never-output-this'})
        self.env.start()
        app = FastAPI(); app.include_router(paypal.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.env.stop(); paypal._cached['until'] = 0

    def test_live_and_missing_configuration_make_no_network_call(self):
        with patch('paypal_sandbox.build_opener') as network:
            with patch.dict(os.environ, {'PAYPAL_ENVIRONMENT':'live'}):
                self.assertFalse(paypal.check_credentials()[0])
            with patch.dict(os.environ, {'PAYPAL_CLIENT_SECRET':''}):
                self.assertFalse(paypal.check_credentials()[0])
            network.assert_not_called()

    def test_success_is_cached_and_never_exposes_token_or_secret(self):
        opener = MagicMock()
        opener.open.return_value = io.BytesIO(json.dumps({
            'access_token':'private-provider-token', 'token_type':'Bearer'}).encode())
        with patch('paypal_sandbox.build_opener', return_value=opener):
            result = self.client.get('/api/paypal/sandbox-status')
            self.client.get('/api/paypal/sandbox-status')
        self.assertEqual(opener.open.call_count, 1)
        self.assertTrue(result.json()['credentials_verified'])
        self.assertFalse(result.json()['checkout_enabled'])
        self.assertFalse(result.json()['paid_access_enabled'])
        self.assertNotIn('private-provider-token',result.text)
        self.assertNotIn('never-output-this',result.text)
        self.assertEqual(result.headers['cache-control'],'no-store')

    def test_provider_rejection_is_safe_and_cached(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError('fixed',401,'secret diagnostic',{},None)
        with patch('paypal_sandbox.build_opener', return_value=opener):
            a = paypal.check_credentials(); b = paypal.check_credentials()
        self.assertEqual(a,(False,'credentials_rejected'))
        self.assertEqual(a,b); self.assertEqual(opener.open.call_count,1)

    def test_redirects_cannot_forward_credentials(self):
        self.assertIsNone(paypal.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid'))
