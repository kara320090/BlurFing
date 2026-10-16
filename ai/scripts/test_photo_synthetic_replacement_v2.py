import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from photo_synthetic_replacement_v2 import render, geometry, color_cells, color_field
from photo_synthetic_replacement_v1 import render as render_v1
from replace_photo_synthetic_v1 import run


class SyntheticV2Tests(unittest.TestCase):
    def fixture(self):
        yy, xx = np.mgrid[:520, :440]
        mask = ((xx-220)/180)**2+((yy-260)/230)**2 < 1
        # Known smooth illumination plus independently controlled fine ridges.
        smooth = 155+22*(xx-220)/180-13*((yy-260)/230)**2
        colors = np.stack([smooth+30, smooth, smooth-15], axis=2)
        rgb = np.clip(np.floor(colors+3*np.sin(2*np.pi*xx/9)[:, :, None]+.5), 0, 255).astype(np.uint8)
        return rgb, mask, mask.astype(np.uint16), colors

    def test_cell_permutations_remove_spatial_ridge_phase(self):
        rgb, mask, labels, _ = self.fixture()
        yy, xx, u, v, width, length = geometry(mask)
        cells, _, _ = color_cells(u, v, width, length)
        permuted = rgb.copy(); rng = np.random.default_rng(63)
        pixels = rgb[mask].copy()
        for cell in np.unique(cells):
            select = cells == cell
            pixels[select] = pixels[select][rng.permutation(select.sum())]
        permuted[mask] = pixels
        self.assertFalse(np.array_equal(permuted[mask], rgb[mask]))
        a, report = render(rgb, mask, labels, seed=11)
        b, _ = render(permuted, mask, labels, seed=11)
        np.testing.assert_array_equal(a[mask], b[mask])
        np.testing.assert_array_equal(a[~mask], rgb[~mask])
        self.assertTrue(report['coarse_spatial_color_preserved'])
        self.assertFalse(report['original_pixel_residual_used'])
        self.assertEqual(report['source_alpha_inside_mask'], 0.)

    def test_known_illumination_recovered_without_high_frequency_residual(self):
        rgb, mask, _, colors = self.fixture()
        _, _, u, v, width, length = geometry(mask)
        reconstructed, meta = color_field(rgb[mask], u, v, width, length)
        self.assertEqual(meta['degree'], 3)
        new_error = np.sqrt(np.mean((reconstructed-colors[mask])**2))
        old_error = np.sqrt(np.mean((np.median(rgb[mask], axis=0)-colors[mask])**2))
        self.assertLess(new_error, 2.)
        self.assertLess(new_error, old_error*.3)

    def test_seed_replay_changes_only_generated_texture(self):
        rgb, mask, labels, _ = self.fixture()
        a, ma = render(rgb, mask, labels, seed=4)
        b, mb = render(rgb, mask, labels, seed=4)
        c, mc = render(rgb, mask, labels, seed=5)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        self.assertEqual(ma['regions'][0]['color_field'], mc['regions'][0]['color_field'])
        np.testing.assert_array_equal(c[~mask], rgb[~mask])

    def test_small_regions_holes_and_empty(self):
        rgb = np.full((60, 60, 3), 100, np.uint8)
        mask = np.zeros((60, 60), bool); mask[10:50, 10:50] = True; mask[25:35, 25:35] = False
        result, report = render(rgb, mask, mask.astype(np.uint16), seed=1)
        np.testing.assert_array_equal(result[~mask], rgb[~mask])
        self.assertEqual(report['regions'][0]['color_field']['degree'], 0)
        mask[:] = False
        result, report = render(rgb, mask, mask.astype(np.uint16), seed=1)
        np.testing.assert_array_equal(result, rgb)
        self.assertEqual(report['replacement_regions'], 0)

    def test_guards(self):
        rgb = np.full((20, 20, 3), 100, np.uint8)
        mask = np.ones((20, 20), bool); labels = mask.astype(np.uint16)
        for bad in [True, -1, 2**128, float('inf')]:
            with self.assertRaises(ValueError): render(rgb, mask, labels, seed=bad)
        with self.assertRaises(ValueError): render(rgb, mask, labels.astype(float), seed=0)
        with patch('photo_synthetic_replacement_v2.MAX_REGION_PIXELS', 10):
            with self.assertRaisesRegex(ValueError, 'pixel_limit'): render(rgb, mask, labels, seed=0)
        labels[8:12] = 0; mask = labels > 0
        with self.assertRaisesRegex(ValueError, 'connected'): render(rgb, mask, labels, seed=0)

    def test_versioned_file_integration_and_default_v1(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, _ = SyntheticReplacementTests().cached(root, accepted=True)
            new, report = run(source, cache, root/'new', seed=77, renderer='v2')
            self.assertEqual(report['synthetic_renderer'], 'v2')
            np.testing.assert_array_equal(new[accepted], native[accepted])
            old, report = run(source, cache, root/'old', seed=77)
            self.assertEqual(report['synthetic_renderer'], 'v1')
            from PIL import Image
            with Image.open(cache/'region_labels.png') as image: labels = np.array(image)
            expected, _ = render_v1(rgb, mask & ~accepted, np.where(accepted, 0, labels).astype(np.uint16), seed=77)
            expected[accepted] = native[accepted]
            np.testing.assert_array_equal(old, expected)
            with self.assertRaisesRegex(ValueError, 'unsupported_synthetic_renderer'):
                run(source, cache, root/'bad', renderer='unknown')


if __name__ == '__main__':
    unittest.main()
