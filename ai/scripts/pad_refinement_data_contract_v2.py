"""Bounded, hash-bound refinement assets; no model/GT-guided crop policy."""
import ast
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from photo_resize_safety_v1 import validate_resize

VERSION = 'pad_refinement_data_v2'
COORDINATES = 'encoded_original_pixels'
SIZE = 256
PADDING = .35
MAX_ASSET_BYTES = 128 * 1024**2
MAX_CROP_BYTES = 2 * 1024**2
MAX_HEADER_BYTES = 2048
RESERVED_NAMES = {'CON','PRN','AUX','NUL'} | {f'{p}{i}' for p in ['COM','LPT'] for i in range(1,10)}


def validate_source_id(sid):
    if (not isinstance(sid, str) or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*', sid) is None or
            sid.upper() in RESERVED_NAMES):
        raise ValueError('invalid_source_id')


def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError('invalid_or_oversized_asset')
    value, total = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while True:
            chunk = stream.read(min(1024**2, MAX_ASSET_BYTES + 1 - total))
            if not chunk:break
            total += len(chunk)
            if total > MAX_ASSET_BYTES:raise ValueError('invalid_or_oversized_asset')
            value.update(chunk)
    return value.hexdigest()


def checked_bytes(path, expected, limit=MAX_ASSET_BYTES):
    path = Path(path)
    if not isinstance(expected, str) or re.fullmatch('[0-9a-f]{64}', expected) is None:
        raise ValueError('asset_hash_required; regenerate a fresh V2 dataset')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('invalid_or_oversized_asset')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('asset_hash_mismatch')
    return data


def native_shape(source):
    h, w = source.get('height'), source.get('width')
    if type(h) is not int or type(w) is not int:
        raise ValueError('native_shape_contract')
    validate_resize(h, w, 1.)
    if source.get('coordinate_system') != COORDINATES:
        raise ValueError('native_coordinate_contract')
    return h, w


def read_mask(path, expected, shape):
    data = checked_bytes(path, expected)
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.mode != 'L' or image.size != shape[::-1]:
            raise ValueError('native_mask_shape_or_dtype_mismatch')
        mask = np.asarray(image).copy()
    if not np.isin(mask, [0, 255]).all():
        raise ValueError('native_mask_nonbinary')
    return mask == 255


def read_body(source):
    return read_mask(source['body_path'], source.get('body_sha256'), native_shape(source))


def read_source_rgb(path, expected):
    """Check the encoded raster before decode; never transpose annotation axes."""
    data = checked_bytes(path, expected)
    with Image.open(io.BytesIO(data)) as image:
        validate_resize(image.height, image.width, 1.)
        if image.mode not in ['RGB', 'L'] or image.getexif().get(274, 1) not in range(1, 9):
            raise ValueError('source_image_contract_mismatch')
        return np.asarray(image.convert('RGB')).copy()


def read_gt(source):
    shape = native_shape(source)
    folder = Path(source['GT_folder'])
    metadata = json.loads(checked_bytes(folder/'source.json', source.get('GT_metadata_sha256')))
    if (metadata.get('human_annotation') is not True or
            metadata.get('annotation_type') != 'human_reviewed_fingerprint_pad' or
            metadata.get('coordinate_system') != COORDINATES or
            metadata.get('source_sha256') != source['source_sha256'] or
            (metadata.get('image_height'), metadata.get('image_width')) != shape or
            metadata.get('exif_orientation') != source['source_exif_orientation'] or
            metadata.get('mask_sha256') != source.get('GT_mask_sha256') or
            metadata.get('annotation_status') not in [None, 'valid_positive', 'positive', 'annotated', 'human_reviewed']):
        raise ValueError('training_annotation_contract_mismatch')
    mask = read_mask(folder/'ground_truth_mask.png', source['GT_mask_sha256'], shape)
    if not mask.any():
        raise ValueError('positive_training_GT_required')
    return mask


