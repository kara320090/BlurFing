"""Opt-in v2 body-associated axis width experiment; default GUI remains v2 adapter."""
import json
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
import photo_region_pipeline_v1 as shared
from contactless_finger_width_body_v1 import estimate_finger_width_body

VERSION = 'photo_region_pipeline_v2_body_width_experimental'


def associated_body(body, pad, association, estimator_regions):
    if (not isinstance(body, np.ndarray) or body.dtype != np.bool_ or body.ndim != 2 or
            not isinstance(pad, np.ndarray) or pad.dtype != np.bool_ or
            body.shape != pad.shape or not pad.any() or np.any(pad & ~body)):
        raise ValueError('body_pad_association_contract_mismatch')
    labels, _ = ndimage.label(body)
    identities = np.unique(labels[pad])
    if len(identities) != 1 or identities[0] == 0:
        raise ValueError('native_body_parent_ambiguous')
    native = labels == identities[0]
    parents = []
    for index, parent in enumerate(estimator_regions, 1):
        mask = parent.get('mask')
        if parent.get('reject_reason') is not None or mask is None:continue
        if mask.shape != body.shape or mask.dtype != np.bool_:
            raise ValueError('estimator_parent_mask_contract_mismatch')
        if np.any(mask & native):parents.append(index)
    if parents != [association['estimator_region_index']]:
        raise ValueError('native_body_has_multiple_or_unmatched_distal_parents')
    return native, dict(native_body_component=int(identities[0]),
                        estimator_region_index=parents[0], native_body_pixels=int(native.sum()),
                        association_policy='one native connected body and one distal estimator parent; no cleanup')


def render_body_region(rgb, artifact, axis_yx, association, estimator_regions):
    pad = artifact['regions'][0]['roi'].binary_mask > 0
    native, context = associated_body(artifact['body'], pad, association, estimator_regions)
    height, width = artifact['working_shape']
    working = cv2.resize(shared.orient(native.astype(np.uint8), artifact['exif_orientation']),
                         (width, height), interpolation=cv2.INTER_NEAREST) > 0
    padding = artifact['regions'][0]['padding']
    working = np.pad(working, ((0,padding['bottom']), (0,padding['right'])), constant_values=False)
    def observe(image, box, axis):
        return estimate_finger_width_body(image, box, axis, working, image_shape=(height,width))
    returned, details = shared.render_region(rgb, artifact, axis_yx, _width_observer=observe)
    return returned, details | dict(body_width_association=context,
                                    body_mask_working_shape=list(working.shape))


def protect_photo_regions(source, output=None, *, photo_semantics=None, detect_only=False, strength=.5):
    return shared.protect_photo_regions(source, output, photo_semantics=photo_semantics,
        detect_only=detect_only, strength=strength, _region_renderer=render_body_region,
        _pipeline_version=VERSION)


if __name__ == '__main__':
    from protect_fingerprint import cli_progress_to_stderr, JSONArgumentParser
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--photo-semantics', type=Path)
    parser.add_argument('--detect-only', action='store_true')
    parser.add_argument('--strength', type=float, default=.5)
    args = parser.parse_args()
    try:
        with cli_progress_to_stderr():
            _, report = protect_photo_regions(args.input, args.output,
                photo_semantics=args.photo_semantics, detect_only=args.detect_only, strength=args.strength)
        print(json.dumps(report, indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error', error=type(error).__name__)))
        raise SystemExit(1)
