"""Run scanner API on loopback plus the existing Nginx Docker bridge only."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from serve_photo_gateway import listen_socket, private_ipv4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--gateway", required=True)
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        raise ValueError("Run on the Linux Docker host")
    gateway = private_ipv4(args.gateway)
    sys.path.insert(0, str(ROOT / "demo"))
    import runtime
    config = runtime.load_config(args.config)
    if Path(sys.prefix) != Path(config["scanner"]["api_python"]).parent.parent:
        raise ValueError("Use the configured scanner API virtualenv Python")
    # Validate actual NBIS and SourceAFIS imports/runtime before exposing this
    # listener. This does not prove image inference or a biometric measurement.
    report = runtime.preflight(config, "scanner", probe=True)
    if not report["configured"]:
        raise ValueError("Scanner preflight failed: " + ", ".join(
            row["check"] for row in report["checks"] if not row["passed"]))
    os.environ.update(runtime.service_environment(config, "scanner"))
    import uvicorn
    from scanner_api import app
    with ExitStack() as stack:
        sockets = [stack.enter_context(listen_socket(host, 8002)) for host in ("127.0.0.1", gateway)]
        uvicorn.Server(uvicorn.Config(app, workers=1, access_log=False, proxy_headers=False,
            log_level="warning", timeout_graceful_shutdown=30)).run(sockets=sockets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
