"""Linux SourceAFIS adapter with isolated temporary outputs and template cache.

Keeps the Windows adapter's call and result contracts. Existing manifests,
classes, results and caches are read-only; each call creates a job under /tmp.
Temporary job files remain available through result['output_folder'].
"""

from pathlib import Path

import hashlib

import json

import math

import os

import re

import shutil

import subprocess

import tempfile

ROOT = Path(__file__).resolve().parents[1]

def _runtime():
    runtime_path = ROOT / 'docs/sourceafis_runtime.json'
    runtime = json.loads(runtime_path.read_text(encoding='utf8'))
    for artifact in runtime['artifacts']:
        path = ROOT / artifact['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact['sha256']:
            raise RuntimeError('SourceAFIS dependency hash changed')
    java = shutil.which('java')
    if not java:
        raise RuntimeError('Java executable not found on Linux PATH')
    tools = ROOT / 'private/sourceafis'
    return java, tools / 'classes', str(tools / 'lib' / '*')

def run_matcher_job(images, pairs, *, dpi=500., run_name='poc_matcher'):
    if not math.isfinite(dpi) or not 100 <= dpi <= 2000:
        raise ValueError('Experiment DPI must be within 100..2000')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', run_name):
        raise ValueError('Simple run name required')
    if len(images) != len(set(images)):
        raise ValueError('Duplicate image keys')
    for key, path in images.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', key):
            raise ValueError('Simple image keys required')
        if not Path(path).is_file():
            raise FileNotFoundError(path)
    ids = [p['key'] for p in pairs]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate pair IDs')
    if any(p['probe'] not in images or p['candidate'] not in images for p in pairs):
        raise ValueError('Pair references unknown image')

    java, classes, jars = _runtime()
    source = ROOT / 'scripts/java/BlurFingMatcher.java'
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    marker = classes / 'source_sha256.txt'
    reuse = (marker.is_file() and marker.read_text() == source_digest
             and (classes / 'BlurFingMatcher.class').is_file())
    javac = None
    if not reuse:
        javac = shutil.which('javac')
        if not javac:
            raise RuntimeError('Matching cached class unavailable; javac required on Linux PATH')

    output = Path(tempfile.mkdtemp(prefix='blurfing_' + run_name + '_', dir='/tmp'))
    if not reuse:
        classes = output / 'classes'
        classes.mkdir()
        subprocess.run([javac, '-encoding', 'UTF-8', '--release', '11',
                        '-cp', jars, '-d', str(classes), str(source)],
                       check=True, timeout=60)
    cache = output / 'templates'
    cache.mkdir()
    request = {'dpi': float(dpi),
               'images': [{'key': key, 'path': str(Path(path).resolve())}
                          for key, path in images.items()], 'pairs': pairs}
    request_path = output / 'matcher_request.json'
    result_path = output / 'matcher_raw.json'
    request_path.write_text(json.dumps(request, indent=2), encoding='utf8')
    classpath = os.pathsep.join([str(classes), jars])
    with (output / 'java_stderr.log').open('w', encoding='utf8') as log:
        subprocess.run([java, '-Xmx1g', '-Djava.awt.headless=true', '-cp',
                        classpath, 'BlurFingMatcher', str(request_path),
                        str(result_path), str(cache)],
                       check=True, stderr=log, timeout=300)
    result = json.loads(result_path.read_text(encoding='utf8'))
    result['output_folder'] = str(output)
    return result

def match_fingerprints(probe_path, candidate_path, *, dpi=500.):
    result = run_matcher_job(
        {'probe': probe_path, 'candidate': candidate_path},
        [{'key': 'pair', 'probe': 'probe', 'candidate': 'candidate'}],
        dpi=dpi, run_name='sourceafis_single')
    pair = result['pairs'][0]
    if pair['status'] != 'ok':
        raise RuntimeError(pair.get('error', 'Matcher failed'))
    return pair['score']
