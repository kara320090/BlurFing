"""Deployment entrypoint and operator-helper tests; no Docker/real AI is run."""
import json
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

import manage_deployment as deployment


def entrypoint(extra, script):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("BLURFING_")}
    environment.update(extra, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).parent,
                          env=environment, capture_output=True, text=True, encoding="utf-8", timeout=15)


def test_default_deployment_is_explicit_mock_and_preserves_health_contract():
    result = entrypoint({}, """
import json
from fastapi.testclient import TestClient
from deployment_main import app
with TestClient(app) as client:
    print(json.dumps([client.get('/').json(),client.get('/ready').json(),client.get('/info').json()]))
""")
    assert result.returncode == 0, result.stderr
    health, ready, info = json.loads(result.stdout)
    assert health == {"message": "BlurFing backend is running"}
    assert ready == {"status": "ready"}
    assert info["mode"] == "mock" and info["mock_no_protection"] is True
    assert info["production_approved"] is False


@pytest.mark.parametrize("environment", [
    {"BLURFING_DEPLOY_MODE": "typo"},
    {"BLURFING_DEPLOY_MODE": "mock", "BLURFING_PROCESSOR": "missing:processor"},
    {"BLURFING_DEPLOY_MODE": "real", "BLURFING_PROCESSOR": "mock_processor:mock_processor"},
    {"BLURFING_MOCK_DELAY_SECONDS": "NaN"},
])
def test_bad_mode_or_ambiguous_mock_real_settings_fail_at_startup(environment):
    result = entrypoint(environment, "import deployment_main")
    assert result.returncode != 0


def test_real_mode_without_model_does_not_fallback_to_mock():
    result = entrypoint({"BLURFING_DEPLOY_MODE": "real"}, """
import json
from fastapi.testclient import TestClient
from deployment_main import app
with TestClient(app) as client:
    print(json.dumps([client.get('/ready').status_code,client.get('/info').json()]))
""")
    assert result.returncode == 0, result.stderr
    status, info = json.loads(result.stdout)
    assert status == 503
    assert info["mock_no_protection"] is False
    assert info["v1_processor_connected"] is False


def test_v2_liveness_does_not_pretend_model_is_ready():
    result = entrypoint({}, """
import json
from fastapi.testclient import TestClient
from deployment_photo_main import app
with TestClient(app) as client:
    print(json.dumps([client.get('/health').json(),client.get('/ready').status_code]))
""")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [{"status": "alive"}, 503]


def test_sudo_only_wraps_docker_and_preserves_nonsecret_release_tag(monkeypatch, tmp_path):
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    command, environment = deployment.compose(tmp_path, "a" * 40, True)
    assert command[:5] == ["sudo", "env", "BLURFING_RELEASE=" + "a" * 40, "docker", "compose"]
    assert environment["BLURFING_RELEASE"] == "a" * 40
    assert "--project-name" in command
    assert "blurfing" in command


def test_state_rejects_source_outside_managed_release_directory(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"source": str(tmp_path.parent), "release": "local"}), encoding="utf-8")
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "STATE", state)
    with pytest.raises(ValueError, match="Invalid deployment state path"):
        deployment.active_source()


def release_archive(name, *, symlink=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = "../../outside"
            archive.addfile(member)
        else:
            content = b"deployment source\n"
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return stream.getvalue()


@pytest.mark.parametrize("name,symlink", [
    ("backend/../../outside", False),
    ("data/untouched.py", False),
    ("/backend/absolute", False),
    ("backend/..\\outside", False),
    ("backend/link", True),
])
def test_release_export_rejects_non_backend_paths_and_links(monkeypatch, tmp_path, name, symlink):
    payload = release_archive(name, symlink=symlink)
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "run", lambda *a, **k: None)
    monkeypatch.setattr(deployment.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=payload))
    with pytest.raises(ValueError, match="Unsafe backend archive member"):
        deployment.export_release("a" * 40)
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_release_export_uses_separate_directory_and_preserves_working_copy(monkeypatch, tmp_path):
    working_file = tmp_path / "compose.yaml"
    working_file.write_text("local changes", encoding="utf-8")
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "run", lambda *a, **k: None)
    monkeypatch.setattr(deployment.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=release_archive("backend/compose.yaml")))
    exported = deployment.export_release("a" * 40)
    assert exported.is_relative_to(tmp_path / ".deploy" / "releases")
    assert (exported / "compose.yaml").read_text() == "deployment source\n"
    assert working_file.read_text() == "local changes"


def test_failed_build_does_not_start_or_record_a_deployment(monkeypatch, tmp_path):
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(deployment, "STATE", tmp_path / ".deploy" / "state.json")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "build" in command:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(deployment, "run", fake_run)
    assert deployment.main(["up"]) == 1
    assert len(calls) == 2  # config, then failing build; no up/reset/stash/checkout.
    assert calls[-1][-3:] == ["build", "api-v1", "api-v2"]
    assert not deployment.STATE.exists()


def test_all_nginx_temp_directories_use_writable_tmpfs():
    # Even unused gateway modules initialize their temp directories during -t.
    config = (Path(__file__).parent / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    configured = dict(re.findall(r"^\s*(\w+_temp_path)\s+(\S+);", config, re.MULTILINE))
    assert configured == {
        "client_body_temp_path": "/tmp/client_body", "proxy_temp_path": "/tmp/proxy",
        "fastcgi_temp_path": "/tmp/fastcgi", "uwsgi_temp_path": "/tmp/uwsgi",
        "scgi_temp_path": "/tmp/scgi",
    }
