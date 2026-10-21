"""Synthetic routing checks; no Docker/school deployment or biometric claim."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from connect_nginx import add_routes, require_scanner, scanner_block


class ScannerGatewayTests(unittest.TestCase):
    def setUp(self):
        self.original = (Path(__file__).resolve().parents[2] / "backend/nginx/nginx.conf").read_bytes()

    def test_adds_only_scanner_routes_preserving_android_and_upstreams(self):
        original = self.original.replace(b"api-v2:8001 resolve", b"172.21.0.1:8001")
        desired = add_routes(original, "172.21.0.1")
        self.assertEqual(desired.replace(scanner_block("172.21.0.1"), b""), original)
        self.assertIn(b"location = /scanner/ready", desired)
        self.assertIn(b"proxy_pass http://172.21.0.1:8002/v1/scanner/compare;", desired)
        self.assertNotIn(b"location /scanner/", desired)  # no arbitrary extra API exposure
        self.assertIn(b"client_max_body_size 4160k;", desired)
        self.assertIn(b"limit_req_status 429;", desired)

    def test_repeat_is_idempotent_and_other_gateway_is_rejected(self):
        desired = add_routes(self.original, "172.21.0.1")
        self.assertEqual(add_routes(desired, "172.21.0.1"), desired)
        with self.assertRaises(ValueError):
            add_routes(desired, "172.22.0.1")

    def test_rejects_unfamiliar_or_duplicate_configs(self):
        for content in (b"", self.original + self.original,
                        self.original.replace(b"proxy_request_buffering off;", b""),
                        self.original + b"# /scanner/ already managed"):
            with self.subTest(content=content[:30]), self.assertRaises(ValueError):
                add_routes(content, "172.21.0.1")

    def test_refuses_public_wildcard_loopback_or_injected_address(self):
        for gateway in ("8.8.8.8", "0.0.0.0", "127.0.0.1", "172.21.0.1; bad"):
            with self.subTest(gateway=gateway), self.assertRaises(ValueError):
                add_routes(self.original, gateway)

    def test_readiness_cannot_be_photo_or_mock_or_falsy_config(self):
        ready = dict(schema_version="scanner-comparison-v1", configured=True,
                     matcher="SourceAFIS", processing="experimental_scanner", inference_checked=False)
        require_scanner(json.dumps(ready))
        for changes in (dict(schema_version="photo-experimental-v2"), dict(configured=1),
                        dict(configured=False), dict(matcher="Mock"), dict(processing="photo")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                require_scanner(json.dumps(ready | changes))


if __name__ == "__main__":
    unittest.main()
