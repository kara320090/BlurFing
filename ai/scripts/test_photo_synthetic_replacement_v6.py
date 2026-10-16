import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v4 import boundary_geometry, boundary_appearance
from photo_synthetic_replacement_v5 import appearance_groups
from photo_synthetic_replacement_v6 import render, continuous_boundary, texture_style, styled_relief
from replace_photo_synthetic_v1 import run


class ContinuousAppearanceTests(unittest.TestCase):
    def fixture(self):
        from test_photo_synthetic_replacement_v4 import LocalAppearanceTests
        rgb, mask, labels, truth = LocalAppearanceTests().fixture()
        yy, xx, u, v, width, length = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        return rgb, mask, labels, truth, (u, v, width, length), local

    def test_known_boundary_gradient_error_decreases(self):
        rgb, mask, _, truth, (u, v, w, h), local = self.fixture()
        distance, sector = boundary_geometry(local)
        base = np.tile([170., 140., 120.], (mask.sum(), 1))
        old, _ = boundary_appearance(base, rgb[mask], u, v, w, h, distance, sector)
        new, meta = continuous_boundary(base, rgb[mask], u, v, w, h, local)
        edge = distance <= 2
        before = np.abs(old[edge]-truth[mask][edge]).mean()
        after = np.abs(new[edge]-truth[mask][edge]).mean()
        self.assertLess(after, before*.75, (before, after))
        inner = distance > 1+meta['generated_transition_width']
        np.testing.assert_array_equal(new[inner], base[inner])
        self.assertEqual(meta['source_pixel_alpha'], 0.)

    def test_observed_detail_changes_strength_without_transferring_phase(self):
        rgb, mask, _, _, args, local = self.fixture()
        sharp, sm = texture_style(rgb[mask], local, *args)
        blurry = cv2.GaussianBlur(rgb, (0, 0), 3)
        soft, bm = texture_style(blurry[mask], local, *args)
        self.assertLess(soft[:, :, 1].mean(), sharp[:, :, 1].mean()*.3)
        a, ma = styled_relief(local, *args, 123, sharp)
        b, mb = styled_relief(local, *args, 123, soft)
        self.assertLess(b.std(), a.std()*.65)
        self.assertGreater(b.std(), .45)  # weak input still receives new texture
        self.assertFalse(sm['source_filtered_image_transferred'])
        self.assertFalse(bm['calibrated_focus_measurement'])
        self.assertLessEqual(max(sm['analysis_shape']), 512)

    def test_spatial_style_has_more_detail_on_sharp_side(self):
        rgb, mask, _, _, (u, v, w, h), local = self.fixture()
        sharp, _ = texture_style(rgb[mask], local, u, v, w, h)
        energies = sharp.copy()
        energies[:, :energies.shape[1]//2] *= .08
        a, _ = styled_relief(local, u, v, w, h, 88, energies)
        self.assertLess(a[u < -.45].std(), a[u > .45].std()*.8)

    def test_fixed_summary_has_no_hidden_source_texture_path(self):
        rgb, mask, labels, _, args, local = self.fixture()
        u, v, w, h = args
        distance, sector = boundary_geometry(local)
        groups = appearance_groups(u, v, w, h, distance, sector)
        shuffled = rgb.copy(); pixels = rgb[mask].copy(); rng = np.random.default_rng(91)
        for group in np.unique(groups):
            take = groups == group; pixels[take] = pixels[take][rng.permutation(take.sum())]
        shuffled[mask] = pixels
        summaries = texture_style(rgb[mask], local, *args)
        # V6 intentionally changes style when spatial energy changes. Hold
        # that explicit new summary constant to test the downstream data flow.
        with patch('photo_synthetic_replacement_v6.texture_style', return_value=summaries):
            a, meta = render(rgb, mask, labels, seed=10)
            b, _ = render(shuffled, mask, labels, seed=10)
        self.assertFalse(np.array_equal(rgb[mask], shuffled[mask]))
        np.testing.assert_array_equal(a, b)
        self.assertFalse(meta['source_permutation_invariance_claimed'])
        self.assertFalse(meta['privacy_validated'])

    def test_background_translation_and_seed_replay(self):
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb, mask, labels, _ = SyntheticV2Tests().fixture(); original = rgb.copy()
        a, _ = render(rgb, mask, labels, seed=91)
        b, _ = render(rgb, mask, labels, seed=91)
        np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(rgb, original)
        moved = np.pad(rgb, ((13, 0), (17, 0), (0, 0)))
        m = np.pad(mask, ((13, 0), (17, 0))); moved[~m] = [0, 255, 0]
        c, _ = render(moved, m, m.astype(np.uint16), seed=91)
        np.testing.assert_array_equal(c[m], a[mask]); np.testing.assert_array_equal(c[~m], moved[~m])
        d, _ = render(rgb, mask, labels, seed=92)
        self.assertFalse(np.array_equal(a[mask], d[mask]))

    def test_holes_thin_empty_and_resource_contracts(self):
        rgb = np.full((60, 60, 3), 180, np.uint8); mask = np.zeros((60, 60), bool)
        a, _ = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(a, rgb)
        mask[5, 5] = True
        a, meta = render(rgb, mask, mask.astype(np.uint16), seed=0)
        self.assertEqual(meta['unresolved_texture_regions'], 1)
        mask[10:50, 10:50] = True; mask[5, 5] = False; mask[25:35, 25:35] = False
        a, _ = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(a[~mask], rgb[~mask])
        for invalid in [True, -1, 2**128, float('nan')]:
            with self.assertRaises(ValueError): render(rgb, mask, mask.astype(np.uint16), seed=invalid)
        for limit in ['MAX_REGION_PIXELS', 'MAX_BOUNDING_PIXELS', 'MAX_REGIONS']:
            with patch('photo_synthetic_replacement_v6.'+limit, 0):
                with self.assertRaises(ValueError): render(rgb, mask, mask.astype(np.uint16), seed=0)
        mask[29:32] = False
        with self.assertRaisesRegex(ValueError, 'connected'): render(rgb, mask, mask.astype(np.uint16), seed=0)

    def test_full_saved_png_accepted_preservation_and_source_binding(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, profile = SyntheticReplacementTests().cached(root, accepted=True)
            a, meta = run(source, cache, root/'v6', seed=15, renderer='v6')
            np.testing.assert_array_equal(a[accepted], native[accepted])
            np.testing.assert_array_equal(a[~mask], rgb[~mask])
            with Image.open(root/'v6/synthetic.png') as image:
                np.testing.assert_array_equal(np.array(image), a)
                self.assertEqual(image.getexif()[274], 6)
                self.assertEqual(image.info['icc_profile'], profile)
            self.assertEqual(meta['synthetic_renderer'], 'v6')
            with self.assertRaises(FileExistsError): run(source, cache, root/'v6', renderer='v6')
            Image.new('RGB', (rgb.shape[1], rgb.shape[0]), 'green').save(source)
            with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
                run(source, cache, root/'bad', renderer='v6')


if __name__ == '__main__':
    cv2.setNumThreads(4)
    unittest.main()
