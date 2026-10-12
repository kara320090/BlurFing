"""Preparation-only Windows raw/match bridge; no runtime is bundled or built.

Same basic call/result contract as nbis_matcher.run_nbis_job. Native batch and
Windows equivalence are deliberately not claimed. See WINDOWS_SETUP.md.
Set BLURFING_NBIS_WINDOWS_CONFIG to a separately verified Windows runtime JSON.
All job files go to a fresh /tmp directory; imports never execute NBIS.
"""

from pathlib import Path

import hashlib

import json

import os

import re

import subprocess

import tempfile

from PIL import Image

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inspect_runtime(config_path=None):
    """Validate explicit hash-pinned PE bridge without launching it."""
    value = config_path or os.environ.get('BLURFING_NBIS_WINDOWS_CONFIG') or os.environ.get('BLURFING_NBIS_CONFIG')
    if not value:
        raise RuntimeError('Windows NBIS runtime is not configured; no Linux fallback')
    config = Path(value).resolve(strict=True)
    runtime = json.loads(config.read_text(encoding='utf-8'))
    if runtime.get('version') != 'NBIS5.0.0' or runtime.get('contract') != 'blurfing-raw-match-v1':
        raise ValueError('Expected NBIS5.0.0 blurfing-raw-match-v1 runtime')
    exe = Path(runtime['exe'])
    if not exe.is_absolute():
        raise ValueError('Windows runtime exe must be an absolute path')
    exe = exe.resolve(strict=True)
    with exe.open('rb') as handle:
        if handle.read(2) != b'MZ':
            raise ValueError('Windows NBIS bridge must be PE')
        handle.seek(0x3c)
        import struct
        pointer = handle.read(4)
        if len(pointer) != 4:
            raise ValueError('Truncated PE header')
        handle.seek(struct.unpack('<I', pointer)[0])
        if handle.read(4) != b'PE\0\0' or handle.read(2) != b'\x64\x86':
            raise ValueError('Expected x86-64 PE bridge')
    if not exe.is_file() or exe.suffix.lower() != '.exe' or sha(exe) != runtime['exe_sha256']:
        raise ValueError('Windows executable permission/hash check failed')
    runtime['exe'] = str(exe)
    return runtime