def source_record(source, sid, semantics, rgb, GT_folder=None):
    validate_source_id(sid)
    source, semantics = Path(source), Path(semantics)
    with Image.open(source) as image:
        orientation = image.getexif().get(274, 1)
    row = dict(source_id=sid, source_path=str(source.resolve()), source_sha256=digest(source),
        source_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        source_exif_orientation=orientation, coordinate_system=COORDINATES,
        height=rgb.shape[0], width=rgb.shape[1], body_path=str((semantics/'body.png').resolve()),
        body_sha256=digest(semantics/'body.png'), tip_path=str((semantics/'tip.png').resolve()),
        tip_sha256=digest(semantics/'tip.png'), semantics_path=str((semantics/'semantics.json').resolve()),
        semantics_sha256=digest(semantics/'semantics.json'))
    if GT_folder is not None:
        folder = Path(GT_folder)
        row.update(GT_folder=str(folder.resolve()), GT_metadata_sha256=digest(folder/'source.json'),
                   GT_mask_sha256=digest(folder/'ground_truth_mask.png'))
    return row


def verify_source(source, purpose):
    if not isinstance(source, dict) or purpose not in ['training', 'inference']:
        raise ValueError('source_contract')
    shape = native_shape(source)
    sid = source.get('source_id')
    validate_source_id(sid)
    data = checked_bytes(source['source_path'], source.get('source_sha256'))
    with Image.open(io.BytesIO(data)) as image:
        if (image.mode not in ['RGB', 'L'] or image.size != shape[::-1] or
                type(source.get('source_exif_orientation')) is not int or
                source['source_exif_orientation'] not in range(1, 9) or
                image.getexif().get(274, 1) != source['source_exif_orientation']):
            raise ValueError('source_image_contract_mismatch')
        rgb = np.asarray(image.convert('RGB')).copy()
    if hashlib.sha256(rgb.tobytes()).hexdigest() != source.get('source_RGB_sha256'):
        raise ValueError('decoded_source_hash_mismatch')
    semantic = json.loads(checked_bytes(source['semantics_path'], source.get('semantics_sha256')))
    if (semantic.get('source_sha256') != source['source_sha256'] or
            semantic.get('coordinate_system') != COORDINATES or
            semantic.get('body_sha256') != source['body_sha256'] or
            semantic.get('tip_sha256') != source['tip_sha256'] or
            semantic.get('body_classes') != [1,2] or semantic.get('tip_class') != 2 or
            semantic.get('minimum_votes') != 2):
        raise ValueError('source_semantics_binding_mismatch')
    if any(k in semantic and (type(semantic[k]) is not int or semantic[k] != v)
           for k, v in [('image_height', shape[0]), ('image_width', shape[1])]):
        raise ValueError('semantic_native_shape_mismatch')
    body = read_body(source)
    tip = read_mask(source['tip_path'], source['tip_sha256'], shape)
    if np.any(tip & ~body):
        raise ValueError('tip_outside_body')
    if purpose == 'training':
        read_gt(source)
    elif any(key.startswith('GT') for key in source):
        raise ValueError('GT_fields_forbidden_in_inference')


