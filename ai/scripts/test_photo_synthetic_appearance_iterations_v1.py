import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from photo_synthetic_replacement_v2 import geometry, color_cells
from photo_synthetic_replacement_v4 import local_appearance, boundary_geometry, source_groups
from photo_synthetic_replacement_v5 import macro_creases
from photo_synthetic_replacement_v6 import texture_style
from photo_synthetic_replacement_v7 import render, reconstructed_skin, skin_cells
from replace_photo_synthetic_v1 import run


class SkinIterationTests(unittest.TestCase):
    def fixture(self):
        from test_photo_synthetic_replacement_v4 import LocalAppearanceTests
        return LocalAppearanceTests().fixture()

    def test_known_broad_fold_reconstruction_improves(self):
        rgb, mask, _, truth = self.fixture()
        _, _, u, v, w, h = geometry(mask)
        base, _, _ = local_appearance(rgb[mask], u, v, w, h)
        correction, _, _ = macro_creases(rgb[mask], base, u, v, w, h)
        surface, meta = reconstructed_skin(rgb[mask], u, v, w, h)
        before = float(np.sqrt(np.mean((base+correction[:, None]-truth[mask])**2)))
        after = float(np.sqrt(np.mean((surface-truth[mask])**2)))
        self.assertLess(after, before*.8, (before, after))
        self.assertFalse(meta['source_filtered_image_transferred'])
        self.assertLessEqual(meta['maximum_source_statistics'], 1440)

    def test_fixed_style_and_summary_has_no_hidden_raw_texture_path(self):
        rgb, mask, labels, _ = self.fixture()
        yy, xx, u, v, w, h = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        distance, sector = boundary_geometry(local)
        old, _, _ = color_cells(u, v, w, h)
        cells, nx, ny = skin_cells(u, v, w, h)
        groups = source_groups(old, distance, w, sector)*(nx*ny)+cells
        shuffled = rgb.copy(); pixels = rgb[mask].copy(); rng = np.random.default_rng(100)
        for group in np.unique(groups):
            take = groups == group; pixels[take] = pixels[take][rng.permutation(take.sum())]
        shuffled[mask] = pixels
        summaries = texture_style(rgb[mask], local, u, v, w, h)
        with patch('photo_synthetic_replacement_v7.texture_style', return_value=summaries):
            a, meta = render(rgb, mask, labels, seed=90)
            b, _ = render(shuffled, mask, labels, seed=90)
        self.assertFalse(np.array_equal(pixels, rgb[mask]))
        np.testing.assert_array_equal(a, b)
        self.assertFalse(meta['privacy_validated'])

    def test_input_resource_background_and_seed_contracts(self):
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb, mask, labels, _ = SyntheticV2Tests().fixture()
        before = rgb.copy()
        a, meta = render(rgb, mask, labels, seed=4)
        b, _ = render(rgb, mask, labels, seed=4)
        c, _ = render(rgb, mask, labels, seed=5)
        np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(rgb, before)
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        shifted = np.pad(rgb, ((11, 0), (7, 0), (0, 0)))
        m = np.pad(mask, ((11, 0), (7, 0))); shifted[~m] = [0, 255, 0]
        d, _ = render(shifted, m, m.astype(np.uint16), seed=4)
        np.testing.assert_array_equal(a[mask], d[m]); np.testing.assert_array_equal(d[~m], shifted[~m])
        self.assertEqual(meta['unresolved_texture_regions'], 0)
        for name in ['MAX_REGION_PIXELS', 'MAX_BOUNDING_PIXELS', 'MAX_REGIONS']:
            with patch('photo_synthetic_replacement_v7.'+name, 0):
                with self.assertRaises(ValueError): render(rgb, mask, labels, seed=0)
        for seed in [True, -1, 2**128, float('nan')]:
            with self.assertRaises(ValueError): render(rgb, mask, labels, seed=seed)

    def test_actual_saved_accepted_pixels_color_and_binding(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, profile = SyntheticReplacementTests().cached(root, accepted=True)
            a, meta = run(source, cache, root/'v7', seed=4, renderer='v7')
            np.testing.assert_array_equal(a[accepted], native[accepted])
            np.testing.assert_array_equal(a[~mask], rgb[~mask])
            with Image.open(root/'v7/synthetic.png') as image:
                np.testing.assert_array_equal(np.array(image), a)
                self.assertEqual(image.getexif()[274], 6)
                self.assertEqual(image.info['icc_profile'], profile)
            self.assertEqual(meta['synthetic_renderer'], 'v7')
            with self.assertRaises(FileExistsError): run(source, cache, root/'v7', renderer='v7')

    def test_finer_ridge_structure_has_higher_spatial_frequency(self):
        from photo_synthetic_replacement_v6 import styled_relief
        from photo_synthetic_replacement_v8 import fine_photographic_relief
        rgb, mask, _, _ = self.fixture()
        yy, xx, u, v, w, h = geometry(mask)
        local = mask[yy.min():yy.max()+1, xx.min():xx.max()+1]
        energy, _ = texture_style(rgb[mask], local, u, v, w, h)
        centers = []
        for fn in (styled_relief, fine_photographic_relief):
            a, meta = fn(local, u, v, w, h, 11, energy)
            raster = np.zeros(local.shape); raster[local] = a
            cy, cx = np.array(raster.shape)//2
            crop = raster[cy-96:cy+96, cx-96:cx+96]; crop -= crop.mean()
            power = np.abs(np.fft.fftshift(np.fft.fft2(crop*np.hanning(192)[:, None]*np.hanning(192)[None, :])))**2
            y, x = np.mgrid[-96:96, -96:96]; radius = np.sqrt(x*x+y*y)/192
            take = (radius > .025) & (radius < .4)
            centers.append(float(np.sum(power[take]*radius[take])/np.sum(power[take])))
            self.assertGreater(a.std(), .6)
        self.assertGreater(centers[1], centers[0]*1.25)

    def test_v8_seed_replay_and_saved_file_contract(self):
        from photo_synthetic_replacement_v8 import render as v8
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        rgb, mask, labels, _ = SyntheticV2Tests().fixture()
        a, _ = v8(rgb, mask, labels, seed=13)
        b, meta = v8(rgb, mask, labels, seed=13)
        c, _ = v8(rgb, mask, labels, seed=14)
        np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(a[~mask], rgb[~mask])
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        self.assertEqual(meta['unresolved_texture_regions'], 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, profile = SyntheticReplacementTests().cached(root, accepted=True)
            a, meta = run(source, cache, root/'v8', seed=4, renderer='v8')
            np.testing.assert_array_equal(a[accepted], native[accepted])
            np.testing.assert_array_equal(a[~mask], rgb[~mask])
            with Image.open(root/'v8/synthetic.png') as im:
                np.testing.assert_array_equal(np.array(im), a)
                self.assertEqual(im.info['icc_profile'], profile)
                self.assertEqual(im.getexif()[274], 6)


if __name__ == '__main__':
    import cv2
    cv2.setNumThreads(4)
    unittest.main()