def run_nbis_job(images, pairs, *, run_name):
    """Extract raw8 at nominal 500 DPI and match sequentially in /tmp.

    Native policy: MINDTCT V2 -> lfs2nist_format -> bz_prune(max150),
    min_computable_minutiae=10. Low feature counts are not valid nonmatches.
    Failures raise and retain audit evidence; there are no automatic retries.
    """
    if not isinstance(run_name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,69}', run_name):
        raise ValueError('ASCII run name of at most 70 characters required')
    if not images:
        raise ValueError('At least one image required')
    for key in images:
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', key):
            raise ValueError('Simple ASCII image key required')
    pairs = list(pairs)
    keys = []
    for pair in pairs:
        key = pair['key']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,191}', key):
            raise ValueError('Simple ASCII pair key required')
        if pair['probe'] not in images or pair['candidate'] not in images:
            raise ValueError('Pair references unknown image')
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate pair keys')
    runtime = inspect_runtime()  # Missing runtime fails before creating job files.
    sources = {key: Path(path).resolve(strict=True) for key, path in images.items()}
    hashes = {key: sha(path) for key, path in sources.items()}
    for path in sources.values():
        with Image.open(path) as im:
            if not all(32 <= size <= 4096 for size in im.size):
                raise ValueError('NBIS project dimensions must be 32..4096')
            im.load()
    folder = Path(tempfile.mkdtemp(prefix='blurfing_nbis_windows_' + run_name + '_', dir=tempfile.gettempdir()))
    audit_path = folder / 'audit.json'
    audit = dict(status='running', commands=[], retry_count=0, failure_is_nonmatch=False,
                 output_folder=str(folder), runtime_sha256=runtime['exe_sha256'])
    def persist():
        audit_path.write_text(json.dumps(audit, indent=2), encoding='utf-8')
    def run(args, stage):
        if sha(runtime['exe']) != runtime['exe_sha256']:
            raise RuntimeError('Windows runtime changed during job')
        command = dict(stage=stage, args=args, status='running')
        audit['commands'].append(command); persist()
        try:
            result = subprocess.run([runtime['exe']] + args, cwd=folder,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45, shell=False)
        except subprocess.TimeoutExpired as exc:
            command.update(status='timeout', message=str(exc))
            persist()
            raise
        except OSError as exc:
            command.update(status='process_launch_failure', message=str(exc))
            persist()
            raise
        command.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr,
                       status='ok' if result.returncode == 0 else 'process_failure')
        persist()
        if result.returncode:
            raise RuntimeError(f'NBIS {stage} exit={result.returncode}: {result.stderr}')
        return result
    records = []; templates = {}; scores = []
    persist()
    try:
        for key, path in sources.items():
            if sha(path) != hashes[key]:
                raise RuntimeError('Input changed after validation')
            # Match frozen Pillow convert(L) policy, including no EXIF transpose.
            with Image.open(path) as im:
                gray = im.convert('L'); w, h = gray.size; data = gray.tobytes()
            raw = folder / (key + '.raw'); xyt = folder / (key + '.xyt')
            raw.write_bytes(data)
            raw_result = run(['raw', str(raw), str(w), str(h), '500', str(xyt)], 'extract:' + key)
            if not re.fullmatch(r'[0-9]+\r?\n', raw_result.stdout):
                raise ValueError('Malformed RAW stdout')
            count = int(raw_result.stdout)
            lines = xyt.read_text(encoding='ascii').splitlines()
            if count < 0 or len(lines) != count or any(len(line.split()) != 4 for line in lines):
                raise ValueError('Invalid template/count output')
            for line in lines:
                tuple(map(int, line.split()))
            templates[key] = xyt
            records.append(dict(key=key, path=str(path), sha256=hashes[key], extracted_features=count,
                status='ok' if count >= 10 else 'insufficient_features', template_sha256=sha(xyt)))
        for pair in pairs:
            match_result = run(['match', str(templates[pair['probe']]), str(templates[pair['candidate']])], 'match:' + pair['key'])
            if not re.fullmatch(r'[0-9]+ [0-9]+ [0-9]+\r?\n', match_result.stdout):
                raise ValueError('Malformed MATCH stdout')
            score, probe, gallery = map(int, match_result.stdout.split())
            if min(score, probe, gallery) < 0 or max(probe, gallery) > 150:
                raise ValueError('Invalid score/count output')
            scores.append(dict(**pair, score=score, probe_features=probe, gallery_features=gallery,
                status='ok' if min(probe, gallery) >= 10 else 'insufficient_features',
                stderr=audit['commands'][-1]['stderr'].strip()))
        if any(sha(path) != hashes[key] for key, path in sources.items()):
            raise RuntimeError('Input changed during job')
        result = dict(matcher='NBIS5.0.0 MINDTCT/BOZORTH3', dpi=500, threshold=None,
            images=records, pairs=scores, independent_extraction=True, max_features=150,
            min_features=10, runtime_sha256=runtime['exe_sha256'], output_folder=str(folder),
            audit_path=str(audit_path), windows_equivalence_verified=False, native_batch=False)
        (folder / 'nbis_raw.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        audit['status'] = 'complete'; persist()
        return result
    except Exception as exc:
        audit.update(status='failed', failure=dict(kind='timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'malformed_output_or_template' if isinstance(exc, ValueError) else 'process_or_io_failure', exception_type=type(exc).__name__, message=str(exc)))
        persist()
        raise RuntimeError(f'Windows NBIS job failed; audit={audit_path}: {exc}') from exc
