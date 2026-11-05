import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import is_allowed_media_url, normalize_media_url
from recognition import make_signature


class MediaUrlTests(unittest.TestCase):
    def test_allows_supported_https_host(self):
        self.assertTrue(is_allowed_media_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_allowed_media_url("https://www.instagram.com/reel/abc/"))
        self.assertTrue(is_allowed_media_url("https://www.snapchat.com/spotlight/abc"))
        self.assertTrue(is_allowed_media_url("https://t.me/channel_name/123"))
        self.assertTrue(is_allowed_media_url("https://likee.video/v/abc"))
        self.assertTrue(is_allowed_media_url("https://www.reddit.com/r/videos/comments/abc"))
        self.assertTrue(is_allowed_media_url("https://x.com/user/status/123"))
        self.assertTrue(is_allowed_media_url("https://www.capcut.com/s/abc"))

    def test_rejects_non_https_and_lookalike_hosts(self):
        self.assertFalse(is_allowed_media_url("http://youtube.com/watch?v=abc"))
        self.assertFalse(is_allowed_media_url("https://youtube.com.attacker.example/watch"))
        self.assertFalse(is_allowed_media_url("https://127.0.0.1/video"))
        self.assertFalse(is_allowed_media_url("https://youtube.com:8443/watch"))

    def test_normalizes_public_telegram_share_links(self):
        self.assertEqual(
            normalize_media_url("https://t.me/s/channel_name/123?single"),
            "https://t.me/channel_name/123?single",
        )
        self.assertEqual(
            normalize_media_url("https://telegram.me/channel_name/123"),
            "https://t.me/channel_name/123",
        )


class ACRCloudSignatureTests(unittest.TestCase):
    def test_signature_matches_protocol_v1_example(self):
        self.assertEqual(
            make_signature("test-key", "test-secret", "1700000000"),
            "iBfU+Pr4tncyMr9T7iihwUaPJGA=",
        )


if __name__ == "__main__":
    unittest.main()
