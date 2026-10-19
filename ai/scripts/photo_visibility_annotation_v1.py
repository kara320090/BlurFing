"""Human ridge visibility on immutable, hash-bound anatomical pad masks.

Components are proposals, not anatomical truth. Human reviewers may merge them
or mark geometry uncertain. No prediction prelabels a human annotation.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import threading
import uuid
import zipfile

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

from pad_refinement_data_contract_v2 import checked_bytes, native_shape, read_mask, validate_source_id
from photo_pad_annotation_v1 import digest, write_json, make_server

VERSION = 'photo_visibility_annotation_v1'
POLICY = 'raw_native_ridge_visibility_three_way_v1'
ASSETS = Path(__file__).resolve().parent.parent / 'app/visibility_annotation'
LABELS = {'visible', 'not_observed', 'uncertain'}
REASONS = {'blur', 'small', 'glare', 'occlusion', 'geometry', 'non_palmar', 'other'}
FORWARD = {2:Image.Transpose.FLIP_LEFT_RIGHT, 3:Image.Transpose.ROTATE_180,
           4:Image.Transpose.FLIP_TOP_BOTTOM, 5:Image.Transpose.TRANSPOSE,
           6:Image.Transpose.ROTATE_270, 7:Image.Transpose.TRANSVERSE, 8:Image.Transpose.ROTATE_90}


def component_map(mask):
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    proposals = []
    for number, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None: continue
        yy, xx = sl
        proposals.append(dict(component_id=number, bbox_xyxy=[xx.start, yy.start, xx.stop, yy.stop],
                              pixels=int(np.count_nonzero(labels[sl] == number))))
    if not 1 <= count <= 128: raise ValueError('review_component_count_out_of_range')
    return labels, proposals


class Project:
    def __init__(self, roster, state):
        self.roster_path = Path(roster).resolve()
        raw = self.roster_path.read_bytes()
        if len(raw) > 4 * 1024**2: raise ValueError('roster_too_large')
        manifest = json.loads(raw.decode('utf-8-sig'))
        if manifest.get('version') != 'visibility_roster_v1' or manifest.get('data_role') not in {'diagnostic_development', 'synthetic_fixture'}:
            raise ValueError('visibility_roster_contract')
        sources = manifest.get('sources')
        if not isinstance(sources, list) or not 1 <= len(sources) <= 128: raise ValueError('source_count')
        self.sources = {}; seen = set(); self.cache = {}
        for row in sources:
            sid = row['source_id']; validate_source_id(sid)
            if sid in self.sources or row['source_sha256'] in seen: raise ValueError('duplicate_source')
            if any(not Path(row[key]).is_absolute() for key in ['source_path', 'mask_path']): raise ValueError('absolute_path_required')
            self.sources[sid] = dict(row); seen.add(row['source_sha256'])
            rgb, mask = self.arrays(sid)
            _, proposals = component_map(mask)
            self.sources[sid].update(display_width=rgb.shape[1], display_height=rgb.shape[0], proposals=proposals)
        self.synthetic = manifest['data_role'] == 'synthetic_fixture'
        self.state = Path(state).resolve()
        if Path(state).is_symlink() or any(self.state == Path(r[k]).parent for r in sources for k in ['source_path', 'mask_path']):
            raise ValueError('separate_state_required')
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.header = dict(version=VERSION, policy=POLICY, roster_sha256=digest(raw), data_role=manifest['data_role'])
        header = self.state/'project.json'
        if header.exists() and json.loads(header.read_text(encoding='utf-8')) != self.header: raise ValueError('project_roster_changed')
        if not header.exists(): write_json(header, self.header)

    @contextmanager
    def writing(self):
        """Prevent two launcher processes from publishing conflicting revisions."""
        with self.lock, (self.state/'review.lock').open('a+b') as stream:
            if stream.tell() == 0: stream.write(b'0'); stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                try: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc: raise ValueError('another_review_write_in_progress') from exc
                try: yield
                finally: stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc: raise ValueError('another_review_write_in_progress') from exc
                try: yield
                finally: fcntl.flock(stream, fcntl.LOCK_UN)

    def arrays(self, sid):
        if sid not in self.sources: raise ValueError('unknown_source')
        row = self.sources[sid]
        data = checked_bytes(row['source_path'], row['source_sha256'])
        checked_bytes(row['mask_path'], row['mask_sha256'])
        if sid in self.cache: return self.cache[sid]
        with Image.open(io.BytesIO(data)) as im:
            shape = (im.height, im.width)
            native_shape(dict(height=im.height, width=im.width, coordinate_system='encoded_original_pixels'))
            orientation = im.getexif().get(274, 1)
            frames = getattr(im, 'n_frames', 1)
            if im.mode not in {'RGB', 'L'}: raise ValueError('RGB_or_L_image_required')
            if frames != row.get('frame_count', 1) or row.get('frame_used', 0) != 0:
                raise ValueError('source_frame_contract_changed')
            if frames > 1 and im.format not in {'JPEG', 'MPO'}:
                raise ValueError('only_hash_bound_JPEG_base_frame_supported')
            im.seek(0)  # Preserve the exact base-frame pixels used by the original GT.
            if type(orientation) is not int or orientation not in range(1, 9) or orientation != row['exif_orientation']:
                raise ValueError('source_orientation_changed')
            if shape != (row['height'], row['width']): raise ValueError('source_shape_changed')
            encoded = np.asarray(im.convert('RGB'))
            rgb = np.asarray(ImageOps.exif_transpose(im).convert('RGB')).copy()
        if digest(encoded.tobytes()) != row['encoded_RGB_sha256'] or digest(rgb.tobytes()) != row['upright_RGB_sha256']:
            raise ValueError('source_decoded_pixels_changed')
        mask = Image.fromarray(read_mask(row['mask_path'], row['mask_sha256'], shape).astype(np.uint8)*255)
        if orientation in FORWARD: mask = mask.transpose(FORWARD[orientation])
        mask = np.asarray(mask) > 0
        if rgb.shape[:2] != mask.shape: raise ValueError('upright_mask_shape_mismatch')
        rgb.flags.writeable = False; mask.flags.writeable = False
        if len(self.cache) >= 1: self.cache.clear()
        self.cache[sid] = (rgb, mask)
        return rgb, mask

    def image(self, sid):
        with self.lock:
            overlay = sid.endswith('-overlay')
            if overlay: sid = sid[:-8]
            rgb, mask = self.arrays(sid)
            if overlay:
                rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
                rgba[mask] = [28, 235, 164, 70]
                im = Image.fromarray(rgba)
            else: im = Image.fromarray(rgb)
            out = io.BytesIO(); im.save(out, format='PNG'); return out.getvalue()

    def current(self, sid):
        if sid not in self.sources: raise ValueError('unknown_source')
        folder = self.state/'annotations'/sid
        latest = folder/'latest.json'
        if latest.exists():
            pointer = json.loads(latest.read_text(encoding='utf-8'))
            rev = pointer['revision']
            if type(rev) is not int or rev < 1: raise ValueError('invalid_revision_pointer')
            record = json.loads(checked_bytes(folder/f'rev-{rev:06d}.json', pointer['sha256']).decode('utf-8'))
            row = self.sources[sid]
            if any(record.get(k) != v for k,v in self.header.items()) or any(record.get(k) != row[k] for k in ['source_sha256','mask_sha256','upright_RGB_sha256']):
                raise ValueError('review_identity_changed')
            return record
        return dict(source_id=sid, revision=0, status='draft', human_GT=False,
                    groups=[dict(component_ids=[p['component_id']], label=None, reasons=[], evidence_box=None, note='')
                            for p in self.sources[sid]['proposals']])

    def overview(self):
        with self.lock:
            return dict(**self.header, sources=[dict(source_id=sid, width=r['display_width'], height=r['display_height'],
                        proposals=r['proposals'], split_role=r['split_role'], acquisition_group=r.get('acquisition_group'),
                        status=self.current(sid)['status']) for sid, r in self.sources.items()],
                        automatic_predictions_hidden=True, independent_validation=False)

    def validated_groups(self, sid, groups, reviewed):
        rgb, mask = self.arrays(sid); labels, proposals = component_map(mask)
        ids = {p['component_id'] for p in proposals}
        if not isinstance(groups, list) or not 1 <= len(groups) <= len(ids): raise ValueError('invalid_groups')
        used = []; result = []
        for group in groups:
            if not isinstance(group, dict): raise ValueError('invalid_group')
            members = group.get('component_ids')
            if not isinstance(members, list) or not members or any(type(i) is not int or i not in ids for i in members): raise ValueError('invalid_component_ids')
            used.extend(members)
            label = group.get('label')
            if label not in LABELS and not (label is None and not reviewed): raise ValueError('invalid_visibility_label')
            reasons = group.get('reasons', [])
            if not isinstance(reasons, list) or any(r not in REASONS for r in reasons) or len(reasons) != len(set(reasons)): raise ValueError('invalid_reasons')
            if reviewed and label == 'uncertain' and not reasons: raise ValueError('uncertain_reason_required')
            box = group.get('evidence_box')
            if box is not None:
                if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box): raise ValueError('integer_evidence_box_required')
                x0, y0, x1, y1 = box
                if not 0 <= x0 < x1 <= mask.shape[1] or not 0 <= y0 < y1 <= mask.shape[0]: raise ValueError('evidence_outside_image')
                if not np.isin(labels[y0:y1, x0:x1], members).all(): raise ValueError('evidence_must_be_inside_selected_pad')
                if min(x1-x0, y1-y0) < 8: raise ValueError('evidence_box_too_small')
                if label != 'visible': raise ValueError('evidence_only_for_visible')
            if reviewed and label == 'visible' and box is None: raise ValueError('visible_requires_evidence_box')
            note = group.get('note', '')
            if not isinstance(note, str) or len(note) > 1000: raise ValueError('invalid_note')
            if reviewed and 'other' in reasons and not note.strip(): raise ValueError('other_requires_note')
            result.append(dict(component_ids=sorted(members), label=label, reasons=reasons, evidence_box=box, note=note))
        if sorted(used) != sorted(ids): raise ValueError('every_component_exactly_once_required')
        return sorted(result, key=lambda g: g['component_ids'][0])

    def save(self, sid, payload):
        with self.writing():
            previous = self.current(sid)
            if type(payload.get('base_revision')) is not int or payload['base_revision'] != previous['revision']:
                raise ValueError('annotation_revision_conflict')
            status = payload.get('status')
            if status not in {'draft', 'reviewed'}: raise ValueError('invalid_review_status')
            reviewed = status == 'reviewed'
            if reviewed and (payload.get('attest_original_reviewed') is not True or payload.get('attest_grouping_reviewed') is not True):
                raise ValueError('explicit_human_attestation_required')
            groups = self.validated_groups(sid, payload.get('groups'), reviewed)
            folder = self.state/'annotations'/sid; folder.mkdir(parents=True, exist_ok=True)
            revision = previous['revision']+1
            while (folder/f'rev-{revision:06d}.json').exists(): revision += 1
            row = self.sources[sid]
            value = dict(**self.header, source_id=sid, revision=revision, status=status, human_GT=reviewed and not self.synthetic,
                coordinates='upright_native_pixels_xyxy_exclusive', source_sha256=row['source_sha256'],
                mask_sha256=row['mask_sha256'], upright_RGB_sha256=row['upright_RGB_sha256'],
                split_role=row['split_role'], acquisition_group=row.get('acquisition_group'),
                groups=groups, attestation=reviewed, predictions_shown=False,
                updated_utc=datetime.now(timezone.utc).isoformat())
            path=folder/f'rev-{revision:06d}.json'; write_json(path, value)
            write_json(folder/'latest.json', dict(revision=revision, sha256=digest(path.read_bytes())))
            return value

    def export(self):
        with self.writing():
            records = []
            for sid in self.sources:
                row = self.current(sid)
                if row['status'] != 'reviewed': continue
                self.validated_groups(sid, row['groups'], True)
                records.append(row)
            if not records: raise ValueError('no_reviewed_records')
            folder = self.state/'exports'; folder.mkdir(exist_ok=True)
            name = 'BlurFing_visibility_GT_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]+'.zip'
            path = folder/name
            with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('visibility_labels.json', json.dumps(dict(**self.header, records=records,
                    originals_included=False, mask_files_included=False, independent_validation=False), ensure_ascii=False, indent=2))
            checksum=digest(path.read_bytes()); (folder/(name+'.sha256')).write_text(checksum+'  '+name+'\n', encoding='ascii')
            return dict(filename=name, sha256=checksum, reviewed=len(records), unreviewed=len(self.sources)-len(records))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roster', type=Path, required=True); parser.add_argument('--state', type=Path, required=True)
    args=parser.parse_args(); project=Project(args.roster, args.state)
    server,url=make_server(project, assets=ASSETS, export_prefix='BlurFing_visibility_GT_')
    write_json(project.state/'session.private.json', dict(url=url, pid=os.getpid(), version=VERSION,
        roster_sha256=project.header['roster_sha256'], script_sha256=digest(Path(__file__).read_bytes())))
    print(json.dumps(dict(status='ready', url=url)), flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__': main()
