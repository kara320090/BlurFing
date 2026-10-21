"""Add two scanner routes to the existing Nginx; preserve Android and tunnel.

Inspection only by default. --apply saves an exclusive backup, tests/reloads,
verifies all three contracts, and rolls back on failure. No container restart.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from connect_photo_nginx import change_with_rollback, fetch_json, require_v23
from serve_photo_gateway import private_ipv4


def scanner_block(gateway):
    return f"""        # BEGIN BlurFing scanner v1 ({gateway})
        location = /scanner/ready {{ proxy_pass http://{gateway}:8002/ready; }}
        location = /scanner/v1/scanner/compare {{
            client_max_body_size 4160k;
            limit_req zone=per_client burst=2 nodelay;
            limit_req zone=global_requests burst=4 nodelay;
            limit_req_status 429;
            limit_conn client_connections 2;
            limit_conn global_connections 8;
            limit_conn_status 429;
            error_page 400 411 414 431 494 = @invalid_request;
            error_page 404 = @not_found;
            error_page 408 = @request_timeout;
            error_page 413 = @too_large;
            error_page 429 = @v2_busy;
            error_page 500 = @internal_error;
            error_page 502 = @unavailable;
            error_page 503 = @busy;
            error_page 504 = @v2_timeout;
            proxy_read_timeout 630s;
            proxy_send_timeout 30s;
            proxy_pass http://{gateway}:8002/v1/scanner/compare;
        }}
        # END BlurFing scanner v1
""".encode()


def add_routes(content, gateway):
    gateway = private_ipv4(gateway)
    block = scanner_block(gateway)
    if block in content and content.count(b"# BEGIN BlurFing scanner v1") == 1:
        return content
    if b"/scanner/" in content or b"BlurFing scanner v1" in content:
        raise ValueError("Scanner routing already exists or differs; inspect instead of replacing it")
    # Refuse unfamiliar proxy layouts; keep every existing byte and upstream.
    for required in (b"location = /v1/protect", b"location = /v2/photo/protect",
                     b"proxy_request_buffering off;", b"proxy_buffering off;",
                     b"proxy_ignore_client_abort off;", b"access_log off;",
                     b"zone=per_client", b"zone=global_requests"):
        if required not in content:
            raise ValueError("Expected existing protected BlurFing Nginx layout")
    marker = b"        location / { return 404; }"
    if content.count(marker) != 1:
        raise ValueError("Expected one existing catch-all location")
    return content.replace(marker, block + marker)


def require_scanner(body):
    value = json.loads(body)
    if (not isinstance(value, dict) or value.get("schema_version") != "scanner-comparison-v1"
            or value.get("configured") is not True or value.get("matcher") != "SourceAFIS"
            or value.get("processing") != "experimental_scanner"):
        raise ValueError("Expected configured scanner contract, not photo/Mock readiness")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--sudo", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    gateway = private_ipv4(args.gateway)
    prefix = ["sudo", "docker"] if args.sudo else ["docker"]

    def docker(*items):
        return subprocess.run(prefix + list(items), check=True, text=True,
                              stdout=subprocess.PIPE, timeout=45).stdout

    def inspect(service):
        value = json.loads(docker("inspect", "blurfing-" + service + "-1"))[0]
        labels = value["Config"].get("Labels", {})
        if (labels.get("com.docker.compose.project") != "blurfing"
                or labels.get("com.docker.compose.service") != service or not value["State"]["Running"]):
            raise ValueError("Expected running BlurFing Compose service")
        return value

    nginx, tunnel = inspect("nginx"), inspect("tunnel")
    if nginx["NetworkSettings"]["Networks"].get("blurfing_tunnel", {}).get("Gateway") != gateway:
        raise ValueError("Use the actual Nginx tunnel-network Docker gateway")
    mounts = [m for m in nginx["Mounts"] if m["Destination"] == "/etc/nginx/nginx.conf"]
    if len(mounts) != 1 or mounts[0]["Type"] != "bind":
        raise ValueError("Expected one existing config bind mount")
    source = Path(mounts[0]["Source"])
    if source.is_symlink() or not source.is_file():
        raise ValueError("Expected regular mounted config")
    original = source.read_bytes()
    desired = add_routes(original, gateway)
    print("Same-origin routes: /scanner/ready and /scanner/v1/scanner/compare")
    if not args.apply:
        print("Inspection only. Start scanner gateway before --apply.")
        return 0
    nginx_id = nginx["Id"]
    require_scanner(fetch_json("http://127.0.0.1:8002/ready"))
    require_scanner(docker("exec", nginx_id, "wget", "-q", "-O", "-", "-T", "10", f"http://{gateway}:8002/ready"))
    before_v1 = json.loads(fetch_json("http://127.0.0.1:8080/info"))
    before_v2 = json.loads(fetch_json("http://127.0.0.1:8080/v2/ready"))
    require_v23(json.dumps(before_v2))

    def check():
        docker("exec", nginx_id, "nginx", "-t")

    def reload():
        docker("exec", nginx_id, "nginx", "-s", "reload")

    def verify():
        for attempt in range(10):
            try:
                require_scanner(fetch_json("http://127.0.0.1:8080/scanner/ready"))
                break
            except (OSError, ValueError):
                if attempt == 9:
                    raise
                time.sleep(1)
        for path, expected in (("info", before_v1), ("v2/ready", before_v2)):
            if json.loads(fetch_json("http://127.0.0.1:8080/" + path)) != expected:
                raise ValueError("Android contract changed unexpectedly")
        current = inspect("tunnel")
        if (current["Id"], current["State"]["StartedAt"]) != (tunnel["Id"], tunnel["State"]["StartedAt"]):
            raise ValueError("Tunnel changed; verify the current public URL")

    check()
    change_with_rollback(source, original, desired, args.backup, check, reload, verify)
    print("PASS scanner readiness; existing Android contracts and tunnel unchanged.")
    print("Real sensor image processing/matching still requires verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
