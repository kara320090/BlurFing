"""Synthetic HTTP acceptance checks for the explicit Mock deployment only."""
import argparse
import sys
from urllib.parse import urlsplit

import httpx

from check_mock_http import check_image, require


def check(base_url):
    parsed = urlsplit(base_url)
    require(parsed.scheme in {"http", "https"} and bool(parsed.hostname), "HTTP(S) base URL required")
    require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
            "Base URL must not contain credentials, query or fragment")
    require(parsed.path in {"", "/"}, "Base URL must not include a path")
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30, trust_env=False,
                      follow_redirects=False) as client:
        response = client.get("/")
        require(response.status_code == 200 and response.json() == {"message": "BlurFing backend is running"}, "Liveness failed")
        require(response.headers.get("cache-control") == "no-store", "Proxy no-store header missing")
        response = client.get("/ready")
        require(response.status_code == 200 and response.json() == {"status": "ready"}, "Mock readiness failed")
        response = client.get("/info")
        require(response.status_code == 200 and response.json() == {
            "service": "BlurFing", "mode": "mock", "mock_no_protection": True,
            "v1_processor_connected": True, "production_approved": False,
        }, "Deployment is not the explicit Mock mode")
        response = client.get("/v1/protect")
        require(response.status_code == 405 and response.json()["code"] == "METHOD_NOT_ALLOWED", "405 contract failed")
        require("POST" in response.headers.get("allow", ""), "Allow header lost")
        response = client.get("/not-an-api")
        require(response.status_code == 404 and response.json()["code"] == "NOT_FOUND", "404 contract failed")
        response = client.get("/v2/ready")
        require(response.status_code == 503 and response.json()["code"] == "PROCESSOR_UNAVAILABLE", "V2 must stay explicitly unconfigured in Mock deployment")
        # Only two protection POSTs: stay within the default public rate budget.
        for image_format in ("PNG", "JPEG"):
            check_image(client, image_format)
    print("PASS: 8 Mock deployment checks; no real AI or protection performance verified")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)
    try:
        check(args.base_url)
        return 0
    except Exception:
        print("FAIL: deployment check failed; no response body or private exception printed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
