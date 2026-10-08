import json,os,unittest
from unittest.mock import patch
import test_paypal_checkout as fixture
import paypal_checkout as p

class WebhookTests(unittest.TestCase):
 buy=fixture.CheckoutTests.buy
 def setUp(self):
  self.provider_failure=False;self.verify="SUCCESS"
  fixture.CheckoutTests.setUp(self)
  self.intent=self.buy().json()['intent'];self.sub=list(self.subs.values())[0]
  self.headers={'paypal-transmission-id':'transmission-123','paypal-transmission-time':'2026-10-08T18:00:00Z','paypal-cert-url':'https://api.sandbox.paypal.com/v1/notifications/certs/CERT-test','paypal-auth-algo':'SHA256withRSA','paypal-transmission-sig':'signature'}
  self.event={'id':'WH-event-123','event_type':'BILLING.SUBSCRIPTION.CANCELLED','resource':{'id':self.sub['id'],'status':'ACTIVE'}}
  self.env2=patch.dict(os.environ,{'PAYPAL_SANDBOX_WEBHOOK_ID':'WEBHOOK123'});self.env2.start()
  self.verify='SUCCESS';self.provider_failure=False
 def tearDown(self):self.env2.stop();fixture.CheckoutTests.tearDown(self)
 def api(self,path,body=None,request_id=None):
  if path=='/v1/notifications/verify-webhook-signature':return {'verification_status':self.verify}
  if self.provider_failure and path.startswith('/v1/billing/subscriptions/'):
   raise p.HTTPException(502,'Provider unavailable')
  return fixture.CheckoutTests.api(self,path,body,request_id)
 def send(self,event=None,headers=None):return self.client.post('/api/paypal/pilot/webhook',json=event or self.event,headers=self.headers if headers is None else headers)
 def state(self):
  c=p.connect();result=c.execute('SELECT state FROM paypal_pilot_intents WHERE id=?',(self.intent,)).fetchone()[0];c.close();return result
 def test_canonical_state_duplicate_and_collision(self):
  self.sub['status']='CANCELLED';self.assertEqual(self.send().json()['outcome'],'reconciled');self.assertEqual(self.state(),'CANCELLED')
  self.assertTrue(self.send().json()['duplicate'])
  changed=dict(self.event,resource={'id':self.sub['id'],'status':'SUSPENDED'});self.assertEqual(self.send(changed).status_code,409)
 def test_failed_signature_no_writes(self):
  self.verify='FAILURE';self.assertEqual(self.send().status_code,403);self.assertEqual(self.state(),'APPROVAL_PENDING')
 def test_missing_headers_and_untrusted_cert(self):
  self.assertEqual(self.send(headers={}).status_code,400)
  self.headers['paypal-cert-url']='https://evil.test/cert';self.assertEqual(self.send().status_code,400)
 def test_retry_after_provider_failure(self):
  self.provider_failure=True;self.assertEqual(self.send().status_code,502)
  self.provider_failure=False;self.sub['status']='CANCELLED';self.assertEqual(self.send().status_code,200);self.assertEqual(self.state(),'CANCELLED')
 def test_unknown_subscription_is_ignored(self):
  self.event['resource']['id']='I-UNKNOWN123';self.assertEqual(self.send().json()['outcome'],'ignored');self.assertEqual(self.state(),'APPROVAL_PENDING')
 def test_live_mode_and_missing_config(self):
  with patch.dict(os.environ,{'PAYPAL_ENVIRONMENT':'live'}):self.assertEqual(self.send().status_code,503)
  with patch.dict(os.environ,{'PAYPAL_SANDBOX_WEBHOOK_ID':''}):self.assertEqual(self.send().status_code,503)
 def test_sale_event_and_stale_activation(self):
  self.event['event_type']='PAYMENT.SALE.COMPLETED';self.event['resource']={'billing_agreement_id':self.sub['id']}
  self.sub['status']='CANCELLED';self.assertEqual(self.send().status_code,200);self.assertEqual(self.state(),'CANCELLED')
 def test_binding_mismatch_and_body_limit(self):
  self.sub['custom_id']='different';self.assertEqual(self.send().status_code,409)
  self.assertEqual(self.client.post('/api/paypal/pilot/webhook',content=b'x'*262145).status_code,413)
