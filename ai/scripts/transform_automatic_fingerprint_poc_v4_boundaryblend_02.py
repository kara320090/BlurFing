"""Boundary/detail fusion experiment based on auto04; human review required.

Reuses frozen detection, independent ridge generation, photometric reference,
structure gate and fail-closed return logic. Overrides are scoped and restored
even on exceptions. Invoke as the Linux entry point with --input; /tmp only.
Original detail is retained in the transition band; core structure stays independent.
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
            # Original illumination/base is kept; only detail is fused.
            base_original = cv2.GaussianBlur(crop.astype(np.float32), (0, 0), sigma)
            detail_original = crop.astype(np.float32) - base_original
            synthetic = low + (amplitude * .85 * native + noise)[..., None]
            # Mask-normalized blur prevents surrounding background from leaking
            # into the synthetic detail near the mask boundary.
            synth_base = np.stack([cv2.GaussianBlur(synthetic[:, :, k] * m,
                (0, 0), sigma) / np.maximum(support, 1e-5) for k in range(3)], axis=2)
            detail_synthetic = synthetic - synth_base
            # Padded signed distance keeps external pixels exactly original.
            padded = np.pad(mask.astype(np.uint8), 1)
            inside = cv2.distanceTransform(padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
            outside = cv2.distanceTransform(1-padded, cv2.DIST_L2, 5)[1:-1, 1:-1]
            distance = inside - outside
            luminance = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float32)
            lighting = cv2.GaussianBlur(luminance, (0, 0), max(1., pitch_native))
            highlight = np.clip((lighting - 220.) / 35., 0., 1.)
            gx = cv2.Sobel(lighting, cv2.CV_32F, 1, 0, ksize=3) / 8.
            gy = cv2.Sobel(lighting, cv2.CV_32F, 0, 1, ksize=3) / 8.
            crease = np.clip(np.hypot(gx, gy) / 12., 0., 1.)
            yy, xx = np.indices(mask.shape, dtype=np.float32)
            # Less than two cycles across the pad: weight only, never field warp.
            phase = (seed % 997) / 997. * 2. * np.pi
            shape = .65 * np.cos(2*np.pi*xx/max(n-1,1) + phase) + .35 * np.sin(np.pi*yy/max(n-1,1) + phase*.7)
            bottoms = np.max(np.where(mask, yy, -1), axis=0)
            bottom_gap = np.maximum(bottoms[None, :] - yy, 0.)
            bottom_factor = np.clip(1-bottom_gap/(6.*pitch_native), 0., 1.)
            bottom_factor = bottom_factor**2*(3-2*bottom_factor) * mask
            nx = cv2.GaussianBlur(np.abs(np.gradient(inside, axis=1)), (0,0), max(1.,pitch_native))
            side = np.clip(nx,0.,1.)
            width_pitch = np.clip(3. + .65*shape + .75*bottom_factor + .25*crease + .2*side + .2*highlight, 2.5, 4.5)
            band_width = width_pitch * pitch_native
            # Bottom buffer grows to 1.25..1.5 pitches at strong crease gradients.
            buffer = pitch_native * (bottom_factor*(1.25+.25*crease) + .15*side)
            perturbation = .20*pitch_native*shape*np.clip(inside/pitch_native,0.,1.)
            # Never perturb the original-dominant buffer or extend outside mask.
            effective_distance = np.maximum(0., distance-buffer)
            perturbation *= np.clip(effective_distance/pitch_native,0.,1.)
            t = np.clip((effective_distance+perturbation)/band_width,0.,1.)
            smooth = t*t*(3-2*t)
            boundary_weight = smooth*smooth
            attenuation = (1-.45*highlight)*(1-.22*crease)*(1-.10*side*np.clip(1-inside/(5*pitch_native),0.,1.))
            weight = boundary_weight*attenuation*m
            # Fine residual is preserved; attenuate the coarser original detail
            # in mixed-weight pixels to limit overlapping original/synthetic ridges.
            # Gaussian separation is approximate, not guaranteed ridge removal.
            coarse_original = cv2.GaussianBlur(detail_original, (0,0), max(.5,.18*pitch_native))
            fine_original = detail_original-coarse_original
            overlap = .5*4*weight*(1-weight)
            original_component = fine_original + (1-overlap[...,None])*coarse_original
            blended_detail = (1-weight[...,None])*original_component + weight[...,None]*detail_synthetic
            generated = np.rint(np.clip(base_original + blended_detail, 0, 255)).astype(np.uint8)
            # Diagnostics are pre-gate proposals, never labelled as returned ROI.
            from pathlib import Path
            from PIL import Image
            import fingerprint_structure_check as structure
            diagnostic_dir = Path(structure.OUT).resolve()
            if not diagnostic_dir.is_relative_to(Path('/tmp')):
                raise ValueError('Boundary diagnostics require /tmp output')
            diagnostic_dir = diagnostic_dir / ('boundary_proposal_' + str(seed))
            diagnostic_dir.mkdir(exist_ok=False)
            def save_rgb(name, value):
                Image.fromarray(np.rint(np.clip(value, 0, 255)).astype(np.uint8)).save(diagnostic_dir / name)
            save_rgb('original_base.png', base_original)
            # Common visualization gain, not actual output colour/contrast.
            for name, value in [('original_detail', detail_original),
                                ('synthetic_detail', detail_synthetic), ('blended_detail', blended_detail)]:
                save_rgb(name + '_visualization.png', 128. + 3. * value)
            Image.fromarray(np.rint(weight * 255).astype(np.uint8)).save(diagnostic_dir / 'weight_map.png')
            np.save(diagnostic_dir / 'weight_map.npy', weight)
            np.save(diagnostic_dir / 'transition_width_pitch.npy', width_pitch)
            np.save(diagnostic_dir / 'original_buffer.npy', (mask & (inside <= buffer)))
            Image.fromarray(np.rint((width_pitch-2.5)/2.*255).astype(np.uint8)).save(diagnostic_dir/'transition_width.png')
            Image.fromarray(((mask & (inside <= buffer))*255).astype(np.uint8)).save(diagnostic_dir/'original_buffer.png')
            Image.fromarray(np.where(~mask, 0, np.where(t < 1., 127, 255)).astype(np.uint8)).save(diagnostic_dir / 'zones.png')
            band = mask & (t < 1.)
            fusion = dict(method='original_base_detail_fusion', gaussian_sigma_native=sigma,
                gaussian_sigma_pitch=1.2, transition_width_native_range=[float(band_width[mask].min()),float(band_width[mask].max())],
                transition_width_pitch=3., transition_width_pitch_range=[2.5,4.5], ramp='squared_smoothstep',
                lower_transition_width_pitch_stats={k:float(fn(width_pitch[mask & (bottom_gap<6*pitch_native)])) for k,fn in [('min',np.min),('mean',np.mean),('max',np.max)]},
                buffer_max_pitch=float(buffer[mask].max()/pitch_native), original_buffer_pixels=int(np.count_nonzero(mask & (inside<=buffer))),
                distance_perturbation_max_pitch=.20, fine_residual_sigma_pitch=.18, original_coarse_overlap_attenuation_max=.5,
                transition_mean_synthetic_weight=float(weight[band].mean()),
                transition_original_dominant_fraction=float(np.mean(weight[band] < .5)),
                core_pixels=int(np.count_nonzero(mask & ~band)), transition_pixels=int(band.sum()),
                highlight_attenuation_max=.45, brightness_gradient_attenuation_max=.22,
                original_residual_core_injection=0., original_structure_copied=False,
                original_detail_retained_in_transition=True,
                modulation_output_attenuated_by_weight=True,
                synthetic_field_warp_unmodified=True, detail_visualization_gain=3.,
                diagnostics_folder=str(diagnostic_dir), diagnostic_stage='pre_structure_gate_proposal')
            candidate = original.copy()
            candidate[b:d, a:c][mask] = generated[mask]
            assert np.array_equal(candidate[b:d, a:c][~mask], crop[~mask])
            return candidate, dict(rendered=True, status='unvalidated_natural_variant_candidate',
                roi_xyxy=scope, scope=quality, pitch_native=pitch_native, pitch512=pitch512,
                seed=seed, field=recipe, profile=profile_meta, texture=noise_meta, boundary_fusion=fusion,
                reference_rms=reference_rms, ridge_contrast_gain=.85 * .85,
                relief_rms_gain=.20, independent_fine_rms_gain=.08, synthetic_boundary_taper_pitch=3., natural_variant=True,
                original_highpass_retained_inside_mask=True, original_highpass_boundary_blend=True,
                human_naturalness_validated=False, privacy_validated=False)

        frozen.render_whole_pad_candidate = render
        try:
            result = frozen.transform_fingerprint_photo(
                image, strength, return_details=return_details)
            if return_details:
                result[1].update(method='automatic_structure_transform_v4_boundaryblend_02_experiment',
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
