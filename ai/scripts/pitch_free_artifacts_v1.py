"""Private, same-coordinate diagnostics for desktop redaction experiments."""
import io
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageCms
from final_png_color_metadata_v1 import save_final_rgb_png, _source_metadata


def candidate_application(candidate, final):
    """Measure model-mask agreement, never human-GT recall or protection success."""
    if (candidate.dtype != np.bool_ or final.dtype != np.bool_ or
            candidate.ndim != 2 or candidate.shape != final.shape):
        raise ValueError('artifact_mask_contract')
    total = int(candidate.sum())
    covered = int((candidate & final).sum())
    return dict(candidate_pixels=total, applied_candidate_pixels=covered,
        unapplied_candidate_pixels=total-covered,
        applied_outside_candidate_pixels=int((final & ~candidate).sum()),
        candidate_applied_fraction=covered/total if total else None,
        candidate_fully_applied=bool(total and covered == total),
        GT_coverage_measured=False, complete_fingerprint_protection_verified=False)


def save_artifacts(source, identity, rgb, candidate, final, returned, output, *, stages=None):
    output = Path(output)
    shape = rgb.shape[:2]
    if any(m.dtype != np.bool_ or m.shape != shape for m in (candidate, final)):
        raise ValueError('artifact_mask_contract')
    if returned.shape != rgb.shape or not np.array_equal(returned[~final], rgb[~final]) or np.any(returned[final]):
        raise ValueError('artifact_protected_RGB_contract')
    application = candidate_application(candidate, final)
    orientation = identity['source_exif_orientation']
    sha = identity['original_source_sha256']
    save_final_rgb_png(source, sha, rgb, output/'original.png', orientation)
    save_final_rgb_png(source, sha, returned, output/'protected.png', orientation)
    exif = Image.Exif(); exif[274] = orientation
    for name, mask in dict(candidate_mask=candidate, refined_mask=final, **(stages or {})).items():
        if not name.replace('_', '').isalnum() or mask.shape != shape or mask.dtype != np.bool_:
            raise ValueError('artifact_stage_contract')
        with (output/(name+'.png')).open('xb') as stream:
            Image.fromarray(mask.astype(np.uint8)*255).save(stream, format='PNG', exif=exif)
    _, _, _, icc = _source_metadata(source, sha)
    canvas = Image.new('RGB', (1440, 410), '#eeeeee')
    draw = ImageDraw.Draw(canvas)
    for i, (label, array) in enumerate([('Original', rgb), ('Candidate proposal (not applied mask)', candidate), ('Actually applied mask', final), ('Protected - REVIEW REQUIRED', returned)]):
        im = Image.fromarray(array.astype(np.uint8)*255 if array.ndim == 2 else array)
        im.info['exif'] = exif.tobytes(); im = ImageOps.exif_transpose(im)
        im.thumbnail((350, 350))
        if array.ndim == 3 and icc is not None:
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
        canvas.paste(im, (i*360+(360-im.width)//2, 28))
        draw.text((i*360+6, 8), label, fill='#111111')
    fraction = application['candidate_applied_fraction']
    coverage = f'{fraction:.1%}' if fraction is not None else 'N/A (no candidate)'
    draw.text((6, 389), f'Candidate area applied: {coverage}. This is not GT coverage. Missed fingerprints and extra skin remain possible.', fill='#880000')
    with (output/'comparison.png').open('xb') as stream:
        canvas.save(stream, format='PNG')
    return dict(protected_path=str((output/'protected.png').resolve()),
        comparison_path=str((output/'comparison.png').resolve()),
        diagnostic_coordinates='encoded_original_pixels_with_original_EXIF', review_required=True,
        candidate_application=application)
