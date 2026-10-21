"""Run the existing Linux photo app on loopback plus ONE Docker bridge address.

No model install, fallback, or process kill. Use the API virtualenv Python.
Keep a manual launch terminal open, or install a configured copy of
systemd/blurfing-photo-v23.service.example (see README-photo-v23.md).
"""
import argparse
from contextlib import ExitStack
import ipaddress
import os
from pathlib import Path
import socket
import sys


def private_ipv4(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in ipaddress.IPv4Network(net) for net in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise ValueError("An explicit RFC1918 Docker bridge address is required")
    return str(address)


def listen_socket(address, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((address, port))
        sock.listen(128)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--gateway", required=True)
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        raise ValueError("This launcher is for the Linux Docker host only")
    gateway = private_ipv4(args.gateway)
    repo = args.repo.resolve(strict=True)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo / "demo"))
    import runtime
    config = runtime.load_config(args.config)
    if Path(sys.prefix) != Path(config["photo"]["api_python"]).parent.parent:
        raise ValueError("Run this launcher using the configured API virtualenv Python")
    report = runtime.preflight(config, "photo", probe=False)
    if not report["configured"]:
        failed = [row["check"] for row in report["checks"] if not row["passed"]]
        raise ValueError("Photo preflight failed: " + ", ".join(failed))
    os.environ.update(runtime.service_environment(config, "photo"))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(repo / "backend"))
    import experimental_photo_main as photo
    settings = photo.PhotoRuntimeConfig.from_environment()
    expected = Path(config["photo"]["ai_python"]).absolute()
    if (settings is None or settings.python != expected or not settings.resident
            or settings.engines != ("synthetic_v23",)):
        raise ValueError("Patched V23 resident backend and intact virtualenv path required")
    import uvicorn
    # Both listeners share ONE app and ONE resident AI worker/admission limit.
    # Binding fails if the supplied address is not assigned to this host.
    with ExitStack() as stack:
        sockets = [stack.enter_context(listen_socket(host, 8001))
                   for host in ("127.0.0.1", gateway)]
        server = uvicorn.Server(uvicorn.Config(
            photo.app, workers=1, access_log=False, proxy_headers=False,
            lifespan="on", timeout_graceful_shutdown=30))
        print(f"Photo listeners: 127.0.0.1:8001 and {gateway}:8001", flush=True)
        print("Server process running; keep a manual terminal open or manage it with systemd.", flush=True)
        server.run(sockets=sockets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
