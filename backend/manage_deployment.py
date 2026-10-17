"""Explicit operator commands; never reset/stash/checkout a working tree.

Run with the host Python, not sudo Python. --sudo elevates Docker commands only.
GitHub updates are exported into backend/.deploy/releases, preserving dirty files.
"""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".deploy" / "state.json"


def run(command, *, capture=False, cwd=ROOT, env=None):
    return subprocess.run(command, cwd=cwd, env=env, check=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          text=True)


def active_source():
    if not STATE.is_file():
        return ROOT, "local"
    state = json.loads(STATE.read_text(encoding="utf-8"))
    source = Path(state["source"]).resolve()
    releases = (ROOT / ".deploy" / "releases").resolve()
    if source != ROOT and not source.is_relative_to(releases):
        raise ValueError("Invalid deployment state path")
    if not (source / "compose.yaml").is_file() or not re.fullmatch(r"local|[0-9a-f]{40}", state["release"]):
        raise ValueError("Missing deployment source or invalid release")
    return source, state["release"]


def compose(source, release, sudo):
    prefix = ["sudo", "docker"] if sudo else ["docker"]
    prefix += ["compose", "--project-name", "blurfing", "--project-directory", str(source),
               "--env-file", str(ROOT / (".env" if (ROOT / ".env").is_file() else ".env.example")),
               "--file", str(source / "compose.yaml")]
    if (ROOT / "compose.local.yaml").is_file():
        prefix += ["--file", str(ROOT / "compose.local.yaml")]
    environment = os.environ.copy()
    environment["BLURFING_RELEASE"] = release
    # sudo normally strips environment variables. Compose interpolation occurs
    # in the elevated process, so pass only this non-secret build tag explicitly.
    if sudo:
        prefix = ["sudo", "env", "BLURFING_RELEASE=" + release] + prefix[1:]
    return prefix, environment


def export_release(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A full commit SHA is required")
    # Refuse an old source revision that has not yet received the deployment files.
    run(["git", "show", revision + ":backend/compose.yaml"], capture=True)
    result = subprocess.run(["git", "archive", "--format=tar", revision, "backend"],
                            cwd=ROOT, check=True, capture_output=True)
    if len(result.stdout) > 64 * 1024 * 1024:
        raise ValueError("Backend source archive is unexpectedly large")
    releases = ROOT / ".deploy" / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=revision[:12] + "-", dir=releases)).resolve()
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name or
                    not name.parts or name.parts[0] != "backend" or
                    not (member.isfile() or member.isdir()) or
                    not (destination / member.name).resolve().is_relative_to(destination)):
                raise ValueError("Unsafe backend archive member")
        # All members are bounded to this new directory; links/devices are rejected.
        archive.extractall(destination)
    return destination / "backend"


def record_deployment(source, release):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else None
    state = {"source": str(source), "release": release,
             "previous": {key: previous[key] for key in ("source", "release")} if previous else None}
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sudo", action="store_true", help="use sudo for Docker only")
    parser.add_argument("command", choices=("check", "up", "verify", "public", "url", "status", "update", "rollback"))
    args = parser.parse_args(argv)
    try:
        source, release = active_source()
        if args.command == "up":
            source, release = ROOT, "local"
        if args.command == "update":
            # Fetch is non-destructive to all working-tree files, including data/.
            run(["git", "fetch", "--no-tags", "origin", "main"])
            release = run(["git", "rev-parse", "FETCH_HEAD"], capture=True).stdout.strip()
            source = export_release(release)
        if args.command == "rollback":
            state = json.loads(STATE.read_text(encoding="utf-8"))
            previous = state.get("previous")
            if not previous:
                raise ValueError("No previous deployment recorded")
            source = Path(previous["source"]).resolve()
            release = previous["release"]
            if ((source != ROOT and not source.is_relative_to((ROOT / ".deploy" / "releases").resolve()))
                    or not re.fullmatch(r"local|[0-9a-f]{40}", release)):
                raise ValueError("Invalid previous deployment state")
        command, environment = compose(source, release, args.sudo)

        def dc(*arguments, capture=False):
            return run(command + list(arguments), capture=capture, env=environment)

        dc("config", "--quiet")
        if args.command in {"up", "update", "rollback"}:
            # Build before replacing running services; a build failure leaves them alone.
            dc("build", "api-v1", "api-v2")
            dc("run", "--rm", "--no-deps", "nginx", "-t")
            dc("up", "-d", "--wait", "--wait-timeout", "120", "--force-recreate", "api-v1", "api-v2", "nginx")
            record_deployment(source, release)
            print("Services started. Run verify next; real AI and external HTTPS are not verified yet.")
        elif args.command == "check":
            dc("run", "--rm", "--no-deps", "nginx", "-t")
        elif args.command == "verify":
            dc("exec", "-T", "api-v1", "python", "check_deployment_http.py", "--base-url", "http://nginx:8080")
        elif args.command == "public":
            dc("exec", "-T", "api-v1", "python", "check_deployment_http.py", "--base-url", "http://nginx:8080")
            dc("--profile", "public", "up", "-d", "--no-recreate", "tunnel")
            print("Quick Tunnel started. Run url to read its temporary HTTPS URL; external verification is still required.")
        elif args.command == "url":
            logs = dc("--profile", "public", "logs", "--no-color", "--tail", "100", "tunnel", capture=True).stdout
            urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", logs)
            if not urls:
                print("No Quick Tunnel URL found yet. Check tunnel status and retry shortly.")
                return 1
            print(urls[-1])
        elif args.command == "status":
            dc("--profile", "public", "ps")
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError):
        print("Deployment command failed. No checkout/reset/stash was performed. Review the visible Docker/Git error; do not share secrets.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
