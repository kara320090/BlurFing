"""Switch only the existing V2 Nginx upstream, preserving V1 and the tunnel.

Host Python, not sudo Python; --sudo elevates Docker commands only. Inspect the
actual bind mount, save an exclusive backup, test/reload, roll back on failure.
No Docker service recreation, model copying, uploads, or firewall changes.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from serve_photo_gateway import private_ipv4

UPSTREAM = re.compile(r"upstream\s+v2\s*\{\s*zone\s+v2\s+64k\s*;\s*server\s+"
                      r"(?P<address>api-v2|[0-9.]+):8001(?P<resolve>\s+resolve)?\s*;\s*\}")


def replace_upstream(content, gateway):
    gateway = private_ipv4(gateway)
    text = content.decode("utf-8")
    matches = list(UPSTREAM.finditer(text))
    if len(matches) != 1:
        raise ValueError("Expected exactly one simple V2 upstream; refusing an unknown config")
    match = matches[0]
    if match["address"] == gateway and not match["resolve"]:
        return content
    if match["address"] != "api-v2" or not match["resolve"]:
        raise ValueError("V2 already points elsewhere; inspect before changing it")
    replacement = match[0].replace("api-v2:8001" + match["resolve"], gateway + ":8001")
    return (text[:match.start()] + replacement + text[match.end():]).encode("utf-8")


def require_v23(body):
    value = json.loads(body)
    if (not isinstance(value, dict) or value.get("status") != "ready"
            or value.get("contract_version") != "photo-experimental-v2"
            or value.get("result_kind") != "experimental"
            or value.get("photo_engines") != ["synthetic_v23"]
            or value.get("production_approved") is not False):
        raise ValueError("Expected ready experimental V23; Mock/other contracts are rejected")


def fetch_json(url):
    # No environment proxy or redirects for these local origin checks.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(url, timeout=5) as response:
        body = response.read(16385)
        if response.status != 200 or len(body) > 16384:
            raise ValueError("Unexpected/oversized origin response")
        return body


def write_mounted(path, content):
    # A single-file bind mount holds its inode: do NOT use atomic rename here.
    with path.open("r+b") as stream:
        stream.write(content)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())


def change_with_rollback(path, original, desired, backup, check, reload, verify):
    if path.is_symlink() or path.read_bytes() != original:
        raise ValueError("Mounted config changed while checking; no changes applied")
    if original == desired:
        verify()
        return
    backup.parent.mkdir(parents=True, exist_ok=True)
    # Existing backup is never overwritten. Backup can contain origin settings.
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        write_mounted(path, desired)
        check()
        reload()
        verify()
    except BaseException:
        write_mounted(path, original)
        check()
        reload()
        print("Original Nginx config restored and reload requested.", file=sys.stderr)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sudo", action="store_true")
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Without this, inspect only")
    args = parser.parse_args(argv)
    gateway = private_ipv4(args.gateway)
    prefix = ["sudo", "docker"] if args.sudo else ["docker"]

    def docker(*items):
        return subprocess.run(prefix + list(items), check=True, text=True,
                              stdout=subprocess.PIPE, timeout=45).stdout

    def inspect(name, service):
        value = json.loads(docker("inspect", name))[0]
        labels = value["Config"].get("Labels", {})
        if (labels.get("com.docker.compose.project") != "blurfing"
                or labels.get("com.docker.compose.service") != service
                or not value["State"]["Running"]):
            raise ValueError("Expected running blurfing Compose service")
        return value

    nginx = inspect("blurfing-nginx-1", "nginx")
    tunnel = inspect("blurfing-tunnel-1", "tunnel")
    network = nginx["NetworkSettings"]["Networks"].get("blurfing_tunnel", {})
    if network.get("Gateway") != gateway:
        raise ValueError("Address must match the running Nginx Docker tunnel gateway")
    mounts = [m for m in nginx["Mounts"] if m["Destination"] == "/etc/nginx/nginx.conf"]
    if len(mounts) != 1 or mounts[0]["Type"] != "bind":
        raise ValueError("Expected one existing Nginx config bind mount")
    source = Path(mounts[0]["Source"])
    if source.is_symlink() or not source.is_file():
        raise ValueError("Config must be a regular host file, not a symlink")
    original = source.read_bytes()
    desired = replace_upstream(original, gateway)
    print("Mounted Nginx config:", source)
    print("V2 target:", gateway + ":8001; V1 and tunnel configuration unchanged")
    if not args.apply:
        print("Inspection only. Restart AI with the bridge listener before --apply.")
        return 0

    nginx_id = nginx["Id"]
    def check():
        docker("exec", nginx_id, "nginx", "-t")
    def reload():
        docker("exec", nginx_id, "nginx", "-s", "reload")

    # Do not change routing unless both host and container can reach actual V23.
    require_v23(fetch_json("http://127.0.0.1:8001/ready"))
    require_v23(docker("exec", nginx_id, "wget", "-q", "-O", "-", "-T", "10",
                       f"http://{gateway}:8001/ready"))
    v1_before = json.loads(fetch_json("http://127.0.0.1:8080/info"))
    check()

    def verify():
        # Reload is asynchronous. Each request uses a fresh connection.
        last = None
        for _ in range(10):
            try:
                require_v23(fetch_json("http://127.0.0.1:8080/v2/ready"))
                break
            except (OSError, ValueError) as error:
                last = error
                time.sleep(1)
        else:
            raise RuntimeError("Nginx V23 readiness did not become healthy") from last
        if json.loads(fetch_json("http://127.0.0.1:8080/info")) != v1_before:
            raise ValueError("V1 info changed unexpectedly")
        current = inspect("blurfing-tunnel-1", "tunnel")
        if (current["Id"], current["State"]["StartedAt"]) != (tunnel["Id"], tunnel["State"]["StartedAt"]):
            raise ValueError("Tunnel changed during this operation; verify its current URL")

    change_with_rollback(source, original, desired, args.backup, check, reload, verify)
    print("PASS Nginx -> real V23 readiness; V1 unchanged; tunnel not restarted.")
    print("External HTTPS, photo inference, latency and unattended startup still require verification.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Connection not confirmed ({type(error).__name__}): {error}", file=sys.stderr)
        raise SystemExit(1)
