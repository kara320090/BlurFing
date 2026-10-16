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

    def test_v17_known_macro_depth_recovery_from_scalar_summaries(self):
        from photo_synthetic_replacement_v17 import fit_crease_depths
        y, x = np.mgrid[:512, :320].astype(float)
        u, v = (2*x/319-1).ravel(), (2*y/511-1).ravel()
        t = (v-.2*u-.04*u*u)*256/6
        basis = -np.exp(-.5*t*t)+.3*np.exp(-.5*((t-1.8)/.8)**2)
        base = np.full((len(u),3),160.)
        pixels = np.clip(np.floor(base+(9*basis)[:,None]+.5),0,255).astype(np.uint8)
        curve = dict(quadratic_v_from_u=[0., .2, .04], sigma_source_pixels=6., depth_RGB=3.)
        _, fitted, meta = fit_crease_depths(pixels,base,u,v,320.,512.,[curve])
        self.assertEqual(curve['depth_RGB'],3.)
        self.assertAlmostEqual(fitted[0]['depth_RGB'],9.,delta=.5)
        self.assertLessEqual(meta['curves'][0]['supported_scalar_cells'],96)
        self.assertFalse(meta['raw_source_residual_transferred'])

    def test_v17_light_response_follows_direction_and_preserves_height(self):
        from photo_synthetic_replacement_v17 import photographic_light
        ridge = np.broadcast_to(np.sin(2*np.pi*np.arange(256)/10),(128,256)).astype(np.float32)
        before = ridge.copy(); empty = np.zeros_like(ridge)
        a, meta = photographic_light(ridge,empty,10,1.,np.array([1.,0.]),8)
        b, _ = photographic_light(ridge,empty,10,1.,np.array([-1.,0.]),8)
        np.testing.assert_array_equal(ridge,before)
        self.assertGreater(np.mean(abs(a-b)),.1)
        self.assertTrue(np.isfinite(a).all());self.assertFalse(meta['source_detail_input'])

    def test_v17_actual_png_native_metadata_and_seed_replay(self):
        self.saved_contract('v17')

    def test_v17_translation_and_outside_colors_do_not_change_generated_region(self):
        from photo_synthetic_replacement_v17 import render
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture()
        a,_=render(rgb,mask,labels,seed=17)
        shifted=np.pad(rgb,((7,0),(13,0),(0,0)));m=np.pad(mask,((7,0),(13,0)))
        shifted[~m]=[0,255,0]
        b,_=render(shifted,m,m.astype(np.uint16),seed=17)
        np.testing.assert_array_equal(a[mask],b[m]);np.testing.assert_array_equal(b[~m],shifted[~m])

    def test_v17_fixed_observer_summaries_have_no_hidden_rgb_residual(self):
        from unittest.mock import patch
        from photo_synthetic_replacement_v17 import render
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture()
        changed=rgb.copy();changed[mask]=np.random.default_rng(9).integers(0,256,(mask.sum(),3),dtype=np.uint8)
        base=np.full((mask.sum(),3),160.)
        with patch('photo_synthetic_replacement_v17.photographic_skin',return_value=(base,{'macro_creases':{'curves':[]}})), \
             patch('photo_synthetic_replacement_v17.boundary_ribbon',side_effect=lambda base,*args:(base,{})), \
             patch('photo_synthetic_replacement_v10.native_style',return_value=(np.ones((1,1,4)),{})):
            a,_=render(rgb,mask,labels,seed=17);b,_=render(changed,mask,labels,seed=17)
        np.testing.assert_array_equal(a[mask],b[mask])


if __name__ == '__main__':
    import cv2
    cv2.setNumThreads(4)
    unittest.main()
