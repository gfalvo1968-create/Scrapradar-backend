"""Concurrent public requests must share one market refresh."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from unittest.mock import patch

import main


class CacheTests(unittest.TestCase):
    def test_parallel_consumers_share_refresh_and_recover_after_failure(self):
        refreshing, release = Event(), Event()

        def build():
            refreshing.set()
            self.assertTrue(release.wait(2))
            return {"status": "live", "metals": {}}

        with patch.object(main, "_price_cache", {"timestamp": 0, "payload": None}), \
                patch.object(main, "_build_prices_payload", side_effect=build) as feed:
            with ThreadPoolExecutor(max_workers=8) as pool:
                jobs = [pool.submit(main.prices) for _ in range(8)]
                self.assertTrue(refreshing.wait(2))
                release.set()
                results = [job.result(timeout=3) for job in jobs]
            self.assertEqual(feed.call_count, 1)
            self.assertEqual(sum(r["cache"] == "miss" for r in results), 1)
            self.assertTrue(all(r["status"] == "live" for r in results))

        with patch.object(main, "_price_cache", {"timestamp": 0, "payload": None}), \
                patch.object(main, "_build_prices_payload", side_effect=[OSError("feed failed"), {"status": "unavailable"}]):
            with self.assertRaises(OSError):
                main.prices()
            self.assertEqual(main.prices()["status"], "unavailable")

    def test_health_check_does_not_refresh_market(self):
        with patch.object(main, "_build_prices_payload", side_effect=AssertionError("upstream call")):
            self.assertEqual(main.health()["release"], "launch-20261006")
