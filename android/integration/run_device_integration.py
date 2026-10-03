"""Build Android and check it against the real local backend plus an explicitly synthetic processor.

Run with a Python environment containing backend/requirements-dev.txt, JAVA_HOME and Android SDK.
Only synthetic pixels are uploaded, all listeners bind 127.0.0.1, and child servers/reverse mappings
created by this invocation are cleaned up. Does not modify production backend implementation.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--serial', required=True)
parser.add_argument('--skip-build', action='store_true')
args = parser.parse_args()
android = Path(__file__).resolve().parents[1]
repo = android.parent
sdk = Path(os.environ.get('ANDROID_HOME') or Path(os.environ.get('LOCALAPPDATA', '')) / 'Android' / 'Sdk')
adb = sdk / 'platform-tools' / ('adb.exe' if os.name == 'nt' else 'adb')
logs = android / 'build' / 'live-backend'
logs.mkdir(parents=True, exist_ok=True)
processes = []
mappings = []
streams = []

def call_adb(*arguments, timeout=120):
    result = subprocess.run([str(adb), '-s', args.serial, *arguments], check=True,
        capture_output=True, encoding='utf-8', errors='replace', timeout=timeout)
    return result.stdout

def start_server(module):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    stream = (logs / f'{port}-server.log').open('w', encoding='utf-8')
    streams.append(stream)
    child = subprocess.Popen([sys.executable, '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(port)],
        cwd=repo, stdout=stream, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    processes.append(child)
    for _ in range(60):
        if child.poll() is not None:
            raise RuntimeError(f'{module} stopped; inspect {logs}')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(.25)
    else:
        raise RuntimeError('Backend startup timed out')
    # --no-rebind refuses to overwrite an existing mapping.
    call_adb('reverse', '--no-rebind', f'tcp:{port}', f'tcp:{port}')
    mappings.append(port)
    return f'http://127.0.0.1:{port}'

try:
    if not args.skip_build:
        subprocess.run([str(android / ('gradlew.bat' if os.name == 'nt' else 'gradlew')),
            'assembleDebug', 'assembleDebugAndroidTest', '--max-workers=4', '--console=plain'], cwd=android, check=True)
    live = start_server('backend.main:app')
    fixture = start_server('android.integration.synthetic_backend:app')
    print(call_adb('install', '-r', str(android / 'app/build/outputs/apk/debug/app-debug.apk')).strip())
    print(call_adb('install', '-r', str(android / 'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk')).strip())
    result = call_adb('shell', 'am', 'instrument', '-w', '-e', 'class', 'com.blurfing.app.LiveBackendDeviceTest',
        '-e', 'liveBackendUrl', live, '-e', 'fixtureBackendUrl', fixture,
        'com.blurfing.app.test/androidx.test.runner.AndroidJUnitRunner', timeout=240)
    (logs / 'device-result.txt').write_text(result, encoding='utf-8')
    print(result)
    if 'OK (4 tests)' not in result or 'FAILURES' in result or 'INSTRUMENTATION_FAILED' in result:
        raise RuntimeError('Live Android/backend checks did not all pass; inspect device-result.txt')
finally:
    for port in mappings:
        try:
            call_adb('reverse', '--remove', f'tcp:{port}', timeout=10)
        except (subprocess.SubprocessError, OSError):
            print(f'Could not remove test reverse mapping tcp:{port}', file=sys.stderr)
    for child in processes:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
    for stream in streams:
        stream.close()
