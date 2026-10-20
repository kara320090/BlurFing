"""Windows launcher integration tests; public dummy files, no photo inference."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
SCRIPT = Path(__file__).with_name("Start-Photo-V23.ps1")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def command(tmp_path, port, reuse=False):
    model = tmp_path / "public unused model"
    model.mkdir(exist_ok=True)
    (model / "final_config.private.json").write_text("{}", encoding="utf-8")
    (model / "final_context_whole_pad.pt").write_bytes(b"unused public test checkpoint")
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    args = [shutil.which("powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(SCRIPT), "-ServerPython", sys.executable, "-AiPython", sys.executable,
            "-ModelPath", str(model), "-RegistryPath", str(registry), "-Port", str(port)]
    return args + (["-ReuseRunning"] if reuse else [])


def stop_owned_tree(process):
    if process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    process.wait(timeout=10)


def test_start_reuse_and_conflict_preserve_the_existing_server(tmp_path):
    port = free_port()
    args = command(tmp_path, port)
    with (tmp_path / "server.log").open("wb") as log:
        process = subprocess.Popen(args, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 25
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1) as response:
                        ready = json.load(response)
                    assert ready["photo_engines"] == ["synthetic_v23"]
                    break
                except OSError:
                    assert process.poll() is None, (tmp_path / "server.log").read_text(errors="replace")
                    assert time.monotonic() < deadline, "Server did not become ready"
                    time.sleep(.1)
            for reuse in (True, False):
                result = subprocess.run(command(tmp_path, port, reuse), capture_output=True,
                                        timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                assert (result.returncode == 0) == reuse, (result.stdout, result.stderr)
                assert process.poll() is None
                if reuse:
                    assert b"already running" in result.stdout
                    assert b"EXISTING configuration" in result.stdout
                else:
                    assert b"already in use" in result.stderr
        finally:
            stop_owned_tree(process)


def test_unrelated_listener_is_not_reused_or_stopped(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(command(tmp_path, port, True), capture_output=True,
                                timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode != 0
        assert b"another application" in result.stderr
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass


def test_native_launch_failure_preserves_nonzero_exit(tmp_path):
    args = command(tmp_path, free_port())
    fake_python = tmp_path / "failed-python.cmd"
    fake_python.write_bytes(b"@echo off\r\nexit /b 7\r\n")
    args[args.index("-ServerPython") + 1] = str(fake_python)
    result = subprocess.run(args, capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 7, (result.stdout, result.stderr)
