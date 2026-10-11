"""Conservative appearance-only v4 natural v2 variant; human review is still required.

Reuses frozen detection, independent ridge generation, photometric reference,
structure gate and fail-closed return logic. Overrides are scoped and restored
even on exceptions. Invoke as the Linux entry point with --input; /tmp only.
No original ridge highpass is blended back into the synthetic fingerprint.
"""

import sys

import threading

sys.dont_write_bytecode = True

_LOCK = threading.RLock()

def transform_fingerprint_photo(image, strength=.5, *, return_details=True):
    import cv2
    import numpy as np
    import whole_pad_skin_relief as renderer
    import transform_automatic_fingerprint_poc_v4 as frozen
    from organic_ridge_profile import smooth_random

    with _LOCK:
        old_profile = renderer.render_photographic_profile
        old_relief = renderer.independent_skin_relief
        old_taper = renderer.synthetic_boundary_taper
        old_render = frozen.render_whole_pad_candidate

        def profile(field, mask, pitch, seed):
            value, meta = old_profile(field, mask, pitch, seed)
            rng = np.random.default_rng(seed ^ 0x4E4154)
            yy, xx = np.indices(value.shape, dtype=np.float32)
            # Smooth bounded displacement: at most 0.04 pitch per axis.
            dx = smooth_random(value.shape, 9, max(1., pitch * 1.5), rng)
            dy = smooth_random(value.shape, 9, max(1., pitch * 1.5), rng)
            value = cv2.remap(value, xx + dx * pitch * .016,
                              yy + dy * pitch * .016, cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REFLECT_101)
            value = cv2.GaussianBlur(value, (0, 0), max(.25, pitch * .04))
            local_gain = np.clip(1 + .14 * smooth_random(
                value.shape, 8, max(1., pitch * 2), rng), .7, 1.2)
            value *= .85 * local_gain
            # Do not renormalize: keep the deliberate visibility reduction.
            meta = dict(meta, natural_variant=dict(
                displacement_max_pitch_per_axis=.04, blur_sigma_pitch=.04,
                global_gain=.85, local_gain_range=[.7, 1.2],
                original_highpass_transferred=False))
            return value, meta

        def render(original, seed_roi, *, pitch_native, seed):
            if not np.isfinite(pitch_native) or not 2 <= pitch_native <= 50:
                raise ValueError('Observed native pitch required')
            scope, mask, quality = renderer.propose_visible_pad(original, seed_roi)
            if scope is None:
                return original.copy(), dict(status=quality['status'], scope=quality, rendered=False)
            a, b, c, d = scope
            crop = original[b:d, a:c]
            n = c - a
            pitch512 = pitch_native * 512 / n
            mask512 = cv2.resize(mask.astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST) > 0
            field, recipe = renderer.independent_irregular_field(mask512, pitch512, seed)
            value, profile_meta = profile(field, mask512, pitch512, seed)
            native = cv2.resize(value, (n, n), interpolation=cv2.INTER_CUBIC if n > 512 else cv2.INTER_AREA)
            m = mask.astype(np.float32)
            sigma = max(1., pitch_native * 1.2)
            support = cv2.GaussianBlur(m, (0, 0), sigma)
            low = np.stack([cv2.GaussianBlur(crop[:, :, k].astype(np.float32) * m, (0, 0), sigma)
                            / np.maximum(support, 1e-5) for k in range(3)], axis=2)
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32)
            low_gray = np.sum(low * np.array([.299, .587, .114], np.float32), axis=2)
            x0, y0, x1, y1 = seed_roi
            seed_gray = cv2.cvtColor(original[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32)
            seed_low = cv2.GaussianBlur(seed_gray, (0, 0), sigma)
            reference_rms = max(1., float(np.sqrt(np.mean((seed_gray - seed_low) ** 2))))
            variance = cv2.GaussianBlur((gray - low_gray) ** 2 * m, (0, 0), max(2., pitch_native * 2)) / np.maximum(
                cv2.GaussianBlur(m, (0, 0), max(2., pitch_native * 2)), 1e-5)
            amplitude = np.clip(np.sqrt(variance), reference_rms * .5, reference_rms * 1.5)
            noise, noise_meta = old_relief(mask, pitch_native, seed)
            rms = float(np.sqrt(np.mean(noise[mask] ** 2)))
            if rms > 0:
                noise *= reference_rms * .20 / rms
            # Independent weak fine surface relief, not original sensor noise/ridges.
            surface_rng = np.random.default_rng(seed ^ 0x5F1A)
            fine = surface_rng.standard_normal(mask.shape).astype(np.float32)
            fine = cv2.GaussianBlur(fine, (0, 0), .4) - cv2.GaussianBlur(fine, (0, 0), 1.)
            fine /= max(float(fine[mask].std()), 1e-6)
            noise += fine * reference_rms * .08
            taper = old_taper(mask, pitch_native * 1.6)
            generated = np.rint(np.clip(low + ((amplitude * .85 * native + noise) * taper)[..., None], 0, 255)).astype(np.uint8)
            candidate = original.copy()
            candidate[b:d, a:c][mask] = generated[mask]
            assert np.array_equal(candidate[b:d, a:c][~mask], crop[~mask])
            return candidate, dict(rendered=True, status='unvalidated_natural_variant_candidate',
                roi_xyxy=scope, scope=quality, pitch_native=pitch_native, pitch512=pitch512,
                seed=seed, field=recipe, profile=profile_meta, texture=noise_meta,
                reference_rms=reference_rms, ridge_contrast_gain=.85 * .85,
                relief_rms_gain=.20, independent_fine_rms_gain=.08, synthetic_boundary_taper_pitch=2., natural_variant=True,
                original_highpass_retained_inside_mask=False, original_highpass_boundary_blend=False,
                human_naturalness_validated=False, privacy_validated=False)

        frozen.render_whole_pad_candidate = render
        try:
            result = frozen.transform_fingerprint_photo(
                image, strength, return_details=return_details)
            if return_details:
                result[1].update(method='automatic_structure_transform_v4_natural_auto_04_experiment',
                                 appearance_variant=True, human_naturalness_validated=False)
            return result
        finally:
            frozen.render_whole_pad_candidate = old_render

if __name__ == '__main__':
    import run_structure_transform_v4_linux as entry
    load = entry.load_implementation

    def load_variant():
        structure, matcher, _ = load()
        return structure, matcher, transform_fingerprint_photo

    entry.load_implementation = load_variant
    try:
        entry.main()
    finally:
        entry.load_implementation = load
