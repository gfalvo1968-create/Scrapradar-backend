import copy
import unittest
from datetime import datetime, timezone, timedelta
from paypal_live_evidence import verified_live_subscription
from entitlement_policy import allowed

NOW = datetime(2026,11,9,21,0,tzinfo=timezone.utc)
ALICE = "11111111-1111-4111-8111-111111111111"

def fixture():
    binding = dict(customer_id=ALICE,plan_id="family",subscription_id="I-ABCDE123",
                   provider_plan_id="P-ABCDE123",custom_id="server-generated-opaque-intent")
    sub = dict(id=binding["subscription_id"],plan_id=binding["provider_plan_id"],
               custom_id=binding["custom_id"],status="ACTIVE",plan_overridden=False,
               quantity="1",billing_info=dict(last_payment=dict(
                   amount=dict(currency_code="USD",value="44.95"),
                   time="2026-11-09T20:00:00Z"),outstanding_balance=dict(value="0"),
                   failed_payments_count=0))
    plan = dict(id=binding["provider_plan_id"],status="ACTIVE",quantity_supported=False,
                billing_cycles=[dict(tenure_type="REGULAR",total_cycles=0,
                   frequency=dict(interval_unit="MONTH",interval_count=1),
                   pricing_scheme=dict(fixed_price=dict(currency_code="USD",value="44.95")))],
                payment_preferences=dict(setup_fee=dict(currency_code="USD",value="0")))
    return binding,sub,plan

class LiveEvidenceTests(unittest.TestCase):
    def test_matching_provider_evidence_is_eligible_for_policy(self):
        evidence=verified_live_subscription(*fixture(),NOW)
        self.assertIsNotNone(evidence)
        self.assertTrue(allowed(ALICE,"board_sense",evidence,NOW))

    def test_reject_identity_price_status_and_payment_tampering(self):
        for idx,path,value in [
            (0,("customer_id",),"not-a-uuid"),
            (0,("plan_id",),"cheap"),
            (0,("custom_id",),"x"),
            (1,("custom_id",),"forged"),
            (1,("plan_id",),"P-OTHER123"),
            (1,("status",),"SUSPENDED"),
            (1,("status",),"CANCELLED"),
            (1,("plan_overridden",),True),
            (1,("quantity",),"2"),
            (1,("billing_info","last_payment","amount","value"),"0.01"),
            (1,("billing_info","last_payment","time"),"2026-09-01T00:00:00Z"),
            (1,("billing_info","failed_payments_count"),1),
            (1,("billing_info","outstanding_balance","value"),"10.00"),
            (2,("billing_cycles",0,"pricing_scheme","fixed_price","value"),"0.01"),
            (2,("status",),"INACTIVE"),
            (2,("payment_preferences","setup_fee","value"),"5"),
        ]:
            parts=list(copy.deepcopy(fixture()))
            item=parts[idx]
            for key in path[:-1]: item=item[key]
            item[path[-1]]=value
            self.assertIsNone(verified_live_subscription(*parts,NOW),repr((idx,path,value)))

    def test_missing_payment_and_bad_binding_fail_closed(self):
        b,s,p=fixture()
        del s["billing_info"]
        self.assertIsNone(verified_live_subscription(b,s,p,NOW))
        self.assertIsNone(verified_live_subscription({},s,p,NOW))
        self.assertIsNone(verified_live_subscription(b,s,None,NOW))

if __name__ == "__main__":
    unittest.main()
