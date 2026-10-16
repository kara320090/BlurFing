"""Behavioral contracts for independent photographic skin material experiments."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from photo_synthetic_replacement_v10 import render, render_core, native_style, material
from photo_synthetic_replacement_v2 import geometry
from replace_photo_synthetic_v1 import run


class MaterialTests(unittest.TestCase):
    def fixture(self):
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        return SyntheticV2Tests().fixture()[:3]

    def test_replay_seed_changes_background_translation_and_resources(self):
        rgb, mask, labels = self.fixture(); before = rgb.copy()
        a, meta = render(rgb, mask, labels, seed=9)
        b, _ = render(rgb, mask, labels, seed=9)
        c, _ = render(rgb, mask, labels, seed=10)
        np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(rgb, before)
        self.assertGreater(np.abs(a[mask].astype(float)-c[mask]).mean(), .5)
        padded = np.pad(rgb, ((5, 0), (9, 0), (0, 0)))
        m = np.pad(mask, ((5, 0), (9, 0))); padded[~m] = [0, 255, 0]
        d, _ = render(padded, m, m.astype(np.uint16), seed=9)
        np.testing.assert_array_equal(a[mask], d[m]); np.testing.assert_array_equal(d[~m], padded[~m])
        self.assertFalse(meta['privacy_validated']); self.assertEqual(meta['unresolved_texture_regions'], 0)
        for name in ['MAX_REGIONS', 'MAX_REGION_PIXELS', 'MAX_BOUNDING_PIXELS']:
            with patch('photo_synthetic_replacement_v10.'+name, 0):
                with self.assertRaises(ValueError): render(rgb, mask, labels, seed=9)
        for seed in [True, -1, 2**128, float('nan')]:
            with self.assertRaises(ValueError): render(rgb, mask, labels, seed=seed)

    def test_style_exports_bounded_scalars_and_material_has_no_source_raster_input(self):
        rgb, mask, _ = self.fixture()
        yy, xx, u, v, w, h = geometry(mask); local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        stats, meta = native_style(rgb[mask], local, u, v, w, h)
        self.assertLessEqual(stats.size, 192); self.assertLessEqual(max(meta['analysis_shape']), 1024)
        self.assertTrue(np.isfinite(stats).all()); self.assertFalse(meta['source_filtered_raster_exported'])
        base = np.full((len(u), 3), 160.)
        a, info = material(local, u, v, w, h, 7, stats, base)
        b, _ = material(local, u, v, w, h, 7, stats, base)
        np.testing.assert_array_equal(a, b)
        self.assertLessEqual(max(info['latent_shape']), 1536)
        self.assertGreater(np.std(a-base), .5)
        self.assertFalse(info['source_ridge_phase_transferred'])

    def test_actual_png_accepted_native_metadata_and_fresh_output(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, icc = SyntheticReplacementTests().cached(root, accepted=True)
            result, meta = run(source, cache, root/'v10', renderer='v10', seed=10)
            np.testing.assert_array_equal(result[accepted], native[accepted])
            np.testing.assert_array_equal(result[~mask], rgb[~mask])
            with Image.open(root/'v10/synthetic.png') as im:
                np.testing.assert_array_equal(result, np.array(im))
                self.assertEqual(im.getexif()[274], 6); self.assertEqual(im.info['icc_profile'], icc)
            self.assertEqual(meta['untreated_candidate_pixels'], 0)
            with self.assertRaises(FileExistsError): run(source, cache, root/'v10', renderer='v10')

    def test_nonfinite_generated_values_rejected_before_cast_and_empty_input(self):
        rgb, mask, labels = self.fixture()
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            render_core(rgb, mask, labels, seed=0,
                material_fn=lambda *args: (np.full((mask.sum(), 3), np.nan), {}))
        empty = np.zeros(mask.shape, bool)
        result, meta = render(rgb, empty, empty.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(result, rgb); self.assertEqual(meta['replacement_regions'], 0)

    def test_known_long_oblique_creases_reconstructed_without_flat_input_hallucination(self):
        from photo_synthetic_replacement_v7 import reconstructed_skin
        from photo_synthetic_replacement_v11 import folded_skin
        y, x = np.mgrid[:640, :420]
        mask = ((x-210)/197.4)**6+((y-320)/307.2)**6 < 1
        _, _, u, v, w, h = geometry(mask)
        broad = 160+8*u-6*v
        grooves = -14*np.exp(-.5*(((v-.28*u+.15)*h/2)/5.)**2)
        grooves -= 10*np.exp(-.5*(((v+.2*u-.35)*h/2)/6.)**2)
        truth = np.tile((broad+grooves)[:, None], (1, 3))
        pixels = np.clip(np.floor(truth+.8*np.sin(v*h)[:, None]+.5), 0, 255).astype(np.uint8)
        old, _ = reconstructed_skin(pixels, u, v, w, h)
        result, meta = folded_skin(pixels, u, v, w, h)
        self.assertLess(np.sqrt(np.mean((result-truth)**2)), np.sqrt(np.mean((old-truth)**2))*.85)
        self.assertEqual(len(meta['macro_creases']['curves']), 2)
        flat = np.full(pixels.shape, 160, np.uint8)
        result, meta = folded_skin(flat, u, v, w, h)
        self.assertEqual(meta['macro_creases']['curves'], [])
        np.testing.assert_allclose(result, 160, atol=1e-8)

    def test_v11_actual_file_contract_and_appearance_is_not_approved(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, icc = SyntheticReplacementTests().cached(root, accepted=True)
            result, meta = run(source, cache, root/'v11', renderer='v11', seed=11)
            np.testing.assert_array_equal(result[accepted], native[accepted])
            np.testing.assert_array_equal(result[~mask], rgb[~mask])
            self.assertFalse(meta['natural_appearance_validated']); self.assertFalse(meta['production_approved'])
            self.assertFalse(meta['native_gate_decisions_changed'])
            with Image.open(root/'v11/synthetic.png') as im:
                np.testing.assert_array_equal(np.array(im), result)
                self.assertEqual(im.getexif()[274], 6); self.assertEqual(im.info['icc_profile'], icc)

    def test_known_contour_shading_boundary_ribbon_improves(self):
        from scipy import ndimage
        from photo_synthetic_replacement_v7 import reconstructed_skin
        from photo_synthetic_replacement_v6 import continuous_boundary
        from photo_synthetic_replacement_v12 import boundary_ribbon
        from test_photo_synthetic_replacement_v4 import LocalAppearanceTests
        rgb, mask, _, truth = LocalAppearanceTests().fixture()
        yy, xx, u, v, w, h = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        base, _ = reconstructed_skin(rgb[mask], u, v, w, h)
        old, _ = continuous_boundary(base, rgb[mask], u, v, w, h, local)
        result, meta = boundary_ribbon(base, rgb[mask], u, v, w, h, local)
        distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
        take = distance < 3
        before = np.sqrt(np.mean((old[take]-truth[mask][take])**2))
        after = np.sqrt(np.mean((result[take]-truth[mask][take])**2))
        self.assertLess(after, before*.65)
        self.assertLessEqual(meta['populated_nodes'], 256)
        self.assertFalse(meta['source_outside_permission_used']); self.assertEqual(meta['source_pixel_alpha'], 0.)

    def test_v12_tiny_region_projection_does_not_magnify_ridge_frequency(self):
        mask = np.ones((30, 20), bool)
        _, _, u, v, w, h = geometry(mask)
        result, meta = material(mask, u, v, w, h, 3, np.ones((1, 1, 4)),
            np.full((mask.sum(), 3), 160.), projection='dome')
        self.assertLessEqual(meta['design_scale'], 1.)
        self.assertGreaterEqual(meta['synthetic_pitch_pixels'], 4.)
        self.assertTrue(np.isfinite(result).all())

    def test_v12_crease_evidence_excludes_silhouette_cells_but_keeps_interior_grooves(self):
        from photo_synthetic_replacement_v12 import folded_skin
        y, x = np.mgrid[:640, :420]
        mask = ((x-210)/197.4)**6+((y-320)/307.2)**6 < 1
        _, _, u, v, w, h = geometry(mask)
        grooves = -18*np.exp(-.5*(((v-.25*u+.15)*h/2)/6.)**2)
        pixels = np.repeat((160+grooves)[:, None], 3, axis=1).astype(np.uint8)
        _, meta = folded_skin(pixels, u, v, w, h)
        info = meta['macro_creases']
        self.assertTrue(info['silhouette_adjacent_evidence_excluded'])
        self.assertGreaterEqual(len(info['curves']), 1)
        self.assertTrue(all(abs(c['quadratic_v_from_u'][0]) < .5 for c in info['curves']))

    def test_v12_fixed_summary_has_no_hidden_raw_rgb_residual(self):
        from photo_synthetic_replacement_v12 import render as v12
        rgb, mask, labels = self.fixture()
        modified = rgb.copy(); modified[mask] = np.random.default_rng(6).integers(0, 256, (mask.sum(), 3), dtype=np.uint8)
        base = np.full((mask.sum(), 3), 160.)
        with patch('photo_synthetic_replacement_v12.folded_skin', return_value=(base, {'macro_creases': {'curves': []}})), \
             patch('photo_synthetic_replacement_v12.boundary_ribbon', side_effect=lambda base, *a: (base, {})), \
             patch('photo_synthetic_replacement_v10.native_style', return_value=(np.ones((1, 1, 4)), {})):
            a, _ = v12(rgb, mask, labels, seed=4)
            b, _ = v12(modified, mask, labels, seed=4)
        np.testing.assert_array_equal(a[mask], b[mask])

    def test_v12_actual_saved_native_preservation_and_translation(self):
        from photo_synthetic_replacement_v12 import render as v12
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        rgb, mask, labels = self.fixture()
        a, meta = v12(rgb, mask, labels, seed=12)
        padded = np.pad(rgb, ((5, 0), (9, 0), (0, 0))); m = np.pad(mask, ((5, 0), (9, 0)))
        padded[~m] = [0, 255, 0]
        b, _ = v12(padded, m, m.astype(np.uint16), seed=12)
        np.testing.assert_array_equal(a[mask], b[m]); np.testing.assert_array_equal(b[~m], padded[~m])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, icc = SyntheticReplacementTests().cached(root, accepted=True)
            result, meta = run(source, cache, root/'v12', renderer='v12', seed=12)
            np.testing.assert_array_equal(result[accepted], native[accepted])
            np.testing.assert_array_equal(result[~mask], rgb[~mask])
            with Image.open(root/'v12/synthetic.png') as im:
                np.testing.assert_array_equal(np.array(im), result)
                self.assertEqual(im.getexif()[274], 6); self.assertEqual(im.info['icc_profile'], icc)


if __name__ == '__main__':
    import cv2
    cv2.setNumThreads(4)
    unittest.main()
