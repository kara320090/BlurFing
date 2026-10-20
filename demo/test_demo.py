"""Synthetic fixtures only. No real models, fingerprints or sensor measurements."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

import httpx
import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from test_experimental_photo_v2 import png, synthetic_payload
from demo import connect, evaluate_photo, evaluate_scanner, rehearse_photo, runtime


def registry():
    return [dict(source_sha256=f'{i:064x}', encoded_RGB_sha256=f'{i + 100:064x}',
                 upright_RGB_sha256=f'{i + 200:064x}', role='consumed_GT7' if i < 8 else 'consumed_holdout')
            for i in range(1, 16)]


@pytest.fixture
def configured(tmp_path, monkeypatch):
    def asset(name, content=b'synthetic-test-fixture'):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(content)
        return str(path)
    checkpoint = asset('model/final_context_whole_pad.pt')
    monkeypatch.setattr(runtime, 'V6_SHA', runtime.digest(checkpoint))
    metadata = dict(training_complete=True, development_only=True, approved_for_inference=False,
                    independent_final_test=False, model_sha256=runtime.V6_SHA)
    cfg = asset('model/final_config.private.json', json.dumps(metadata).encode())
    reg = asset('registry.json', json.dumps(registry()).encode())
    col = asset('col.tar.gz')
    monkeypatch.setattr(runtime, 'COLFISPOOF_SHA', runtime.digest(col))
    hand = asset('hand.task')
    executable = asset('python')
    config = dict(schema_version='blurfing-demo-runtime-v1', photo=dict(api_python=executable, ai_python=executable,
                  model_dir=str(tmp_path / 'model'), config_sha256=runtime.digest(cfg), consumed_registry=reg,
                  registry_sha256=runtime.digest(reg), colfispoof_python=executable, colfispoof_source=str(tmp_path),
                  colfispoof_model=col, hand_python=executable, hand_model=hand, hand_model_sha256=runtime.digest(hand),
                  development_replay=False), scanner=dict(api_python=executable, ai_python=executable,
                  nbis_config=asset('nbis.json'), sourceafis_config=asset('sourceafis.json'), sourceafis_home=str(tmp_path)))
    return config


def test_asset_checks_never_promote_configuration_to_inference(configured):
    report = runtime.preflight(configured)
    assert report['configured']
    assert not report['inference_verified'] and not report['privacy_validated']
    assert 'synthetic-test-fixture' not in json.dumps(report)
    env = runtime.service_environment(configured, 'photo')
    assert env['BLURFING_PHOTO_ENGINES'] == 'synthetic_v23'
    assert env['BLURFING_PHOTO_DEVELOPMENT_REPLAY'] == 'false'


@pytest.mark.parametrize('field', ['config_sha256', 'registry_sha256', 'hand_model_sha256'])
def test_missing_or_wrong_asset_hash_rejected(configured, field):
    configured['photo'].pop(field)
    assert not runtime.preflight(configured, 'photo')['configured']


def test_registry_history_cannot_be_replaced_with_empty_list(configured):
    path = Path(configured['photo']['consumed_registry'])
    path.write_text('[]')
    configured['photo']['registry_sha256'] = runtime.digest(path)
    assert not runtime.preflight(configured, 'photo')['configured']


def test_model_approval_flags_cannot_be_changed_to_bypass_handoff(configured):
    path = Path(configured['photo']['model_dir']) / 'final_config.private.json'
    value = json.loads(path.read_text())
    value['approved_for_inference'] = True
    path.write_text(json.dumps(value))
    configured['photo']['config_sha256'] = runtime.digest(path)
    assert not runtime.preflight(configured, 'photo')['configured']


def test_config_rejects_string_replay_and_does_not_modify_input(tmp_path, configured):
    configured['photo']['development_replay'] = 'false'
    path = tmp_path / 'runtime.private.json'
    path.write_text(json.dumps(configured))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        runtime.load_config(path)
    assert path.read_bytes() == before


def test_probe_records_separate_environment_checks_without_inference_claim(configured, monkeypatch):
    from types import SimpleNamespace
    def run(args, **kwargs):
        body = json.dumps(dict(python='synthetic-test-version', packages={'fixture': '0'})) if '-I' in args else ''
        return SimpleNamespace(returncode=0, stdout=body, stderr='')
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    report = runtime.preflight(configured, 'photo', probe=True)
    assert report['configured'] and report['runtime_probe_requested']
    assert len([r for r in report['checks'] if r['check'].endswith('_environment')]) == 4
    assert not report['inference_verified']


def test_missing_assets_do_not_execute_any_probe(configured, monkeypatch):
    configured['photo']['model_dir'] += '/missing'
    def fail(*args, **kwargs):
        raise AssertionError('missing assets must not execute anything')
    monkeypatch.setattr(runtime.subprocess, 'run', fail)
    monkeypatch.setattr(runtime.subprocess, 'check_output', lambda *args, **kwargs: 'synthetic-code-revision')
    assert not runtime.preflight(configured, 'photo', probe=True)['configured']


@pytest.mark.parametrize('platform,expected,other', [
    ('win32', 'BLURFING_NBIS_WINDOWS_CONFIG', 'BLURFING_NBIS_LINUX_CONFIG'),
    ('linux', 'BLURFING_NBIS_LINUX_CONFIG', 'BLURFING_NBIS_WINDOWS_CONFIG')])
def test_scanner_uses_only_the_selected_platform_runtime(configured, monkeypatch, platform, expected, other):
    monkeypatch.setenv('BLURFING_NBIS_WINDOWS_CONFIG', 'stale-windows-config')
    monkeypatch.setenv('BLURFING_NBIS_LINUX_CONFIG', 'stale-linux-config')
    monkeypatch.setenv('BLURFING_NBIS_CONFIG', 'stale-generic-config')
    env = runtime.service_environment(configured, 'scanner', platform=platform)
    assert env[expected] == configured['scanner']['nbis_config']
    assert other not in env and 'BLURFING_NBIS_CONFIG' not in env
    assert env['BLURFING_SCANNER_AI_ROOT'] == str(runtime.ROOT / 'ai')


@pytest.mark.parametrize('target', ['-oProxyCommand=bad', 'user@host;bad', 'a\nb', 'host bad', '$(bad)'])
def test_tunnel_arguments_cannot_be_shell_options(target):
    with pytest.raises(ValueError):
        connect.ssh_command(target)


def test_ready_checks_both_real_contracts_and_does_not_claim_inference():
    photo = dict(status='ready', contract_version='photo-experimental-v2', result_kind='experimental',
                 production_approved=False, photo_engines=['synthetic_v23'])
    scanner = dict(schema_version='scanner-comparison-v1', configured=True, processing='experimental_scanner',
                   matcher='SourceAFIS', inference_checked=False)
    connect.check_ready(photo, scanner)
    with pytest.raises(ValueError):
        connect.check_ready(dict(photo, photo_engines=['native_v12']), scanner)
    with pytest.raises(ValueError):
        connect.check_ready(photo, dict(scanner, configured=False))
    with pytest.raises(ValueError):
        connect.check_ready(photo, dict(status='ready'))
    command = connect.ssh_command('demo-user@school-host')
    assert 'ExitOnForwardFailure=yes' in command
    assert '127.0.0.1:8002:127.0.0.1:8002' in command


def client_for(content, fail_first=False, tamper=False, rejected=False):
    calls = []
    def handle(request):
        body = request.read()
        identity = re.search(rb'name="request_id"\r\n\r\n([^\r]+)', body)[1].decode()
        calls.append(identity)
        if fail_first and len(calls) == 1:
            return httpx.Response(503, json={'private': 'must not be written as error text'})
        payload = synthetic_payload(content, identity, 'synthetic_v23', all_rejected=rejected)
        if tamper:
            payload['source_sha256'] = '0' * 64
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handle)), calls


@pytest.mark.parametrize('fail_first,tamper,rejected,passes', [
    (False, False, False, True), (True, False, False, False),
    (False, True, False, False), (False, False, True, False)])
def test_rehearsal_keeps_every_attempt_and_validates_binding_and_readback(tmp_path, fail_first, tamper, rejected, passes):
    content = png(np.full((12, 16, 3), 120, np.uint8))
    source = tmp_path / 'source.png'
    source.write_bytes(content)
    client, calls = client_for(content, fail_first, tamper, rejected)
    with client:
        report = rehearse_photo.rehearsal(source, 'http://127.0.0.1:8001', tmp_path / 'run', client=client)
    assert len(report['runs']) == len(set(calls)) == 3
    assert report['three_consecutive_http_runs_within_120s'] is passes
    assert not report['android_e2e_verified'] and not report['actual_model_execution_attested']
    assert source.read_bytes() == content
    assert not (tmp_path / 'run/INCOMPLETE').exists()
    assert 'must not be written' not in json.dumps(report)
    if passes:
        assert (tmp_path / 'run/run-01/returned.png').is_file()
    with pytest.raises(FileExistsError):
        rehearse_photo.rehearsal(source, 'http://127.0.0.1:8001', tmp_path / 'run')


@pytest.mark.parametrize('url', ['http://school.example', 'https://user:password@host',
                                  'https://host?token=private', 'file:///source'])
def test_private_upload_cannot_use_unsafe_address(url):
    with pytest.raises(ValueError):
        rehearse_photo.address(url)


@pytest.fixture
def evaluation(tmp_path):
    (tmp_path / 'registry.json').write_text(json.dumps(registry()))
    rows = []
    for i, split in enumerate(('development', 'evaluation')):
        content = png(np.full((12, 16, 3), 120 + i, np.uint8))
        source, response, gt = f'{split}.png', f'{split}.json', f'{split}-gt.png'
        (tmp_path / source).write_bytes(content)
        (tmp_path / response).write_text(json.dumps(synthetic_payload(content, split, 'synthetic_v23')))
        mask = np.zeros((12, 16), np.uint8)
        mask[0, 0] = mask[5, 5] = 255  # One detected pixel, one missed fingertip pixel.
        Image.fromarray(mask).save(tmp_path / gt)
        rows.append(dict(sample_id=split, split=split, participant_alias=f'person-{i}', capture_group=f'group-{i}',
                         source=source, source_sha256=hashlib.sha256(content).hexdigest(), response=response,
                         all_visible_fingertips_annotated=True, never_used_for_training_or_tuning=True,
                         regions=[dict(mask=gt, visibility='visible', human_reviewed=True)]))
    manifest = dict(schema_version='blurfing-photo-evaluation-v1', samples=rows, consumed_registry='registry.json',
                    independence_confirmed_by_provider=False)
    path = tmp_path / 'manifest.private.json'
    path.write_text(json.dumps(manifest))
    return path, manifest


def test_missing_fingertips_stay_in_evaluation_denominator(evaluation):
    path, _ = evaluation
    report = evaluate_photo.evaluate(path)
    for sample in report['samples']:
        assert sample['candidate_vs_visible']['recall'] == .5
        assert sample['candidate_vs_visible']['excess_pixels'] == 1
        assert sample['regions'][0]['applied_coverage'] == .5
    assert not report['planned_minimum_collection_met']
    assert not report['independence_attested'] and not report['privacy_validated']


@pytest.mark.parametrize('field', ['participant_alias', 'capture_group', 'source_sha256'])
def test_independent_split_rejects_leakage(evaluation, field):
    path, manifest = evaluation
    manifest['samples'][1][field] = manifest['samples'][0][field]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        evaluate_photo.evaluate(path)


def test_consumed_evaluation_sample_cannot_be_promoted_to_holdout(evaluation):
    path, manifest = evaluation
    rows = registry()
    rows[-1]['source_sha256'] = manifest['samples'][1]['source_sha256']
    (path.parent / 'registry.json').write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='consumed'):
        evaluate_photo.evaluate(path)


@pytest.mark.parametrize('missing', [False, True])
def test_scanner_reference_retains_raw_score_or_unavailable_without_claims(tmp_path, missing):
    paths = []
    for name, color in [('reference', 20), ('original', 40), ('processed', 80)]:
        path = tmp_path / (name + '.png')
        Image.fromarray(np.full((12, 16), color, np.uint8)).save(path)
        paths.append(path)
    def matcher(images, pairs, **kwargs):
        if missing:
            raise ValueError('private matcher path must not appear in report')
        return dict(sourceafis_version='synthetic-test-runtime', pairs=[
            dict(key=p['key'], status='ok', score=201.75, probe_minutiae=12, candidate_minutiae=13) for p in pairs])
    report = evaluate_scanner.evaluate(*paths, tmp_path / 'scores', matcher=matcher)
    assert not report['privacy_validated']
    assert all(row['score'] == (None if missing else 201.75) for row in report['pairs'])
    assert 'private matcher path' not in json.dumps(report)
    with pytest.raises(ValueError, match='separately_acquired'):
        evaluate_scanner.evaluate(paths[1], paths[1], paths[2], tmp_path / 'self-comparison', matcher=matcher)
