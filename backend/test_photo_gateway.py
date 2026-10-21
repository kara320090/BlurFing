"""Standard-library-only routing/rollback tests; no real AI or Docker needed."""
import json
import configparser
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from connect_photo_nginx import change_with_rollback, main, replace_upstream, require_v23
from serve_photo_gateway import listen_socket, private_ipv4


READY = {"status": "ready", "contract_version": "photo-experimental-v2",
         "result_kind": "experimental", "photo_engines": ["synthetic_v23"],
         "production_approved": False}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "nginx.conf"
        self.original = (Path(__file__).parent / "nginx/nginx.conf").read_bytes()
        self.source.write_bytes(self.original)
        self.desired = replace_upstream(self.original, "172.21.0.1")
        self.backup = self.root / "backup.conf"

    def test_only_v2_upstream_changes(self):
        self.assertEqual(self.desired, self.original.replace(
            b"server api-v2:8001 resolve;", b"server 172.21.0.1:8001;"))

    def test_already_connected_is_idempotent(self):
        self.assertEqual(replace_upstream(self.desired, "172.21.0.1"), self.desired)

    def test_refuses_unknown_or_multiple_upstreams(self):
        for content in (b"", self.original + self.original,
                        self.original.replace(b"api-v2:8001", b"172.22.0.1:8001")):
            with self.subTest(content=content[:20]), self.assertRaises(ValueError):
                replace_upstream(content, "172.21.0.1")

    def test_refuses_public_wildcard_loopback_and_injected_addresses(self):
        for address in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "169.254.1.1", "::1",
                        "172.21.0.1;server other", "localhost"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                private_ipv4(address)

    def test_accepts_explicit_private_addresses(self):
        for address in ("172.21.0.1", "10.0.0.1", "192.168.10.1"):
            self.assertEqual(private_ipv4(address), address)

    def test_ready_requires_experimental_v23(self):
        require_v23(json.dumps(READY))
        for changes in ({"result_kind": "mock"}, {"photo_engines": ["native_v12"]},
                        {"production_approved": True}, {"production_approved": 0},
                        {"status": "not_ready"}, {"contract_version": "v1"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                require_v23(json.dumps(READY | changes))

    def test_v1_ready_is_not_v23_ready(self):
        with self.assertRaises(ValueError):
            require_v23('{"status":"ready"}')

    def test_success_keeps_mounted_inode_and_original_backup(self):
        inode = self.source.stat().st_ino
        check, reload, verify = Mock(), Mock(), Mock()
        change_with_rollback(self.source, self.original, self.desired, self.backup,
                             check, reload, verify)
        self.assertEqual(self.source.stat().st_ino, inode)
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(self.source.read_bytes(), self.desired)
        check.assert_called_once()
        reload.assert_called_once()
        verify.assert_called_once()

    def test_failed_nginx_validation_restores_config(self):
        check = Mock(side_effect=[ValueError("synthetic nginx failure"), None])
        reload, verify = Mock(), Mock()
        with self.assertRaises(ValueError):
            change_with_rollback(self.source, self.original, self.desired, self.backup,
                                 check, reload, verify)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(check.call_count, 2)
        reload.assert_called_once()
        verify.assert_not_called()

    def test_failed_reload_restores_config(self):
        reload = Mock(side_effect=[RuntimeError("synthetic reload failure"), None])
        with self.assertRaises(RuntimeError):
            change_with_rollback(self.source, self.original, self.desired, self.backup,
                                 Mock(), reload, Mock())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(reload.call_count, 2)

    def test_failed_health_check_restores_config(self):
        check, reload = Mock(), Mock()
        with self.assertRaises(RuntimeError):
            change_with_rollback(self.source, self.original, self.desired, self.backup,
                                 check, reload, Mock(side_effect=RuntimeError("not ready")))
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(reload.call_count, 2)

    def test_existing_backup_is_preserved(self):
        self.backup.write_bytes(b"older backup")
        with self.assertRaises(FileExistsError):
            change_with_rollback(self.source, self.original, self.desired, self.backup,
                                 Mock(), Mock(), Mock())
        self.assertEqual(self.backup.read_bytes(), b"older backup")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_changed_config_is_not_overwritten(self):
        self.source.write_bytes(b"teammate change")
        with self.assertRaises(ValueError):
            change_with_rollback(self.source, self.original, self.desired, self.backup,
                                 Mock(), Mock(), Mock())
        self.assertEqual(self.source.read_bytes(), b"teammate change")
        self.assertFalse(self.backup.exists())

    def test_idempotent_apply_only_verifies(self):
        self.source.write_bytes(self.desired)
        check, reload, verify = Mock(), Mock(), Mock()
        change_with_rollback(self.source, self.desired, self.desired, self.backup,
                             check, reload, verify)
        check.assert_not_called()
        reload.assert_not_called()
        verify.assert_called_once()
        self.assertFalse(self.backup.exists())

    def test_listener_binds_only_selected_address(self):
        sock = Mock()
        with patch("serve_photo_gateway.socket.socket", return_value=sock):
            self.assertIs(listen_socket("172.21.0.1", 8001), sock)
        sock.bind.assert_called_once_with(("172.21.0.1", 8001))
        sock.listen.assert_called_once_with(128)
        sock.close.assert_not_called()

    def test_unavailable_listener_closes_socket(self):
        sock = Mock()
        sock.bind.side_effect = OSError("address not assigned")
        with patch("serve_photo_gateway.socket.socket", return_value=sock):
            with self.assertRaises(OSError):
                listen_socket("172.21.0.1", 8001)
        sock.close.assert_called_once()

    def test_apply_only_executes_nginx_and_inspects_tunnel(self):
        commands = []
        nginx = {"Id": "nginx-id", "Config": {"Labels": {
            "com.docker.compose.project": "blurfing", "com.docker.compose.service": "nginx"}},
            "State": {"Running": True}, "NetworkSettings": {"Networks": {
                "blurfing_tunnel": {"Gateway": "172.21.0.1"}}},
            "Mounts": [{"Type": "bind", "Source": str(self.source),
                        "Destination": "/etc/nginx/nginx.conf"}]}
        tunnel = {"Id": "unchanged-tunnel", "Config": {"Labels": {
            "com.docker.compose.project": "blurfing", "com.docker.compose.service": "tunnel"}},
            "State": {"Running": True, "StartedAt": "same-time"}}

        def run(command, **kwargs):
            commands.append(command)
            args = command[1:]
            if args[0] == "inspect":
                value = nginx if args[1] == "blurfing-nginx-1" else tunnel
                return Mock(stdout=json.dumps([value]))
            self.assertEqual(args[:2], ["exec", "nginx-id"])
            return Mock(stdout=json.dumps(READY) if args[2] == "wget" else "")

        def fetch(url):
            return json.dumps({"mode": "mock"} if url.endswith("/info") else READY).encode()

        with patch("connect_photo_nginx.subprocess.run", side_effect=run), \
                patch("connect_photo_nginx.fetch_json", side_effect=fetch):
            self.assertEqual(main(["--gateway", "172.21.0.1", "--backup",
                                   str(self.backup), "--apply"]), 0)
        self.assertEqual(self.source.read_bytes(), self.desired)
        self.assertFalse(any("restart" in command or "compose" in command for command in commands))


class ServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.template = (Path(__file__).parent / "systemd/blurfing-photo-v23.service.example").read_text(encoding="utf-8")
        self.values = {
            "SERVICE_USER": "photo-test", "SERVICE_GROUP": "photo-test",
            "WORKING_DIRECTORY": "/srv/example-photo", "API_PYTHON": "/srv/api-venv/bin/python",
            "REPO_ROOT": "/srv/example-photo/source", "RUNTIME_CONFIG": "/srv/private/runtime.json",
            "DOCKER_GATEWAY": "172.30.0.1",
        }
        self.rendered = self.template
        for key, value in self.values.items():
            self.rendered = self.rendered.replace("@" + key + "@", value)
        self.unit = configparser.ConfigParser(interpolation=None)
        self.unit.read_string(self.rendered)

    def test_template_has_no_school_host_paths_or_installed_defaults(self):
        body = "\n".join(line for line in self.template.splitlines() if not line.startswith("#"))
        self.assertEqual(set(re.findall(r"@([A-Z_]+)@", body)), set(self.values))
        for field in ("/home/user", "20261021", "172.21.0.1"):
            self.assertNotIn(field, self.template)
        self.assertNotRegex("\n".join(line for line in self.rendered.splitlines()
                                     if not line.startswith("#")), r"@[A-Z_]+@")

    def test_system_boot_and_docker_ordering(self):
        self.assertEqual(self.unit["Install"]["WantedBy"], "multi-user.target")
        self.assertIn("docker.service", self.unit["Unit"]["After"].split())
        self.assertIn("network-online.target", self.unit["Unit"]["Wants"].split())

    def test_runs_existing_api_environment_without_root(self):
        service = self.unit["Service"]
        self.assertEqual(service["User"], "photo-test")
        self.assertEqual(service["Group"], "photo-test")
        self.assertEqual(service["WorkingDirectory"], "/srv/example-photo")
        command = service["ExecStart"]
        self.assertTrue(command.startswith("/srv/api-venv/bin/python "))
        self.assertIn("source/backend/serve_photo_gateway.py", command)
        self.assertIn("--config /srv/private/runtime.json", command)
        self.assertIn("--gateway 172.30.0.1", command)
        self.assertNotIn("0.0.0.0", command)

    def test_checks_startup_readiness_with_bounded_retry(self):
        service = self.unit["Service"]
        command = service["ExecStartPost"]
        self.assertIn("--fail", command)
        self.assertIn("--retry-all-errors", command)
        self.assertIn("--retry-max-time 210", command)
        self.assertIn("http://127.0.0.1:8001/ready", command)
        self.assertEqual(service["TimeoutStartSec"], "240s")

    def test_restarts_failed_process_and_reaps_children(self):
        service = self.unit["Service"]
        self.assertEqual(service["Restart"], "on-failure")
        self.assertEqual(service["RestartSec"], "15s")
        self.assertEqual(service["KillMode"], "mixed")
        self.assertEqual(service["TimeoutStopSec"], "90s")

    def test_uses_journal_and_private_temporary_files(self):
        service = self.unit["Service"]
        self.assertEqual(service["StandardOutput"], "journal")
        self.assertEqual(service["PrivateTmp"], "yes")
        self.assertEqual(service["NoNewPrivileges"], "yes")
        self.assertEqual(service["UMask"], "0077")


if __name__ == "__main__":
    unittest.main()
