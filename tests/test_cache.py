import time
import unittest
from app.cache import ResponseCache


class TestResponseCache(unittest.TestCase):

    def setUp(self):
        self.cache = ResponseCache(ttl_seconds=1)

    def test_cache_set_and_get(self):
        self.cache.set("Hello World", "Hello! How can I help you?")
        result = self.cache.get("Hello World")
        self.assertEqual(result, "Hello! How can I help you?")

    def test_cache_case_and_whitespace_insensitivity(self):
        self.cache.set("Hello World", "Cached answer")
        self.assertEqual(self.cache.get("  hello world  "), "Cached answer")

    def test_cache_miss(self):
        result = self.cache.get("Non-existent query")
        self.assertIsNone(result)

    def test_cache_expiration(self):
        self.cache.set("Expiring query", "Expiring response")
        time.sleep(1.1)
        self.assertIsNone(self.cache.get("Expiring query"))

    def test_cache_stats(self):
        self.cache.set("Q1", "A1")
        self.cache.get("Q1")  # Hit
        self.cache.get("Q2")  # Miss
        stats = self.cache.stats
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertIn("50.0%", stats["hit_rate"])


if __name__ == "__main__":
    unittest.main()
