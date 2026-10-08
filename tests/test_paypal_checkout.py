import os,tempfile,unittest
from unittest.mock import patch
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
import paypal_checkout as p
from customer_accounts import verified_customer
OWNER={'id':'11111111-1111-4111-8111-111111111111','email':'support@scrapradarfamily.com'}
class CheckoutTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'SCRAPRADAR_DB_PATH':self.tmp.name+'/db','PAYPAL_ENVIRONMENT':'sandbox'});self.env.start()
  self.app=FastAPI();self.app.include_router(p.router);self.app.dependency_overrides[verified_customer]=lambda:OWNER
  self.client=TestClient(self.app);self.calls=[];self.subs={};self.plans={};self.mock=patch('paypal_checkout.api',side_effect=self.api);self.mock.start()
 def tearDown(self):self.mock.stop();self.env.stop();self.tmp.cleanup()
 def api(self,path,body=None,request_id=None):
  self.calls.append((path,body,request_id))
  if path=='/v1/catalogs/products':return {'id':'PROD-ABCDE123'}
  if path=='/v1/billing/plans':
   id='P-ABCDE'+str(len(self.plans)+1);self.plans[id]=dict(body,id=id);return self.plans[id]
  if path.startswith('/v1/billing/plans/'):return self.plans[path.split('/')[-1]]
  if path=='/v1/billing/subscriptions':
   id='I-ABCDE'+str(len(self.subs)+1);self.subs[id]=dict(body,id=id,status='ACTIVE',billing_info={'last_payment':{'amount':{'value':'44.95','currency_code':'USD'}}})
   return dict(self.subs[id],links=[{'rel':'approve','href':'https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=test'}])
  return self.subs[path.split('/')[-1]]
 def buy(self,plan='family'):return self.client.post('/api/paypal/pilot/checkout',json={'plan':plan})
 def test_prices_and_duplicate_retries(self):
  for name,expected in [('scrap_radar','19.95'),('board_sense','29.95'),('family','44.95')]:
   a=self.buy(name);b=self.buy(name);self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json(),b.json())
   plan=list(self.plans.values())[-1];self.assertEqual(plan['billing_cycles'][0]['pricing_scheme']['fixed_price']['value'],expected);self.assertEqual(len(plan['billing_cycles']),1)
  self.assertEqual(len(self.subs),3)
 def test_posted_identity_price_and_unknown_plan_rejected(self):
  self.assertEqual(self.buy('cheap').status_code,422)
  self.assertEqual(self.client.post('/api/paypal/pilot/checkout',json={'plan':'family','amount':1,'customer_id':'other'}).status_code,422);self.assertEqual(self.calls,[])
 def test_owner_live_and_unsigned_gates(self):
  self.app.dependency_overrides[verified_customer]=lambda:dict(OWNER,email='other@example.com');self.assertEqual(self.buy().status_code,403)
  self.app.dependency_overrides[verified_customer]=lambda:OWNER
  with patch.dict(os.environ,{'PAYPAL_ENVIRONMENT':'live'}):self.assertEqual(self.buy().status_code,503)
  self.app.dependency_overrides.clear();self.assertEqual(self.buy().status_code,401);self.assertEqual(self.calls,[])
 def test_provider_reconciliation_isolated_no_paid_grant(self):
  intent=self.buy().json()['intent'];d=self.client.get('/api/paypal/pilot/intents/'+intent+'?status=ACTIVE&paid=true').json()
  self.assertTrue(d['test_payment_recorded']);self.assertFalse(d['paid_access_enabled'])
  self.app.dependency_overrides[verified_customer]=lambda:dict(OWNER,id='22222222-2222-4222-8222-222222222222')
  self.assertEqual(self.client.get('/api/paypal/pilot/intents/'+intent).status_code,404)
 def test_tampered_binding_and_price_fail_closed(self):
  intent=self.buy().json()['intent'];sub=list(self.subs.values())[0];sub['custom_id']='wrong'
  self.assertEqual(self.client.get('/api/paypal/pilot/intents/'+intent).status_code,409);sub['custom_id']=intent
  list(self.plans.values())[0]['billing_cycles'][0]['pricing_scheme']['fixed_price']['value']='0.01'
  self.assertEqual(self.client.get('/api/paypal/pilot/intents/'+intent).status_code,409)
 def test_redirect_allowlist(self):
  for href in ['https://www.paypal.com/webapps/billing/subscriptions?x=1','https://www.sandbox.paypal.com.evil.test/webapps/billing/subscriptions?x=1']:
   with self.assertRaises(HTTPException):p.approval_url({'links':[{'rel':'approve','href':href}]})
