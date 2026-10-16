import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from photo_synthetic_replacement_v3 import render
from photo_synthetic_replacement_v2 import geometry, color_cells
import test_photo_synthetic_replacement_v2 as v2_tests
from replace_photo_synthetic_v1 import run


class PhotographicSyntheticTests(unittest.TestCase):
    def test_arch_normal_is_along_finger_not_across(self):
        from photographic_ridge_field_v3 import orientation
        mask = np.zeros((512, 512), bool); mask[30:480, 90:420] = True
        checked = 0
        for seed in range(15):
            angle, meta = orientation(mask, seed)
            if meta['pattern'] == 'arch':
                # Horizontal tangent at the arch's centre, vertical normal.
                self.assertLess(abs(np.cos(float(angle[230, 255]))), .22)
                self.assertTrue(meta['angle_is_ridge_normal'])
                checked += 1
        self.assertGreater(checked, 0)

    def test_source_phase_removed_and_seed_replay(self):
        rgb, mask, labels, _ = v2_tests.SyntheticV2Tests().fixture()
        _, _, u, v, width, length = geometry(mask)
        cells, _, _ = color_cells(u, v, width, length)
        rng = np.random.default_rng(723)
        permuted = rgb.copy(); pixels = rgb[mask].copy()
        for cell in np.unique(cells):
            take = cells == cell
            pixels[take] = pixels[take][rng.permutation(take.sum())]
        permuted[mask] = pixels
        a, ma = render(rgb, mask, labels, seed=321)
        b, mb = render(permuted, mask, labels, seed=321)
        c, mc = render(rgb, mask, labels, seed=322)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a[~mask], rgb[~mask])
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        self.assertEqual(ma['regions'][0]['color_field'], mc['regions'][0]['color_field'])
        self.assertFalse(ma['regions'][0]['pitch_is_measured'])
        self.assertFalse(ma['privacy_validated'])
        self.assertEqual(ma['source_alpha_inside_mask'], 0)

    def test_visible_ridge_structure_not_flat_fill_or_white_noise(self):
        rgb, mask, labels, _ = v2_tests.SyntheticV2Tests().fixture()
        rgb[:] = (185, 155, 140)
        a, meta = render(rgb, mask, labels, seed=321)
        region = meta['regions'][0]
        values = a[:, :, 0].astype(np.float32)-185
        self.assertGreater(values[mask].std(), 2.)
        # Neighbour correlation distinguishes continuous ridges from grain.
        inner = mask[:-1, :] & mask[1:, :]
        corr = np.corrcoef(values[:-1][inner], values[1:][inner])[0, 1]
        self.assertGreater(corr, .5)
        self.assertTrue(region['fingerprint_texture_resolved'])
        self.assertFalse(region['field_recipe']['original_pixels_input'])
        self.assertGreater(region['profile_recipe']['centers_count'], 100)

    def test_canonical_geometry_is_isotropic_and_translation_invariant(self):
        rgb, mask, labels, _ = v2_tests.SyntheticV2Tests().fixture()
        a, ma = render(rgb, mask, labels, seed=81)
        rgb2 = np.pad(rgb, ((21, 7), (13, 9), (0, 0)))
        mask2 = np.pad(mask, ((21, 7), (13, 9)))
        b, mb = render(rgb2, mask2, mask2.astype(np.uint16), seed=81)
        np.testing.assert_array_equal(a[mask], b[mask2])
        self.assertEqual(ma['regions'][0]['synthetic_pitch_pixels'], mb['regions'][0]['synthetic_pitch_pixels'])
        self.assertTrue(ma['regions'][0]['aspect_ratio_preserved'])
        self.assertEqual(ma['regions'][0]['canonical_shape'], [512, 512])

    def test_tiny_empty_holes_and_resource_limits(self):
        rgb = np.full((60, 60, 3), 100, np.uint8)
        mask = np.zeros((60, 60), bool); mask[5, 5] = True
        result, report = render(rgb, mask, mask.astype(np.uint16), seed=0)
        self.assertEqual(report['unresolved_texture_regions'], 1)
        np.testing.assert_array_equal(result[~mask], rgb[~mask])
        mask[:] = False
        result, report = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(result, rgb)
        mask[10:50, 10:50] = True; mask[25:35, 25:35] = False
        result, report = render(rgb, mask, mask.astype(np.uint16), seed=1)
        np.testing.assert_array_equal(result[~mask], rgb[~mask])
        with patch('photo_synthetic_replacement_v3.MAX_REGION_PIXELS', 3):
            with self.assertRaisesRegex(ValueError, 'pixel_limit'):
                render(rgb, mask, mask.astype(np.uint16), seed=0)
        for seed in [True, -1, 2**128, float('nan')]:
            with self.assertRaises(ValueError): render(rgb, mask, mask.astype(np.uint16), seed=seed)
        mask[29:32] = False
        with self.assertRaisesRegex(ValueError, 'connected'):
            render(rgb, mask, mask.astype(np.uint16), seed=0)

    def test_file_integration_preserves_accepted_and_roundtrips(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, _ = SyntheticReplacementTests().cached(root, accepted=True)
            result, meta = run(source, cache, root/'out', seed=61, renderer='v3')
            np.testing.assert_array_equal(result[accepted], native[accepted])
            np.testing.assert_array_equal(result[~mask], rgb[~mask])
            with Image.open(root/'out/synthetic.png') as image:
                np.testing.assert_array_equal(np.array(image), result)
            self.assertEqual(meta['synthetic_renderer'], 'v3')
            self.assertFalse(meta['native_gate_decisions_changed'])
            with self.assertRaises(FileExistsError): run(source, cache, root/'out', renderer='v3')


if __name__ == '__main__':
    cv2.setNumThreads(4)
    unittest.main()
