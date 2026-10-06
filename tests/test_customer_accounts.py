import io,json,os,tempfile,unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from customer_accounts import router
from membership_records import register_subscription

ALICE='11111111-1111-4111-8111-111111111111'
BOB='22222222-2222-4222-8222-222222222222'
class CustomerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'SCRAPRADAR_DB_PATH':self.tmp.name+'/db'});self.env.start()
  app=FastAPI();app.include_router(router);self.client=TestClient(app)
  self.headers={'Authorization':'Bearer '+'x'*40}
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def user(self,identity=ALICE,**changes):return {'id':identity,'email':'test@example.invalid','email_confirmed_at':'2026-10-06','role':'authenticated','is_anonymous':False,**changes}
 def get(self,user,path='/api/account'):
  with patch('customer_accounts.urlopen',return_value=io.BytesIO(json.dumps(user).encode())):
   return self.client.get(path,headers=self.headers)
 def test_missing_identity_and_profile_capability_rejected(self):
  self.assertEqual(self.client.get('/api/account').status_code,401)
  with patch('customer_accounts.urlopen',side_effect=HTTPError('fixed',401,'invalid',{},None)):
   self.assertEqual(self.client.get('/api/account',headers=self.headers).status_code,401)
 def test_verified_accounts_are_isolated_and_posted_id_ignored(self):
  register_subscription(ALICE,'sub1','family')
  a=self.get(self.user());b=self.get(self.user(BOB),'/api/account?customer_id='+ALICE)
  self.assertEqual(len(a.json()['subscriptions']),1);self.assertEqual(b.json()['subscriptions'],[])
  self.assertEqual(b.json()['customer']['id'],BOB)
  self.assertEqual(a.headers['cache-control'],'no-store')
  self.assertFalse(a.json()['paid_access_enabled'])
 def test_unconfirmed_and_anonymous_denied(self):
  for user in [self.user(email_confirmed_at=None),self.user(is_anonymous=True),self.user(role='anon'),self.user(id='bad')]:
   self.assertIn(self.get(user).status_code,(401,403))
 def test_user_metadata_cannot_grant_plan(self):
  d=self.get(self.user(user_metadata={'plan':'family','role':'admin'})).json()
  self.assertEqual(d['subscriptions'],[]);self.assertFalse(d['paid_access_enabled'])
 def test_auth_outage_fails_closed(self):
  with patch('customer_accounts.urlopen',side_effect=URLError('down')):
   self.assertEqual(self.client.get('/api/account',headers=self.headers).status_code,503)
