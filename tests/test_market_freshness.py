"""Price dates must come from daily market bars, not the time we fetched them."""

import json
import sys
import types
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

# This suite does not download quotes or require network access.
sys.modules.setdefault("yfinance", types.SimpleNamespace())
import main  # noqa: E402


CHECKED = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)


class Series:
    def __init__(self, values):
        self.values = values

    def dropna(self):
        return self

    def items(self):
        return iter(self.values)


class Frame:
    empty = False

    def __init__(self, values):
        self.values = values

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        return Series(self.values)


class FreshnessTests(unittest.TestCase):
    def test_uses_bar_date_and_rejects_nonfinite_history(self):
        rows = [(date(2026, 9, 18), 3.5), (date(2026, 9, 21), float("nan")),
                (date(2026, 9, 22), float("inf")), (date(2026, 9, 23), 0)]
        feed = types.SimpleNamespace(Ticker=lambda _: types.SimpleNamespace(
            history=lambda **__: Frame(rows)))
        with patch.object(main, "yf", feed):
            history, bar_date = main._history_with_price_date("HG=F")
        self.assertEqual((history, bar_date), ([3.5], date(2026, 9, 18)))

    def test_old_quotes_cannot_emit_current_status_or_sell_signals(self):
        with patch.object(main, "_history_with_price_date", return_value=(
                [3, 3.1, 3.2, 3.3, 3.4], date(2026, 9, 18))):
            payload = main._build_prices_payload(CHECKED)
        self.assertEqual(payload["status"], "stale")
        self.assertEqual(payload["checked_at"], CHECKED.isoformat())
        self.assertEqual(payload["metals"]["copper"]["source_price_date"], "2026-09-18")
        self.assertTrue(payload["metals"]["copper"]["stale"])
        self.assertEqual(payload["metals"]["copper"]["intelligence"]["signal"], "STALE MARKET DATA")
        copper_grade = next(category for category in payload["materials"] if category["id"] == "copper")
        self.assertTrue(copper_grade["materials"][0]["stale"])
        json.dumps(payload, allow_nan=False)

    def test_mixed_freshness_and_missing_quotes(self):
        def feed(ticker, _period):
            if ticker == "HG=F":
                return [3.4] * 5, date(2026, 9, 21)
            if ticker == "SI=F":
                return [4.0] * 5, None
            return [], None

        with patch.object(main, "_history_with_price_date", side_effect=feed):
            payload = main._build_prices_payload(CHECKED)
        self.assertEqual(payload["status"], "live")
        self.assertFalse(payload["metals"]["copper"]["stale"])
        self.assertTrue(payload["metals"]["silver"]["stale"])
        self.assertFalse(payload["metals"]["gold"]["available"])
        self.assertEqual(payload["available_metals"], 2)
        json.dumps(payload, allow_nan=False)

    def test_all_missing_quotes_are_unavailable(self):
        with patch.object(main, "_history_with_price_date", return_value=([], None)):
            payload = main._build_prices_payload(CHECKED)
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["available_metals"], 0)


if __name__ == "__main__":
    unittest.main()
