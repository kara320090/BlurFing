import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from photo_synthetic_replacement_v4 import render, local_appearance, boundary_appearance, boundary_geometry, source_groups
from photo_synthetic_replacement_v2 import geometry, color_cells, color_field
from replace_photo_synthetic_v1 import run


class LocalAppearanceTests(unittest.TestCase):
    def fixture(self):
        yy, xx = np.mgrid[:800, :600]
        x, y = (xx-300)/240, (yy-400)/350
        mask = x*x+y*y < 1
        # Broad oblique fold, illumination and independent fine ridge signal.
        smooth = 160+15*x-12*y*y-22*np.exp(-((y-.48-.10*x)/.15)**2)
        known = np.stack((smooth+30, smooth, smooth-15), axis=2)
        rgb = np.clip(np.floor(known+3*np.sin(2*np.pi*yy/9)[:, :, None]+.5), 0, 255).astype(np.uint8)
        return rgb, mask, mask.astype(np.uint16), known

    def test_broad_crease_reconstruction_beats_global_polynomial(self):
        rgb, mask, _, known = self.fixture()
        _, _, u, v, width, length = geometry(mask)
        previous, _ = color_field(rgb[mask], u, v, width, length)
        current, gain, meta = local_appearance(rgb[mask], u, v, width, length)
        old_error = float(np.sqrt(np.mean((previous-known[mask])**2)))
        new_error = float(np.sqrt(np.mean((current-known[mask])**2)))
        self.assertLess(new_error, old_error*.8, (new_error, old_error))
        self.assertTrue(np.isfinite(gain).all())
        self.assertGreaterEqual(gain.min(), .70)
        self.assertLessEqual(gain.max(), 1.20)
        self.assertEqual(meta['evaluation_grid'], [128, 128])

    def test_cell_permutation_changes_source_ridges_not_generated_output(self):
        rgb, mask, labels, _ = self.fixture()
        yy, xx, u, v, width, length = geometry(mask)
        cells, _, _ = color_cells(u, v, width, length)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        distance, sector = boundary_geometry(local)
        cells = source_groups(cells, distance, width, sector)
        rng = np.random.default_rng(18)
        shuffled = rgb.copy(); p = rgb[mask].copy()
        for cell in np.unique(cells):
            take = cells == cell; p[take] = p[take][rng.permutation(take.sum())]
        shuffled[mask] = p
        first, ma = render(rgb, mask, labels, seed=123)
        second, mb = render(shuffled, mask, labels, seed=123)
        self.assertFalse(np.array_equal(shuffled[mask], rgb[mask]))
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(first[~mask], rgb[~mask])
        self.assertEqual(ma['source_alpha_inside_mask'], 0.)
        self.assertFalse(ma['privacy_validated'])

    def test_boundary_reconstruction_reduces_known_color_step_without_raw_blend(self):
        rgb, mask, _, _ = self.fixture()
        yy, xx, u, v, width, length = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        distance, sector = boundary_geometry(local)
        # A known coarse boundary color differs from the interior fill.
        pixels = np.tile([180, 150, 130], (len(u), 1)).astype(np.uint8)
        pixels[distance <= max(2., .004*width)] = [205, 175, 155]
        base = np.tile([180., 150., 130.], (len(u), 1))
        result, meta = boundary_appearance(base, pixels, u, v, width, length, distance, sector)
        edge = distance == 1
        self.assertLess(float(np.abs(result[edge]-pixels[edge]).mean()), 1.)
        np.testing.assert_allclose(result[distance > 1+meta['generated_transition_width']],
                                   base[distance > 1+meta['generated_transition_width']])
        self.assertEqual(meta['source_pixel_alpha'], 0.)
        self.assertFalse(meta['source_outside_permission_used'])

    def test_side_background_color_does_not_cross_into_proximal_sector(self):
        rgb, mask, _, _ = self.fixture()
        yy, xx, u, v, width, length = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        distance, sector = boundary_geometry(local)
        pixels = np.tile([180, 150, 130], (len(u), 1)).astype(np.uint8)
        pixels[sector < 2] = 245
        base = np.tile([180., 150., 130.], (len(u), 1))
        out, _ = boundary_appearance(base, pixels, u, v, width, length, distance, sector)
        np.testing.assert_allclose(out[sector >= 2], base[sector >= 2], atol=1e-8)
        with patch('photo_synthetic_replacement_v4.MAX_BOUNDING_PIXELS', 4):
            with self.assertRaisesRegex(ValueError, 'bbox_pixel_limit'):
                render(rgb, mask, mask.astype(np.uint16), seed=0)

    def test_background_does_not_enter_generated_skin(self):
        rgb, mask, labels, _ = self.fixture()
        second = rgb.copy(); second[~mask] = (0, 255, 0)
        a, _ = render(rgb, mask, labels, seed=18)
        b, _ = render(second, mask, labels, seed=18)
        np.testing.assert_array_equal(a[mask], b[mask])
        np.testing.assert_array_equal(b[~mask], second[~mask])

    def test_replay_and_original_array_unchanged(self):
        rgb, mask, labels, _ = self.fixture()
        before = rgb.copy()
        a, ma = render(rgb, mask, labels, seed=1)
        b, mb = render(rgb, mask, labels, seed=1)
        c, mc = render(rgb, mask, labels, seed=2)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(rgb, before)
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        self.assertEqual(ma['regions'][0]['color_field'], mc['regions'][0]['color_field'])

    def test_fallback_thin_holes_empty_and_resource_guards(self):
        rgb = np.full((80, 80, 3), (180, 150, 130), np.uint8)
        mask = np.zeros((80, 80), bool)
        a, meta = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(a, rgb)
        self.assertEqual(meta['replacement_regions'], 0)
        mask[10:70, 40] = True
        a, meta = render(rgb, mask, mask.astype(np.uint16), seed=0)
        self.assertEqual(meta['unresolved_texture_regions'], 1)
        self.assertIn('fallback', meta['regions'][0]['color_field']['method'])
        mask[10:70, 10:70] = True; mask[35:45, 35:45] = False
        a, meta = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(a[~mask], rgb[~mask])
        for bad in [True, -1, 2**128, float('inf')]:
            with self.assertRaises(ValueError): render(rgb, mask, mask.astype(np.uint16), seed=bad)
        with patch('photo_synthetic_replacement_v4.MAX_REGION_PIXELS', 4):
            with self.assertRaisesRegex(ValueError, 'pixel_limit'):
                render(rgb, mask, mask.astype(np.uint16), seed=0)
        mask[39:41] = False
        with self.assertRaisesRegex(ValueError, 'connected'):
            render(rgb, mask, mask.astype(np.uint16), seed=0)

    def test_constant_color_generates_ridges_and_bounded_field(self):
        rgb, mask, labels, _ = self.fixture(); rgb[:] = (180, 150, 130)
        _, _, u, v, width, length = geometry(mask)
        base, gain, _ = local_appearance(rgb[mask], u, v, width, length)
        np.testing.assert_allclose(base, rgb[mask], atol=1e-8)
        out, report = render(rgb, mask, labels, seed=2)
        self.assertGreater(out[mask, 0].astype(float).std(), 1.5)
        self.assertEqual(report['unresolved_texture_regions'], 0)

    def test_actual_file_binding_and_accepted_native_preservation(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, profile = SyntheticReplacementTests().cached(root, accepted=True)
            a, meta = run(source, cache, root/'v4', seed=15, renderer='v4')
            self.assertEqual(meta['synthetic_renderer'], 'v4')
            np.testing.assert_array_equal(a[accepted], native[accepted])
            np.testing.assert_array_equal(a[~mask], rgb[~mask])
            with Image.open(root/'v4/synthetic.png') as image:
                np.testing.assert_array_equal(np.array(image), a)
                self.assertEqual(image.getexif()[274], 6)
                self.assertEqual(image.info['icc_profile'], profile)
            with self.assertRaises(FileExistsError): run(source, cache, root/'v4', renderer='v4')


if __name__ == '__main__':
    cv2.setNumThreads(4)
    unittest.main()
