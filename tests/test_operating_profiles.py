"""Isolated profile and arithmetic fixtures; these are not measured scrap yields."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from operating_profiles import build_profile_router, LB_GRAMS, TROY_GRAMS


class OperatingProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SCRAPRADAR_DB_PATH": str(Path(self.temp.name) / "rates.db")})
        self.env.start()
        self.market = {"metals": {
            "gold": {"price": 4172, "unit": "troy_oz", "available": True, "source_price_date": "2026-10-02"},
            "copper": {"price": 6.55, "unit": "lb", "available": True, "source_price_date": "2026-10-02"},
        }}
        self.app = FastAPI()
        self.app.include_router(build_profile_router(lambda: self.market))
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer srp_" + "a" * 64}
        self.other = {"Authorization": "Bearer srp_" + "b" * 64}
        self.rates = {"fuel_cost_per_mile": .45, "target_hourly_wage": 25, "chemical_cost_per_lb": .5}
        self.payload = {
            "scrap_data": {"category": "automotive", "subcategory": "harness_plugs", "grade_type": "high_grade", "gross_weight_lbs": 50},
            "yield_basis": "assumed",
            "recovered_metals": [
                {"metal": "gold", "recovered_grams": .12 * TROY_GRAMS, "buyer_pay_percent": 100},
                {"metal": "copper", "recovered_grams": 14.7 * LB_GRAMS, "buyer_pay_percent": 100},
            ],
            "distance_miles": 30, "labor_hours_invested": 2.5,
            "processing_weight_lbs": 15, "other_costs": 0,
        }

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()

    def save(self, rates=None):
        return self.client.post("/api/update-profile", headers=self.headers, json=rates or self.rates)

    def calculate(self):
        return self.client.post("/api/calculate-yield", headers=self.headers, json=self.payload)

    def test_no_hidden_defaults_and_private_profile(self):
        self.assertEqual(self.client.get("/api/profile", headers=self.headers).json()["profile"], None)
        self.assertEqual(self.client.get("/api/profile").status_code, 401)
        self.assertEqual(self.client.post("/api/update-profile", json=self.rates).status_code, 401)
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.client.get("/api/profile", headers=self.other).json()["profile"], None)
        self.assertFalse(self.client.get("/api/profile", headers={"Authorization": "Bearer user-id"}).status_code == 200)

    def test_upsert_persists_across_app_restart_and_clear(self):
        self.save()
        self.save({**self.rates, "target_hourly_wage": 30})
        client = TestClient(self.app)
        self.assertEqual(client.get("/api/profile", headers=self.headers).json()["profile"]["target_hourly_wage"], 30)
        self.save(dict.fromkeys(self.rates))
        self.assertFalse(client.get("/api/profile", headers=self.headers).json()["saved"])
        client.close()

    def test_negative_nonfinite_and_foreign_user_id_rejected(self):
        for bad in [-1, "nan", "Infinity", 1001]:
            self.assertEqual(self.save({**self.rates, "fuel_cost_per_mile": bad}).status_code, 422)
        self.assertEqual(self.save({**self.rates, "user_id": "someone-else"}).status_code, 422)
        self.assertEqual(self.client.post("/api/update-profile?user_id=someone", headers=self.headers, json=self.rates).status_code, 200)
        self.assertFalse(self.client.get("/api/profile", headers=self.other).json()["saved"])

    def test_sourced_prices_round_trip_labor_and_shared_costs_once(self):
        self.save()
        result = self.calculate().json()
        self.assertEqual(result["status"], "complete_scenario")
        self.assertEqual(result["financial_summary"], {
            "gross_commodity_value": 596.93,
            "total_overhead_deductions": 97,
            "estimated_net_after_entered_costs": 499.93,
        })
        self.assertEqual(result["cost_breakdown"], {"travel": 27, "labor": 62.5, "processing": 7.5, "other": 0})
        self.assertNotIn("predictive_intelligence", result)
        self.assertNotIn("true_net_profit", result["financial_summary"])

    def test_grade_never_creates_gold_or_palladium_yield(self):
        self.save()
        self.payload["recovered_metals"] = []
        for grade in ("high_grade", "airbag_sensor"):
            self.payload["scrap_data"]["grade_type"] = grade
            result = self.calculate().json()
            self.assertEqual(result["status"], "needs_yields")
            self.assertEqual(result["financial_summary"]["gross_commodity_value"], None)

    def test_missing_inputs_and_buyer_terms_withhold_net(self):
        self.save()
        self.payload["recovered_metals"][0]["buyer_pay_percent"] = None
        self.assertIsNone(self.calculate().json()["financial_summary"]["estimated_net_after_entered_costs"])
        self.payload["recovered_metals"][0]["buyer_pay_percent"] = 90
        self.payload["labor_hours_invested"] = None
        self.assertIsNone(self.calculate().json()["financial_summary"]["total_overhead_deductions"])

    def test_zero_explicitly_excludes_cost_without_a_rate(self):
        self.payload.update(distance_miles=0, labor_hours_invested=0, processing_weight_lbs=0)
        result = self.calculate().json()
        self.assertEqual(result["financial_summary"]["total_overhead_deductions"], 0)

    def test_buyer_percent_deducted_before_costs(self):
        self.save()
        self.payload["recovered_metals"][0]["buyer_pay_percent"] = 90
        self.payload["recovered_metals"][1]["buyer_pay_percent"] = 80
        self.assertEqual(self.calculate().json()["financial_summary"]["estimated_net_after_entered_costs"], 430.60)

    def test_duplicates_mass_and_negative_values_rejected(self):
        self.payload["recovered_metals"].append(dict(self.payload["recovered_metals"][0]))
        self.assertEqual(self.calculate().status_code, 422)
        self.payload["recovered_metals"] = [{"metal": "gold", "recovered_grams": 51 * LB_GRAMS}]
        self.assertEqual(self.calculate().status_code, 422)
        self.payload["recovered_metals"] = []
        self.payload["processing_weight_lbs"] = 51
        self.assertEqual(self.calculate().status_code, 422)
        self.payload["processing_weight_lbs"] = -1
        self.assertEqual(self.calculate().status_code, 422)

    def test_stale_unavailable_and_ordinary_ounce_prices(self):
        self.save()
        self.market["metals"]["gold"]["stale"] = True
        self.assertIsNone(self.calculate().json()["financial_summary"]["estimated_net_after_entered_costs"])
        self.market["metals"]["gold"]["stale"] = False
        self.market["metals"]["gold"]["unit"] = "oz"
        self.assertIsNone(self.calculate().json()["financial_summary"]["gross_commodity_value"])
        self.market["metals"]["gold"]["unit"] = "troy_oz"
        self.market["metals"]["gold"]["available"] = False
        self.assertIsNone(self.calculate().json()["financial_summary"]["gross_commodity_value"])

    def test_storage_failure_returns_service_error(self):
        with patch.dict(os.environ, {"SCRAPRADAR_DB_PATH": self.temp.name}):
            self.assertEqual(self.save().status_code, 503)
            self.assertEqual(self.client.get("/api/profile", headers=self.headers).status_code, 503)


if __name__ == "__main__":
    unittest.main()
