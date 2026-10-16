"""Behavioral and file contracts for the five versioned skin experiments."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from photo_synthetic_replacement_v13 import crease_geometry
from replace_photo_synthetic_v1 import run


class FiveIterationTests(unittest.TestCase):
    def test_crease_controls_deformation_and_occlusion_with_bounded_jacobian(self):
        y, x = np.mgrid[:512, :320].astype(float)
        u, v = 2*x/319-1, 2*y/511-1
        curve = dict(quadratic_v_from_u=[0., .2, .04], sigma_source_pixels=5., depth_RGB=10.)
        bent, occupancy, folds, meta = crease_geometry(u, v, 320., 512., [curve], 5)
        distance = abs(v-.2*u-.04*u*u)*256
        self.assertGreater(float(occupancy[distance < 2].mean()), .8)
        self.assertGreater(float(np.abs(bent-v).max()), .0001)
        self.assertLessEqual(meta['warp_gradient_bound'], .220001)
        self.assertTrue(np.isfinite(folds).all())
        dy, dx = np.gradient(bent-v)
        norm = np.hypot(dy*511/2, dx*319/2*512/320)
        self.assertLessEqual(float(norm.max()), .220001)

    def saved_contract(self, version):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, accepted, native, _, icc = SyntheticReplacementTests().cached(root, accepted=True)
            a, meta = run(source, cache, root/version, renderer=version, seed=91)
            b, _ = run(source, cache, root/(version+'-replay'), renderer=version, seed=91)
            np.testing.assert_array_equal(a, b)
            np.testing.assert_array_equal(a[accepted], native[accepted])
            np.testing.assert_array_equal(a[~mask], rgb[~mask])
            with Image.open(root/version/'synthetic.png') as image:
                np.testing.assert_array_equal(a, np.array(image))
                self.assertEqual(image.info['icc_profile'], icc)
                self.assertEqual(image.getexif()[274], 6)
            self.assertFalse(meta['production_approved']); self.assertFalse(meta['native_gate_decisions_changed'])
            self.assertEqual(meta['untreated_candidate_pixels'], 0)
            with self.assertRaises(FileExistsError): run(source, cache, root/version, renderer=version)

    def test_v13_actual_png_native_metadata_and_seed_replay(self):
        self.saved_contract('v13')

    def test_v14_known_boundary_shading_and_inner_join(self):
        from scipy import ndimage
        from photo_synthetic_replacement_v2 import geometry
        from photo_synthetic_replacement_v7 import reconstructed_skin
        from photo_synthetic_replacement_v12 import boundary_ribbon
        from photo_synthetic_replacement_v14 import hermite_ribbon
        from test_photo_synthetic_replacement_v4 import LocalAppearanceTests
        rgb, mask, _, truth = LocalAppearanceTests().fixture()
        y, x, u, v, w, h = geometry(mask); local = mask[y.min():y.max()+1, x.min():x.max()+1]
        base, _ = reconstructed_skin(rgb[mask], u, v, w, h)
        old, _ = boundary_ribbon(base, rgb[mask], u, v, w, h, local)
        new, meta = hermite_ribbon(base, rgb[mask], u, v, w, h, local)
        distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
        edge = distance < 3
        self.assertLess(np.sqrt(np.mean((new[edge]-truth[mask][edge])**2)),
                        np.sqrt(np.mean((old[edge]-truth[mask][edge])**2))*.8)
        np.testing.assert_array_equal(new[distance >= meta['transition_width']+1], base[distance >= meta['transition_width']+1])

    def test_v14_actual_png_native_metadata_and_seed_replay(self):
        self.saved_contract('v14')

    def test_pore_depressions_are_on_new_ridge_crests_and_replay(self):
        from photo_synthetic_replacement_v15 import pore_height
        ridge = np.broadcast_to(np.cos(2*np.pi*np.arange(256)/10), (128, 256)).astype(np.float32)
        a, meta = pore_height(ridge, 10, 7)
        b, _ = pore_height(ridge, 10, 7)
        c, _ = pore_height(ridge, 10, 8)
        np.testing.assert_array_equal(a, b)
        self.assertGreater(np.mean(np.abs(a-c)), .01)
        self.assertGreater(float(np.mean((ridge > .3)[a < -.3])), .95)
        self.assertEqual(meta['centers_outside_generated_ridge_crest'], 0)
        self.assertGreater(meta['centers'], 20); self.assertFalse(meta['uniform_white_flecks'])

    def test_v15_actual_png_native_metadata_and_seed_replay(self):
        self.saved_contract('v15')

    def test_v16_ridge_cross_sections_have_spatial_width_variation(self):
        from photo_synthetic_replacement_v16 import organic_profile
        field = np.broadcast_to(np.sin(2*np.pi*np.arange(512)/10), (512, 512)).astype(np.float32)
        a, meta = organic_profile(field, 10, 2)
        b, _ = organic_profile(field, 10, 2)
        duty = [(a[y:y+64, x:x+64] > 0).mean() for y in range(0,512,64) for x in range(0,512,64)]
        np.testing.assert_array_equal(a, b)
        self.assertGreater(float(np.std(duty)), .025)
        self.assertTrue(np.isfinite(a).all()); self.assertFalse(meta['source_phase_input'])

    def test_v16_actual_png_native_metadata_and_seed_replay(self):
        self.saved_contract('v16')


if __name__ == '__main__':
    import cv2
    cv2.setNumThreads(4)
    unittest.main()