def crop_geometry(record, source):
    box, g = record.get('bbox'), record.get('geometry')
    h, w = native_shape(source)
    if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
        raise ValueError('crop_bbox_contract')
    a, b, c, d = box
    if not (0 <= a < c <= w and 0 <= b < d <= h):
        raise ValueError('crop_bbox_outside_source')
    width, height = c-a, d-b
    ratio = SIZE/max(height, width)
    sw, sh = max(1, round(width*ratio)), max(1, round(height*ratio))
    expected = dict(width=width, height=height, scaled_width=sw, scaled_height=sh,
                    left=(SIZE-sw)//2, top=(SIZE-sh)//2)
    if not isinstance(g, dict) or set(g) != set(expected) or any(type(g[k]) is not int or g[k] != v for k, v in expected.items()):
        raise ValueError('crop_letterbox_geometry_mismatch')
    if record.get('source_id') != source['source_id'] or record.get('source_sha256') != source['source_sha256']:
        raise ValueError('crop_source_binding_mismatch')


def crop_path(root, name):
    if not isinstance(name, str) or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*\\.npz', name) is None:
        raise ValueError('crop_relative_basename_required')
    if name.split('.')[0].upper() in RESERVED_NAMES:
        raise ValueError('reserved_crop_name')
    root = Path(root).resolve()
    path = root/name
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError('crop_path_outside_dataset')
    return path


def load_crop(root, record, source, purpose):
    crop_geometry(record, source)
    data = checked_bytes(crop_path(root, record.get('path')), record.get('file_sha256'), MAX_CROP_BYTES)
    expected = {'rgb.npy':(SIZE,SIZE,3), 'coarse.npy':(SIZE,SIZE), 'label.npy':(SIZE,SIZE)}
    arrays = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) != 3 or {m.filename for m in members} != set(expected):
                raise ValueError('crop_NPZ_members_mismatch')
            for member in members:
                shape = expected[member.filename]
                count = int(np.prod(shape))
                if (member.flag_bits & 1 or member.file_size > count+MAX_HEADER_BYTES+12 or
                        member.compress_type not in [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED]):
                    raise ValueError('crop_NPY_resource_limit')
                with archive.open(member) as stream:
                    payload = stream.read(count+MAX_HEADER_BYTES+12+1)
                if payload[:6] != b'\x93NUMPY' or payload[6:8] not in [b'\x01\x00', b'\x02\x00']:
                    raise ValueError('crop_NPY_format_mismatch')
                prefix = 10 if payload[6] == 1 else 12
                length = int.from_bytes(payload[8:prefix], 'little')
                if length > MAX_HEADER_BYTES or prefix+length+count != len(payload):
                    raise ValueError('crop_NPY_payload_mismatch')
                header = ast.literal_eval(payload[prefix:prefix+length].decode('latin1').strip())
                if (not isinstance(header, dict) or header != dict(descr='|u1', fortran_order=False, shape=shape) or
                        type(header.get('fortran_order')) is not bool or
                        type(header.get('shape')) is not tuple or any(type(d) is not int for d in header['shape'])):
                    raise ValueError('crop_array_shape_or_dtype_mismatch')
                arrays[member.filename[:-4]] = np.frombuffer(payload, np.uint8, offset=prefix+length).reshape(shape).copy()
    except (zipfile.BadZipFile, SyntaxError, UnicodeError, EOFError, KeyError, RuntimeError, NotImplementedError) as exc:
        raise ValueError('invalid_crop_archive') from exc
    if not np.isin(arrays['coarse'], [0,1]).all() or not np.isin(arrays['label'], [0,1]).all():
        raise ValueError('crop_mask_nonbinary')
    if purpose == 'inference' and arrays['label'].any():
        raise ValueError('GT_label_forbidden_in_inference')
    g = record['geometry']
    padding = np.ones((SIZE,SIZE),bool)
    padding[g['top']:g['top']+g['scaled_height'],g['left']:g['left']+g['scaled_width']] = False
    if any(array[padding].any() for array in arrays.values()):
        raise ValueError('nonzero_letterbox_padding')
    return arrays


def check_dataset(root, manifest, purpose):
    if (not isinstance(manifest, dict) or manifest.get('version') != VERSION or manifest.get('purpose') != purpose or
            purpose not in ['training','inference'] or manifest.get('coordinate_system') != COORDINATES or
            manifest.get('input_size') != SIZE or manifest.get('context_padding') != PADDING or
            manifest.get('crop_policy') != 'coarse_guided_v1' or
            manifest.get('GT_present') is not (purpose == 'training')):
        raise ValueError('refinement_V2_dataset_required; regenerate without overwriting V1')
    if (not isinstance(manifest.get('sources'), list) or not manifest['sources'] or
            not isinstance(manifest.get('crops'), list)):
        raise ValueError('source_and_crop_lists_required')
    sources, hashes, names, ids = {}, set(), set(), set()
    for source in manifest['sources']:
        if not isinstance(source, dict):raise ValueError('source_contract')
        validate_source_id(source.get('source_id'))
        folded = source['source_id'].casefold()
        if folded in ids:raise ValueError('duplicate_source_identity')
        ids.add(folded)
    for source in manifest['sources']:
        verify_source(source, purpose)
        if source['source_id'] in sources or source['source_sha256'] in hashes:
            raise ValueError('duplicate_source_identity')
        sources[source['source_id']] = source
        hashes.add(source['source_sha256'])
    if not sources:
        raise ValueError('empty_source_dataset')
    counts = dict.fromkeys(sources, 0)
    for crop in manifest['crops']:
        if not isinstance(crop, dict) or not isinstance(crop.get('path'), str):
            raise ValueError('crop_record_contract')
        if crop.get('source_id') not in sources or crop['path'].casefold() in names:
            raise ValueError('crop_owner_or_path_duplicate')
        names.add(crop['path'].casefold())
        load_crop(root, crop, sources[crop['source_id']], purpose)
        counts[crop['source_id']] += 1
    for sid, source in sources.items():
        if 'crop_count' in source and (type(source['crop_count']) is not int or source['crop_count'] != counts[sid]):
            raise ValueError('source_crop_count_mismatch')
    return sources
