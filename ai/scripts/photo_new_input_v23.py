"""Local arbitrary-photo review UI. Runtime selections are never training GT."""
import argparse
import hashlib
import io
import json
import secrets
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from PIL import Image, ImageCms, ImageDraw
from scipy import ndimage

from final_png_color_metadata_v1 import _source_metadata, save_final_rgb_png
from photo_pad_annotation_v1 import validate_points
from photo_resize_safety_v1 import validate_resize
from photo_source_rgb_v1 import canonical_rgb
from photo_visibility_reviewed_apply_v1 import apply_reviewed, pixels
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged

MAX_UPLOAD = 40 * 1024 * 1024
DECISIONS = ('visible', 'not_observed', 'uncertain')
FORWARD = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
           4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
           6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}
ASSETS = Path(__file__).resolve().parents[1] / 'app' / 'new_photo_v23'


def json_write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def display_png(rgb, icc, target):
    image = Image.fromarray(rgb)
    if icc:
        image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                         ImageCms.createProfile('sRGB'), outputMode='RGB')
    image.save(target)


def decode_upload(raw, folder):
    """Preserve original bytes. Normalize orientation once without resizing."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError('upload_empty_or_over_40_MiB')
    source = folder / 'original.upload'
    source.write_bytes(raw)
    with Image.open(source) as image:
        container, frame_count = image.format, getattr(image, 'n_frames', 1)
        # Phone JPEGs may contain an auxiliary gain map and be identified as MPO.
        # Select the primary image explicitly; never concatenate auxiliary frames.
        if (container not in ('JPEG', 'MPO', 'PNG')
                or (container != 'MPO' and frame_count != 1)):
            raise ValueError('JPEG_or_nonanimated_PNG_required')
        image.seek(0)
        validate_resize(image.height, image.width, 1.)
    rgb, identity = canonical_rgb(source)
    _, _, _, icc = _source_metadata(source, identity['original_source_sha256'])
    image = Image.fromarray(rgb)
    orientation = identity['source_exif_orientation']
    if orientation in FORWARD:
        image = image.transpose(FORWARD[orientation])
    rgb = np.array(image)
    exif = Image.Exif()
    exif[274] = 1
    image.save(folder / 'canonical.png', exif=exif, **({'icc_profile': icc} if icc else {}))
    display_png(rgb, icc, folder / 'display.png')
    identity.update(coordinate_system='upright_native_pixels', EXIF_transposed=True,
                    upright_RGB_sha256=pixels(rgb), shape=list(rgb.shape),
                    container_format=container, frame_count=frame_count, frame_used=0,
                    frame_policy='primary_image_only',
                    canonical_file_sha256=file_hash(folder / 'canonical.png'))
    return rgb, icc, identity


def review_candidates(baseline, refined, unanchored_owners):
    """Do not confuse a rejected protection permission with an absent proposal.

    Only restore pixels belonging to an explicitly unanchored owner. Detached
    noise removed for other reasons must stay removed. These are suggestions,
    never automatic protection permissions.
    """
    if (not isinstance(baseline, np.ndarray) or not isinstance(refined, np.ndarray)
            or baseline.dtype != np.bool_ or refined.dtype != np.bool_
            or not isinstance(unanchored_owners, np.ndarray) or unanchored_owners.dtype != np.bool_
            or baseline.ndim != 2 or refined.shape != baseline.shape
            or unanchored_owners.shape != baseline.shape):
        raise ValueError('review_candidate_mask_contract')
    restored = baseline & unanchored_owners & ~refined
    _, count = ndimage.label(restored, np.ones((3, 3), np.uint8))
    result = refined | restored
    return result, dict(version='retain_unanchored_review_candidates_v1',
        restored_candidate_components=int(count), restored_pixels=int(restored.sum()),
        baseline_pixels=int(baseline.sum()), boundary_refined_pixels=int(refined.sum()),
        proposed_pixels=int(result.sum()), proposal_pixel_sha256=pixels(result),
        boundary_review_required=True, protection_authorized=False,
        whole_finger_coverage_verified=False)


def read_raw_v6_support(detection, source, model_sha256):
    """Reload the actual prediction, never the downstream pose union mask."""
    from pad_refinement_data_contract_v2 import checked_bytes, read_mask, native_shape
    private = Path(detection) / 'private'
    prediction = json.loads((private / 'predictions/inference.private.json').read_text('utf-8'))
    manifest = json.loads(checked_bytes(private / 'dataset/manifest.input.private.json',
                                      prediction['input_manifest_sha256']))
    rows = prediction.get('rows', [])
    if (prediction.get('model_sha256') != model_sha256 or manifest.get('sources') != [source]
            or len(rows) != 1 or rows[0].get('source_id') != source['source_id']
            or rows[0].get('source_sha256') != source['source_sha256']
            or rows[0].get('native_shape') != list(native_shape(source))):
        raise ValueError('partial_pose_raw_V6_binding_mismatch')
    # The single-photo detector always writes this fixed ID; do not interpret
    # untrusted source IDs as file paths.
    if source['source_id'] != 'INPUT':
        raise ValueError('partial_pose_raw_V6_source_id')
    return read_mask(private / 'predictions/INPUT.png', rows[0]['prediction_sha256'], native_shape(source))


def propose(source, model, registry, output, *, allow_development_replay=True, minimal_artifacts=False, partial_observed_pose=False):
    """Executed in a separate process: existing detector policies stay unchanged."""
    from protect_photo_pitch_free_v1 import run
    from photo_crease_native_adapter_v1 import prepare
    from photo_rounded_native_pipeline_v1 import protection_contexts
    from pad_refinement_data_contract_v2 import read_body, read_mask, native_shape
    from photo_consumed_replay_v1 import development_replay
    import pad_refinement_tiles_v3 as tiles
    if type(minimal_artifacts) is not bool:
        raise ValueError('minimal_artifacts_flag_must_be_boolean')
    rgb, _ = canonical_rgb(source)
    detection = output / 'detection'
    _, report = run(source, model, registry, detection, development_replay=allow_development_replay,
                    include_observed_pose=True, include_coarse_pad=True,
                    complete_holes=True, allow_scanner=True, rounded_pads=True,
                    candidate_only=minimal_artifacts,partial_observed_pose=partial_observed_pose)
    with Image.open(detection / 'redacted_mask.png') as image:
        mask = np.asarray(image) > 0
    baseline = mask.copy()
    unanchored = np.zeros_like(mask)
    owner_binding = None
    if report.get('input_type') == 'PHOTO' and report.get('rounded_pad_metadata'):
        manifest = json.loads((detection / 'private/dataset/manifest.input.private.json').read_text('utf-8'))
        record = manifest['sources'][0]
        learned_support = (read_raw_v6_support(detection, record, report['model_sha256'])
                           if partial_observed_pose else None)
        with Image.open(detection / 'before_rounding_mask.png') as image:
            before = np.asarray(image) > 0
        worker = detection / 'private/hand.private.json'
        hand = json.loads(worker.read_text('utf-8')) if worker.exists() else None
        reg, _ = tiles.json_snapshot(registry)
        with development_replay(reg, [tiles.image_identity(source),
                                     tiles.image_identity(Path(record['source_path']))], enabled=allow_development_replay):
            derived, mask, boundary, pose = prepare(record, rgb, before, report['rounded_pad_metadata'], hand,
                                                    output / 'crease',partial_observed_pose=partial_observed_pose,
                                                    learned_support=learned_support)
            rows = boundary['candidates']
            if partial_observed_pose and pose is not None:
                owners = pose['owner_labels']
                selected_labels = [a['label'] for a in pose['axes']]
                # Keep V6 suggestions for unselected fingers visible for
                # review, without granting them automatic permissions.
                unanchored |= read_body(derived) & ~np.isin(owners, selected_labels)
                Image.fromarray(owners).save(output / 'pose_owners.png')
                owner_binding = dict(pixel_sha256=pixels(owners), selected_labels=selected_labels)
            if any(row.get('unanchored_candidate_excluded') for row in rows):
                body = read_body(derived)
                tip = read_mask(derived['tip_path'], derived['tip_sha256'], native_shape(derived))
                contexts = protection_contexts(body, tip, boundary, pose, complete_native_edges=True)
                for row, context in zip(rows, contexts):
                    if row.get('unanchored_candidate_excluded'):
                        unanchored |= context['body']
            json_write(output / 'boundary.private.json', boundary)
    if mask.shape != rgb.shape[:2]:
        raise ValueError('detector_mask_shape_mismatch')
    Image.fromarray(mask.astype(np.uint8) * 255).save(output / 'boundary_refined_mask.png')
    Image.fromarray(unanchored.astype(np.uint8) * 255).save(output / 'unanchored_owners.png')
    mask, selection = review_candidates(baseline, mask, unanchored)
    Image.fromarray(mask.astype(np.uint8) * 255).save(output / 'proposal.png')
    json_write(output / 'proposal.private.json', dict(
        source_sha256=file_hash(source), input_type=report.get('input_type'),
        candidate_selection=selection,
        partial_pose=owner_binding,
        candidate_only=True, human_reviewed=False, independent_validation=False))


class Session:
    def __init__(self, root, model=None, registry=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.model, self.registry = model, registry
        self.lock = threading.RLock()
        self.current = None
        self.busy = None
        self.error = None
        self.thread = None
        self.detector_available = bool(model and registry and Path(model).exists() and Path(registry).is_file())

    def state(self):
        with self.lock:
            result = dict(busy=self.busy, error=self.error, detector_available=self.detector_available,
                          output_root=str(self.root), photo=None)
            if self.current:
                c = self.current
                result['photo'] = dict(id=c['id'], name=c['name'], revision=c['revision'],
                    width=c['rgb'].shape[1], height=c['rgb'].shape[0], regions=c['regions'],
                    primary_frame_only=c['identity']['frame_count'] > 1,
                    candidate_selection=c.get('candidate_selection'),
                    can_undo=bool(c['history']), result=c['result'])
            return result

    def check(self, data):
        if self.busy:
            raise ValueError('job_running_please_wait')
        c = self.current
        if (not c or data.get('id') != c['id'] or type(data.get('revision')) is not int
                or data['revision'] != c['revision']):
            raise ValueError('stale_photo_or_revision_reload')
        return c

    def upload(self, raw, name):
        with self.lock:
            if self.busy:
                raise ValueError('job_running_please_wait')
            uid = secrets.token_hex(10)
            folder = self.root / uid
            folder.mkdir()
            try:
                rgb, icc, identity = decode_upload(raw, folder)
                safe_name = str(name).replace('\\', '/').split('/')[-1][:180]
                json_write(folder / 'source.private.json', dict(identity, name=safe_name,
                    data_role='interactive_development_not_training_GT'))
                c = dict(id=uid, name=safe_name, folder=folder, rgb=rgb, icc=icc, identity=identity,
                         labels=np.zeros(rgb.shape[:2], np.uint16), decisions={}, revision=-1,
                         history=[], result=None)
                self.save_revision(c)
            except Exception as exc:
                json_write(folder / 'failed-upload.private.json', dict(reason=str(exc)))
                raise
            self.current = c
            self.error = None
            return self.state()

    def save_revision(self, c):
        labels = c['labels']
        rows = []
        for rid, slices in enumerate(ndimage.find_objects(labels), 1):
            if slices is None:
                continue
            y, x = slices
            rows.append(dict(region_id=rid, decision=c['decisions'].get(rid, 'uncertain'),
                             pixels=int(np.count_nonzero(labels[slices] == rid)),
                             bbox=[x.start, y.start, x.stop, y.stop]))
        number = c['revision'] + 1
        destination = c['folder'] / ('revision-%04d' % number)
        rev = c['folder'] / ('pending-' + secrets.token_hex(8))
        rev.mkdir()
        Image.fromarray(labels).save(rev / 'labels.png')
        overlay = np.zeros((*labels.shape, 4), np.uint8)
        for row in rows:
            color = {'visible': (38, 200, 145, 100), 'not_observed': (120, 145, 175, 85),
                     'uncertain': (245, 173, 65, 110)}[row['decision']]
            overlay[labels == row['region_id']] = color
        Image.fromarray(overlay).save(rev / 'overlay.png')
        json_write(rev / 'selection.private.json', dict(regions=rows, labels_sha256=pixels(labels),
            source_RGB_sha256=pixels(c['rgb']), coordinate_system='upright_native_pixels',
            review_origin='runtime_draft', training_GT=False))
        rev.rename(destination)
        c.update(decisions={r['region_id']: r['decision'] for r in rows}, regions=rows,
                 revision=number, result=None)

    def edit(self, data):
        with self.lock:
            c = self.check(data)
            if c['revision'] >= 500:
                raise ValueError('session_edit_limit_load_photo_again')
            action = data.get('action')
            labels = c['labels'].copy()
            decisions = c['decisions'].copy()
            rid = data.get('region_id')
            if action in ('delete', 'decision', 'add', 'erase') and (
                    type(rid) is not int or rid not in decisions):
                raise ValueError('select_existing_region')
            if action == 'decision':
                if data.get('decision') not in DECISIONS:
                    raise ValueError('invalid_visibility_decision')
                decisions[rid] = data['decision']
            elif action == 'delete':
                labels[labels == rid] = 0
            elif action in ('new', 'add', 'erase'):
                points = data.get('points')
                validate_points(points, labels.shape[1], labels.shape[0], True)
                polygon = Image.new('1', (labels.shape[1], labels.shape[0]))
                ImageDraw.Draw(polygon).polygon([tuple(p) for p in points], fill=1)
                target = np.asarray(polygon, dtype=bool)
                if action == 'new':
                    if len(decisions) >= 128:
                        raise ValueError('maximum_128_regions')
                    rid = next(i for i in range(1, 129) if i not in decisions)
                if action in ('new', 'add'):
                    if np.any(target & (labels != 0) & (labels != rid)):
                        raise ValueError('polygon_overlaps_another_region')
                    labels[target] = rid
                else:
                    labels[target & (labels == rid)] = 0
                decisions[rid] = 'uncertain'
            elif action == 'undo':
                if not c['history']:
                    raise ValueError('nothing_to_undo')
                previous = c['folder'] / ('revision-%04d' % c['history'][-1])
                with Image.open(previous / 'labels.png') as image:
                    labels = np.array(image, dtype=np.uint16)
                record = json.loads((previous / 'selection.private.json').read_text('utf-8'))
                decisions = {r['region_id']: r['decision'] for r in record['regions']}
            else:
                raise ValueError('unknown_edit_action')
            history = list(c['history'])
            if action == 'undo':
                history.pop()
            else:
                history.append(c['revision'])
            draft = dict(c, labels=labels, decisions=decisions, history=history, candidate_selection=None)
            self.save_revision(draft)
            self.current = draft
            self.error = None
            return self.state()

    def start_job(self, data, kind, *, seed=None):
        with self.lock:
            c = self.check(data)
            if kind == 'apply':
                if data.get('confirmed') is not True:
                    raise ValueError('explicit_boundary_and_visibility_confirmation_required')
                if not any(d == 'visible' for d in c['decisions'].values()):
                    raise ValueError('no_explicit_visible_region_selected')
            elif kind == 'detect':
                if not self.detector_available:
                    raise ValueError('detector_unavailable_manual_edit_available')
                if c['regions'] and data.get('replace_draft') is not True:
                    raise ValueError('confirm_replacing_draft_candidates')
            else:
                raise ValueError('unknown_job')
            self.busy, self.error = kind, None
            self.thread = threading.Thread(target=self._job, args=(c, kind, seed), daemon=True)
            self.thread.start()
            return self.state()

    def _job(self, c, kind, seed):
        folder = c['folder'] / (kind + '-' + secrets.token_hex(6))
        try:
            snapshot = capture_runtime_sources()
            folder.mkdir()
            (folder / 'INCOMPLETE.txt').write_text('Incomplete; do not use partial results.', encoding='utf-8')
            if file_hash(c['folder'] / 'canonical.png') != c['identity']['canonical_file_sha256']:
                raise ValueError('canonical_input_changed')
            if kind == 'detect':
                args = [sys.executable, str(Path(__file__).resolve()), '--propose',
                        '--source', str(c['folder'] / 'canonical.png'), '--model', str(self.model),
                        '--registry', str(self.registry), '--output', str(folder)]
                with (folder / 'worker.log').open('w', encoding='utf-8') as log:
                    child = subprocess.run(args, stdout=log, stderr=log, timeout=600,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if child.returncode:
                    raise RuntimeError('automatic_detection_failed_manual_edit_available')
                binding = json.loads((folder / 'proposal.private.json').read_text('utf-8'))
                if binding['source_sha256'] != file_hash(c['folder'] / 'canonical.png'):
                    raise ValueError('proposal_source_mismatch')
                with Image.open(folder / 'proposal.png') as image:
                    mask = np.asarray(image) > 0
                if mask.shape != c['labels'].shape:
                    raise ValueError('proposal_shape_mismatch')
                selection = binding['candidate_selection']
                if (selection.get('proposal_pixel_sha256') != pixels(mask)
                        or selection.get('protection_authorized') is not False):
                    raise ValueError('proposal_review_contract_mismatch')
                labels, count = ndimage.label(mask, np.ones((3, 3), np.uint8))
                if count > 128:
                    raise ValueError('too_many_candidates_manual_edit_available')
                assert_runtime_sources_unchanged(snapshot)
                with self.lock:
                    draft = dict(c, labels=labels.astype(np.uint16), decisions={}, candidate_selection=selection,
                                 history=c['history'] + [c['revision']])
                    self.save_revision(draft)  # Detection never authorizes visibility.
                    self.current = draft
            else:
                review = dict(version='explicit_visibility_review_v1', review_origin='human_confirmed',
                    all_regions_reviewed=True, coordinate_system='upright_native_pixels',
                    RGB_sha256=pixels(c['rgb']), labels_sha256=pixels(c['labels']),
                    regions=[dict(region_id=i, decision=d) for i, d in sorted(c['decisions'].items())])
                json_write(folder / 'review.private.json', dict(review,
                    selection_origin='user_confirmed_runtime_selection', training_GT=False,
                    revision=c['revision'], source_id=c['id']))
                returned, applied, report = apply_reviewed(c['rgb'], c['labels'], review,
                                                           seed=seed, appearance='junction_v23')
                target = folder / 'returned.png'
                save_final_rgb_png(c['folder'] / 'canonical.png', c['identity']['canonical_file_sha256'],
                                   returned, target, 1)
                Image.fromarray(applied.astype(np.uint8) * 255).save(folder / 'applied_mask.png')
                with Image.open(target) as image:
                    actual = np.array(image)
                with Image.open(folder / 'applied_mask.png') as image:
                    saved_mask = np.asarray(image) > 0
                visible = np.isin(c['labels'], [i for i, d in c['decisions'].items() if d == 'visible'])
                if (actual.shape != c['rgb'].shape or pixels(actual) != report['output_RGB_sha256']
                        or not np.array_equal(applied, saved_mask) or np.any(applied & ~visible)
                        or not np.array_equal(actual[~applied], c['rgb'][~applied])):
                    raise RuntimeError('saved_output_verification_failed')
                display_png(actual, c['icc'], folder / 'display.png')
                provenance = assert_runtime_sources_unchanged(snapshot)
                json_write(folder / 'runtime.private.json', provenance)
                json_write(folder / 'result.private.json', dict(report,
                    selection_origin='user_confirmed_runtime_selection', training_GT=False,
                    saved_RGB_verified=True, original_upload_sha256=c['identity']['original_source_sha256']))
                result = dict(folder=folder.name, path=str(folder), applied_regions=report['applied_region_count'],
                              selected_regions=report['selected_region_count'],
                              review_required=report['review_required_count'], saved_RGB_verified=True,
                              privacy_validated=False)
            (folder / 'INCOMPLETE.txt').unlink()
            if kind == 'apply':
                with self.lock:
                    c['result'] = result
        except Exception as exc:
            folder.mkdir(exist_ok=True)
            (folder / 'error.private.txt').write_text(traceback.format_exc(), encoding='utf-8')
            with self.lock:
                self.error = str(exc)
                # A failed run cannot leave a previous result looking current.
                c['result'] = None
        finally:
            with self.lock:
                self.busy = None

    def asset(self, parts):
        with self.lock:
            c = self.current
            if not c or len(parts) < 3 or parts[0] != 'photo' or parts[1] != c['id']:
                raise ValueError('photo_not_current')
            if parts[2:] == ['original.png']:
                return (c['folder'] / 'display.png').read_bytes()
            if parts[2:] == ['overlay.png']:
                return (c['folder'] / ('revision-%04d' % c['revision']) / 'overlay.png').read_bytes()
            if len(parts) == 4 and parts[2] == 'result' and c['result']:
                allowed = {'returned.png', 'display.png', 'applied_mask.png'}
                if parts[3] in allowed:
                    return (c['folder'] / c['result']['folder'] / parts[3]).read_bytes()
            raise ValueError('asset_not_available')


def make_server(session):
    prefix = '/s/' + secrets.token_urlsafe(24) + '/'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; "
                             "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                             "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def route(self):
            if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                raise ValueError('invalid_host')
            path = urlsplit(self.path).path
            if not path.startswith(prefix):
                raise ValueError('invalid_session')
            return path[len(prefix):]

        def do_GET(self):
            try:
                route = self.route()
                if route == 'api/state':
                    self.send(200, json.dumps(session.state(), ensure_ascii=False).encode('utf-8'))
                elif route in ('', 'app.js', 'style.css'):
                    name, mime = {'': ('index.html', 'text/html; charset=utf-8'),
                                  'app.js': ('app.js', 'text/javascript; charset=utf-8'),
                                  'style.css': ('style.css', 'text/css; charset=utf-8')}[route]
                    self.send(200, (ASSETS / name).read_bytes(), mime)
                else:
                    self.send(200, session.asset(route.split('/')), 'image/png')
            except (ValueError, FileNotFoundError) as exc:
                self.send(404, json.dumps(dict(error=str(exc))).encode())

        def do_POST(self):
            try:
                route = self.route()
                if self.headers.get('Origin') != 'http://127.0.0.1:' + str(self.server.server_port):
                    raise ValueError('invalid_origin')
                limit = MAX_UPLOAD if route == 'api/upload' else 256 * 1024
                length = int(self.headers.get('Content-Length', '-1'))
                if length < 0 or length > limit or self.headers.get('Transfer-Encoding'):
                    raise ValueError('invalid_request_length')
                expected = 'application/octet-stream' if route == 'api/upload' else 'application/json'
                if self.headers.get_content_type() != expected:
                    raise ValueError('invalid_content_type')
                self.connection.settimeout(30)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('incomplete_request')
                if route == 'api/upload':
                    from urllib.parse import unquote
                    result = session.upload(raw, unquote(self.headers.get('X-File-Name', 'photo')))
                else:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError('object_required')
                    if route == 'api/edit':
                        result = session.edit(data)
                    elif route in ('api/detect', 'api/apply'):
                        result = session.start_job(data, route.split('/')[-1])
                    elif route == 'api/stop':
                        with session.lock:
                            if session.busy:
                                raise ValueError('job_running_please_wait')
                            threading.Thread(target=self.server.shutdown, daemon=True).start()
                        result = dict(stopped=True)
                    else:
                        raise ValueError('unknown_request')
                self.send(200, json.dumps(result, ensure_ascii=False).encode('utf-8'))
            except Exception as exc:
                self.send(400, json.dumps(dict(error=str(exc)), ensure_ascii=False).encode('utf-8'))

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.url = 'http://127.0.0.1:' + str(server.server_port) + prefix
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--propose', action='store_true')
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.propose:
        propose(args.source, args.model, args.registry, args.output)
        return
    session = Session(args.output, args.model, args.registry)
    server = make_server(session)
    if args.ready_file:
        json_write(args.ready_file, dict(url=server.url, output=str(session.root)))
    print(json.dumps(dict(url=server.url, output=str(session.root))), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
