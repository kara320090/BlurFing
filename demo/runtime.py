"""Check private handoff assets and launch existing loopback services unchanged.

No installer, model downloader, empty registry, or fallback processor is used.
File checks are configuration checks, never proof of inference or protection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
V6_SHA = '0c9d057ab220daadc369ed425a67f732d44e32a9da63155cc53842c2a545e14b'
COLFISPOOF_SHA = 'f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f'
SHA = re.compile(r'[0-9a-f]{64}\Z')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def load_config(path):
    path = Path(path).resolve()
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or value.get('schema_version') != 'blurfing-demo-runtime-v1':
        raise ValueError('runtime_schema_required')
    for service in ('photo', 'scanner'):
        section = value.get(service)
        if not isinstance(section, dict):
            raise ValueError('runtime_sections_required')
        for key, item in list(section.items()):
            if key.endswith('_sha256') or key == 'development_replay':
                continue
            if not isinstance(item, str) or not item.strip():
                raise ValueError('runtime_paths_required')
            candidate = Path(item).expanduser()
            section[key] = str(candidate if candidate.is_absolute() else path.parent / candidate)
    if type(value['photo'].get('development_replay')) is not bool:
        raise ValueError('explicit_replay_boolean_required')
    return value


def preflight(config, service='all', probe=False):
    checks = []
    selected = ('photo', 'scanner') if service == 'all' else (service,)

    def check(name, condition, **details):
        checks.append(dict(check=name, passed=bool(condition), **details))

    def file(section, key, expected=None):
        candidate = Path(section.get(key, ''))
        present = candidate.is_file()
        check(key + '_exists', present)
        if expected is not None and present:
            actual = digest(candidate)
            check(key + '_sha256', isinstance(expected, str) and SHA.fullmatch(expected) is not None
                  and actual == expected, observed_sha256=actual)
        return present

    for name in selected:
        section = config[name]
        first = len(checks)
        for key in ('api_python', 'ai_python'):
            file(section, key)
        if name == 'photo':
            model = Path(section.get('model_dir', ''))
            files = dict(section, checkpoint=str(model / 'final_context_whole_pad.pt'),
                         model_config=str(model / 'final_config.private.json'))
            file(files, 'checkpoint', V6_SHA)
            if file(files, 'model_config', section.get('config_sha256') or ''):
                try:
                    metadata = json.loads(Path(files['model_config']).read_text(encoding='utf-8'))
                    valid = (isinstance(metadata, dict) and metadata.get('training_complete') is True and metadata.get('development_only') is True
                             and metadata.get('approved_for_inference') is False
                             and metadata.get('independent_final_test') is False
                             and metadata.get('model_sha256') == V6_SHA)
                    check('v6_development_identity', valid)
                except (ValueError, OSError):
                    check('v6_development_identity', False)
            if file(section, 'consumed_registry', section.get('registry_sha256') or ''):
                try:
                    rows = json.loads(Path(section['consumed_registry']).read_text(encoding='utf-8'))
                    keys = {'source_sha256', 'encoded_RGB_sha256', 'upright_RGB_sha256', 'role'}
                    valid = (isinstance(rows, list) and bool(rows) and all(
                        isinstance(row, dict) and set(row) == keys and row['role'] in ('consumed_GT7', 'consumed_holdout')
                        and all(isinstance(row[k], str) and SHA.fullmatch(row[k]) for k in keys - {'role'}) for row in rows))
                    if valid:
                        valid = (len({r['source_sha256'] for r in rows if r['role'] == 'consumed_GT7'}) == 7
                                 and len({tuple(sorted((r['encoded_RGB_sha256'], r['upright_RGB_sha256'])))
                                          for r in rows if r['role'] == 'consumed_holdout'}) >= 8)
                    check('registry_history_retained', valid)
                except (ValueError, OSError):
                    check('registry_history_retained', False)
            for key in ('colfispoof_python', 'hand_python'):
                file(section, key)
            check('colfispoof_source_exists', bool(section.get('colfispoof_source')) and Path(section['colfispoof_source']).is_dir())
            file(section, 'colfispoof_model', COLFISPOOF_SHA)
            file(section, 'hand_model', section.get('hand_model_sha256') or '')
        else:
            file(section, 'nbis_config')
            file(section, 'sourceafis_config')
            check('sourceafis_home_exists', bool(section.get('sourceafis_home')) and Path(section['sourceafis_home']).is_dir())
        if probe and all(row['passed'] for row in checks[first:]):
            environments = {'api': section['api_python'], 'ai': section['ai_python']}
            if name == 'photo':
                environments.update(colfispoof=section['colfispoof_python'], hand=section['hand_python'])
            for label, executable in environments.items():
                try:
                    snapshot = subprocess.run([executable, '-I', '-c',
                        'import sys,json,importlib.metadata as m; '
                        'print(json.dumps(dict(python=sys.version.split()[0], '
                        'packages={d.metadata["Name"]:d.version for d in m.distributions()})))'],
                        capture_output=True, text=True, timeout=30, check=False)
                    info = json.loads(snapshot.stdout) if snapshot.returncode == 0 else {}
                    pip = subprocess.run([executable, '-m', 'pip', 'check'], capture_output=True, timeout=30, check=False)
                    check(label + '_environment', bool(info) and pip.returncode == 0, observed_environment=info)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    check(label + '_environment', False)
            # Use the real V6 validator, including protocol/code/encoder binding.
            # stdout/stderr can contain private paths and are never echoed.
            code = ("import sys; sys.path.insert(0,sys.argv[1]); "
                    "from infer_whole_pad_context_v6 import load_model; "
                    "load_model(sys.argv[2])") if name == 'photo' else (
                    "import sys; sys.path.insert(0,sys.argv[1]); "
                    "import protect_fingerprint, sourceafis_matcher; "
                    "from nbis_matcher import inspect_runtime; "
                    "from platform_loader import load_adapter; "
                    "inspect_runtime(); load_adapter('sourceafis')._runtime()")
            args = [section['ai_python'], '-c', code, str(ROOT / 'ai/scripts')]
            if name == 'photo':
                args.append(section['model_dir'])
            try:
                result = subprocess.run(args, env=service_environment(config, name),
                                        capture_output=True, timeout=180, check=False)
                check(name + '_runtime_probe', result.returncode == 0)
            except (OSError, subprocess.TimeoutExpired):
                check(name + '_runtime_probe', False)
        checks[first:] = [dict(row, service=name) for row in checks[first:]]
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True,
                                         stderr=subprocess.DEVNULL, timeout=10).strip() or 'unknown'
    except (OSError, subprocess.SubprocessError):
        commit = 'unknown'
    return dict(schema_version='blurfing-demo-preflight-v1', checks=checks, source_commit=commit,
                runtime_tool_sha256=digest(__file__),
                configured=all(row['passed'] for row in checks), runtime_probe_requested=probe,
                inference_verified=False, physical_devices_verified=False, privacy_validated=False)


def service_environment(config, name, *, platform=None):
    env = os.environ.copy()
    section = config[name]
    if name == 'photo':
        bindings = {'BLURFING_PHOTO_PYTHON': 'ai_python', 'BLURFING_PHOTO_MODEL': 'model_dir',
                    'BLURFING_PHOTO_CONSUMED_REGISTRY': 'consumed_registry',
                    'BLURFING_COLFISPOOF_PYTHON': 'colfispoof_python', 'BLURFING_COLFISPOOF_SOURCE': 'colfispoof_source',
                    'BLURFING_COLFISPOOF_MODEL': 'colfispoof_model', 'BLURFING_HAND_PYTHON': 'hand_python',
                    'BLURFING_HAND_MODEL': 'hand_model'}
        env.update({key: section[field] for key, field in bindings.items()})
        env.update(BLURFING_PHOTO_ENGINES='synthetic_v23', BLURFING_PHOTO_TIMEOUT_SECONDS='600',
                   BLURFING_PHOTO_BRIDGE=str(ROOT / 'ai/scripts/export_photo_permissions_v1.py'),
                   BLURFING_PHOTO_DEVELOPMENT_REPLAY=str(section['development_replay']).lower())
    else:
        nbis_key = 'BLURFING_NBIS_WINDOWS_CONFIG' if (platform or sys.platform) == 'win32' else 'BLURFING_NBIS_LINUX_CONFIG'
        for key in ('BLURFING_NBIS_WINDOWS_CONFIG', 'BLURFING_NBIS_LINUX_CONFIG', 'BLURFING_NBIS_CONFIG'):
            env.pop(key, None)
        env[nbis_key] = section['nbis_config']
        env.update(BLURFING_SCANNER_PYTHON=section['ai_python'], BLURFING_SCANNER_AI_ROOT=str(ROOT / 'ai'),
                   BLURFING_SOURCEAFIS_CONFIG=section['sourceafis_config'],
                   BLURFING_SOURCEAFIS_HOME=section['sourceafis_home'])
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'serve'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--service', choices=('all', 'photo', 'scanner'), default='all')
    parser.add_argument('--probe', action='store_true', help='Load actual model/AI imports; no inference.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == 'serve' and args.service == 'all':
            raise ValueError('choose_one_service_per_terminal')
        report = preflight(config, args.service, probe=args.probe or args.command == 'serve')
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2)
        print(json.dumps(report, indent=2))
        if not report['configured']:
            return 2
        if args.command == 'serve':
            name = args.service
            folder, app, port = ('backend', 'experimental_photo_main:app', '8001') if name == 'photo' else (
                'sensor/server', 'scanner_api:app', '8002')
            return subprocess.call([config[name]['api_python'], '-m', 'uvicorn', app, '--app-dir', str(ROOT / folder),
                                    '--host', '127.0.0.1', '--port', port, '--workers', '1', '--no-access-log'],
                                   env=service_environment(config, name))
        return 0
    except (OSError, ValueError, KeyError):
        print('Invalid/missing runtime configuration or output. Private paths were not printed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
