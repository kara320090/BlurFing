"""Foreground SSH + USB demo connection; closes only its own tunnel/mapping."""
import argparse
import json
import os
import re
import socket
import subprocess
import time
from urllib.request import build_opener, ProxyHandler


def ssh_command(target):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@:-]{0,199}', target):
        raise ValueError('ssh_alias_or_user_at_host_required')
    return ['ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-L', '127.0.0.1:8001:127.0.0.1:8001', '-L', '127.0.0.1:8002:127.0.0.1:8002', target]


def check_ready(photo, scanner):
    if not isinstance(photo, dict) or not isinstance(scanner, dict):
        raise ValueError('readiness_object_required')
    if (photo.get('status') != 'ready' or photo.get('contract_version') != 'photo-experimental-v2'
            or photo.get('result_kind') != 'experimental' or photo.get('production_approved') is not False
            or photo.get('photo_engines') != ['synthetic_v23']):
        raise ValueError('photo_v23_not_configured')
    if (scanner.get('schema_version') != 'scanner-comparison-v1' or scanner.get('configured') is not True
            or scanner.get('processing') != 'experimental_scanner' or scanner.get('matcher') != 'SourceAFIS'
            or scanner.get('inference_checked') is not False):
        raise ValueError('scanner_not_configured')


def readiness():
    opener = build_opener(ProxyHandler({}))
    values = []
    for port in (8001, 8002):
        with opener.open(f'http://127.0.0.1:{port}/ready', timeout=5) as response:
            data = response.read(32769)
            if len(data) > 32768:
                raise ValueError('readiness_size')
            values.append(json.loads(data))
    check_ready(*values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-target', required=True, help='Existing SSH alias or user@host; never a password.')
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True, help='Physical USB device serial from adb devices.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    command = ssh_command(args.ssh_target)
    if args.serial.startswith('emulator-') or not re.fullmatch(r'[A-Za-z0-9_.-]+', args.serial):
        raise ValueError('physical_usb_serial_required')
    adb = [args.adb, '-s', args.serial]
    if args.dry_run:
        print(json.dumps(dict(ssh=command, usb=adb + ['reverse', 'tcp:8001', 'tcp:8001']), indent=2))
        return
    for port in (8001, 8002):
        with socket.socket() as connection:
            connection.settimeout(.3)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                raise ValueError('local_port_in_use_no_process_was_stopped')
    result = subprocess.run(adb + ['get-state'], capture_output=True, text=True, timeout=10, check=True)
    if result.stdout.strip() != 'device':
        raise ValueError('usb_device_not_authorized')
    mappings = subprocess.run(adb + ['reverse', '--list'], capture_output=True, text=True, timeout=10, check=True)
    if any('tcp:8001' in line.split()[1:] for line in mappings.stdout.splitlines()):
        raise ValueError('existing_reverse_mapping_not_changed')
    tunnel = None
    added = False
    try:
        tunnel = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for attempt in range(15):
            if tunnel.poll() is not None:
                raise ValueError('ssh_failed_use_existing_ssh_login_first')
            try:
                readiness()
                break
            except (OSError, ValueError):
                if attempt == 14:
                    raise ValueError('services_not_ready') from None
                time.sleep(1)
        subprocess.run(adb + ['reverse', 'tcp:8001', 'tcp:8001'], check=True, timeout=10)
        added = True
        print('Configured only, NOT inference verified. Android: http://127.0.0.1:8001; scanner: http://127.0.0.1:8002')
        print('Keep this terminal open. Ctrl+C removes this connection.')
        while tunnel.poll() is None:
            time.sleep(1)
        raise ValueError('ssh_connection_closed')
    finally:
        try:
            if added:
                subprocess.run(adb + ['reverse', '--remove', 'tcp:8001'], timeout=10, check=False)
        finally:
            if tunnel is not None and tunnel.poll() is None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Do not print subprocess command lines, usernames, or private paths.
        print('Connection failed: ' + (str(error) if type(error) is ValueError else type(error).__name__))
        raise SystemExit(2)
