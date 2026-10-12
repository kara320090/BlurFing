"""Explicit public fixture check on Windows; no bundled biometric inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from nbis_matcher_windows import inspect_runtime

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--wsq', required=True, type=Path)
    p.add_argument('--decoder', required=True, type=Path)
    p.add_argument('--reference-xyt', required=True, type=Path)
    a = p.parse_args()
    if platform.system() != 'Windows':
        p.error('Execute the real fixture validation on Windows')
    out = Path(tempfile.mkdtemp(prefix='blurfing_windows_fixture_'))
    audit = {'status': 'running', 'commands': [], 'output_folder': str(out),
             'windows_full_equivalence_verified': False, 'retry_count': 0}
    def save():
        (out / 'validation_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    def run(args):
        r = subprocess.run([str(x) for x in args], shell=False, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=60)
        audit['commands'].append({'exit_code': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        save()
        if r.returncode:
            raise RuntimeError('Fixture command failed')
        return r
    save()
    try:
        runtime = inspect_runtime(a.config)
        original_hashes = {str(x): sha(x) for x in [a.wsq, a.reference_xyt, a.decoder]}
        if sha(a.wsq) != '10b952aa4c00be8af38076001d306b9446a5db97653c2cc6be8bd779e6db528b':
            raise ValueError('Expected public a011p_03.wsq fixture')
        wsq = out / 'a011p_03.wsq'
        shutil.copy2(a.wsq, wsq)
        run([a.decoder.resolve(), 'raw', wsq, '-raw_out'])
        raw = out / 'a011p_03.raw'
        ncm = dict(line.split(None, 1) for line in (out / 'a011p_03.ncm').read_text().splitlines())
        if [int(ncm[k]) for k in ['PIX_WIDTH','PIX_HEIGHT','PIX_DEPTH']] != [336,512,8] or raw.stat().st_size != 172032:
            raise ValueError('Fixture decode dimensions/depth/size mismatch')
        xyt = out / 'fixture.xyt'
        r = run([runtime['exe'], 'raw', raw, 336, 512, 500, xyt])
        if r.stdout != '87\n' or r.stderr or len(xyt.read_bytes().splitlines()) != 87:
            raise ValueError('RAW fixture contract mismatch')
        if xyt.read_bytes() != a.reference_xyt.read_bytes():
            raise ValueError('Fixture XYT byte mismatch')
        match = run([runtime['exe'], 'match', xyt, xyt])
        if match.stdout != '499 87 87\n' or match.stderr:
            raise ValueError('MATCH fixture contract mismatch')
        if sha(runtime['exe']) != runtime['exe_sha256'] or any(sha(Path(x)) != h for x,h in original_hashes.items()):
            raise ValueError('Input/runtime changed')
        audit.update(status='complete', WINDOWS_BRIDGE_FIXTURE_VALIDATED=True,
                     raw_features=87, self_match='499 87 87', raw_sha256=sha(raw),
                     xyt_sha256=sha(xyt), runtime_sha256=runtime['exe_sha256'])
        save()
        print(json.dumps(audit, indent=2))
        return 0
    except Exception as exc:
        audit.update(status='failed', WINDOWS_BRIDGE_FIXTURE_VALIDATED=False,
                     error={'type': type(exc).__name__, 'message': str(exc)})
        save()
        print(json.dumps(audit, indent=2))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
