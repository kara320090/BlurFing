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


if __name__ == '__main__':
    import cv2
    cv2.setNumThreads(4)
    unittest.main()
