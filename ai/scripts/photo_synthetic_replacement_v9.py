"""Iteration 3: independent pores, shallow microfolds and irregular skin sheen."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v7 import render_core
from photo_synthetic_replacement_v8 import fine_photographic_relief
from photo_synthetic_replacement_v6 import smoothstep


def micro_surface(values, base, local, u, v, width, length, seed, energies):
    """Independent skin details; coarse energy controls strength, never phase."""
    rng = np.random.default_rng(seed ^ 0x932D)
    scale = min(1., 640/max(width, length))
    w, h = max(16, round(width*scale)), max(16, round(length*scale))
    sample = np.vstack(((v+1)*(h-1)/2, (u+1)*(w-1)/2))
    pitch = max(2., width*scale/70.)
    def normalize(a):
        a = a-float(a.mean())
        return a/max(float(a.std()), 1e-6)
    def take(a):
        return ndimage.map_coordinates(a, sample, order=1, mode='nearest', prefilter=False)
    random = rng.standard_normal((h, w)).astype(np.float32)
    fine = normalize(cv2.GaussianBlur(random, (0, 0), max(.45, pitch*.11))-
                     cv2.GaussianBlur(random, (0, 0), max(.9, pitch*.4)))
    impulses = (rng.random((h, w)) < .028).astype(np.float32)
    pores = cv2.GaussianBlur(impulses, (0, 0), max(.45, pitch*.09))
    shoulder = cv2.GaussianBlur(impulses, (0, 0), max(.9, pitch*.22))
    pore_relief = np.clip(normalize(shoulder-pores), -3., 2.)
    # Mostly transverse, short shallow microfolds, not long random scratches.
    canvas = np.zeros((h*2, w*2), np.float32)
    count = min(512, max(1, round(w*h/(pitch*pitch*70))))
    for _ in range(count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        span = pitch*rng.uniform(1.8, 5.0)
        slope = rng.uniform(-.4, .4)
        t = np.linspace(-.5, .5, 9)
        xy = np.column_stack((x+t*span, y+slope*t*span+pitch*rng.uniform(-.2, .2)*(1-4*t*t)))
        cv2.polylines(canvas, [np.rint(xy*2).astype(np.int32)], False,
            float(rng.uniform(.4, 1.)), 1, lineType=cv2.LINE_AA)
    folds = cv2.resize(canvas, (w, h), interpolation=cv2.INTER_AREA)
    folds = cv2.GaussianBlur(folds, (0, 0), max(.35, pitch*.065))
    folds = np.clip(normalize(cv2.GaussianBlur(folds, (0, 0), max(.75, pitch*.2))-folds), -3, 2)
    broad = cv2.resize(rng.standard_normal((9, 7)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    broad = normalize(cv2.GaussianBlur(broad, (0, 0), max(1., pitch*1.5)))
    sheen = np.clip(.78+.28*take(broad), .25, 1.30)
    ny, nx, _ = energies.shape
    coords = np.vstack(((v+1)*ny/2-.5, (u+1)*nx/2-.5))
    energy = ndimage.map_coordinates(energies[:, :, 0], coords, order=1, mode='nearest', prefilter=False)
    strength = np.clip(.25+.45*energy, .25, 1.8)
    detail = (.75*take(fine)+.65*take(pore_relief)+.90*take(folds))*strength
    middle = cv2.resize(rng.standard_normal((28, 20)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    middle = normalize(cv2.GaussianBlur(middle, (0, 0), max(.8, pitch*.75)))
    color = (.55*take(broad)+.45*take(middle))*np.clip(.8+.65*energy, .8, 3.2)
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    fade = smoothstep((distance-1)/max(2., .025*width))
    generated = (values-base)*sheen[:, None]+detail[:, None]*np.array([1., .96, .90])
    # Broad pigment irregularity is newly generated, not retained source detail.
    generated += color[:, None]*np.array([1., .70, .50])
    result = values*(1-fade[:, None])+(base+generated)*fade[:, None]
    return result, dict(applied=True, method='independent_pores_short_microfolds_and_irregular_sheen',
        latent_shape=[h, w], maximum_latent_dimension=640, shallow_fold_count=count,
        source_pixels_input=False, source_residual_input=False, source_phase_input=False,
        source_style_input='coarse_isotropic_band_energy_pairs_only',
        detail_strength_range=[float(strength.min()), float(strength.max())],
        sheen_range=[float(sheen.min()), float(sheen.max())], original_pixel_alpha=0.)


def render(rgb, mask, labels, *, seed=None):
    return render_core(rgb, mask, labels, seed=seed, version='v9',
        relief_fn=fine_photographic_relief, surface_fn=micro_surface)
