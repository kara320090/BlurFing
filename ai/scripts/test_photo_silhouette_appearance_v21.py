import unittest
from unittest.mock import patch
import cv2
import numpy as np
from scipy import ndimage
from scipy.special import ndtr
from photo_silhouette_appearance_v21 import refine, refine_regions, _fit_profile


class SilhouetteTests(unittest.TestCase):
    @staticmethod
    def scene():
        y, x = np.mgrid[:256, :320]
        signed = 92.-np.hypot(x-160., y-128.)
        skin = ndtr(signed/1.2)
        original = np.array([60., 72., 78.]) + skin[..., None]*np.array([115., 56., 32.])
        original += skin[..., None]*3*np.cos(y[..., None]*2*np.pi/8)
        mask = np.zeros(x.shape, np.uint8)
        angles = np.arange(9)*2*np.pi/9
        vertices = np.column_stack((160+97*np.cos(angles), 128+97*np.sin(angles))).astype(np.int32)
        cv2.fillPoly(mask, [vertices], 1);mask=mask.astype(bool)
        original=np.clip(np.floor(original+.5),0,255).astype(np.uint8)
        generated=original.copy()
        field=np.broadcast_to([175.,128.,110.],original.shape).copy()
        field+=2*np.sin(x[...,None]*2*np.pi/11)
        generated[mask]=np.floor(field[mask]+.5).astype(np.uint8)
        return original,generated,mask

    def test_curve_recovers_known_edge_without_shrinking_permission(self):
        source, generated, mask=self.scene()
        result,meta=refine(source,generated,mask,194.)
        self.assertTrue(meta['applied'])
        d=ndimage.distance_transform_edt(mask)
        edge=mask&(d<5)
        self.assertLess(np.abs(result[edge].astype(float)-source[edge]).mean(),
                        np.abs(generated[edge].astype(float)-source[edge]).mean()*.6)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        np.testing.assert_array_equal(result[d>=meta['correction_depth']],generated[d>=meta['correction_depth']])
        self.assertFalse(meta['permission_geometry_changed'])
        self.assertEqual(meta['source_pixel_alpha'],0.)
        self.assertGreater(np.count_nonzero(result[mask]!=source[mask]),mask.sum())

    def test_constant_same_skin_and_crease_do_not_become_silhouette(self):
        t=np.linspace(-12,12,65)
        for profile in (np.full((65,3),150.),150.+t[:,None]*np.ones((1,3)),
                        150.-40*np.exp(-t[:,None]**2/4)*np.ones((1,3)),
                        150.+4*np.cos(t[:,None]*2*np.pi/8)*np.ones((1,3))):
            self.assertIsNone(_fit_profile(profile,t,12.))

    def test_step_geometry_and_coarse_color_fit(self):
        t=np.linspace(-16,16,65)
        profile=np.array([60.,70.,80.])+ndtr((t[:,None]-2.)/1.2)*np.array([100.,65.,40.])
        model=_fit_profile(profile,t,16.)
        self.assertIsNotNone(model)
        self.assertAlmostEqual(model['offset'],2.,places=3)
        self.assertAlmostEqual(model['blur'],1.2,places=3)

    def test_rotation_axis_order(self):
        source,generated,mask=self.scene()
        result,meta=refine(source,generated,mask,194.)
        rotated,other=refine(np.rot90(source),np.rot90(generated),np.rot90(mask),194.)
        self.assertTrue(other['applied'])
        edge=mask&(ndimage.distance_transform_edt(mask)<12)
        # OpenCV contour start point changes; scalar evidence is not a bitwise
        # rotation promise. This catches x/y swaps while allowing node resampling.
        error=np.abs(np.rot90(rotated,-1).astype(float)-result)[edge]
        self.assertLess(error.mean(),3.)

    def test_inputs_immutable_and_deterministic(self):
        source,generated,mask=self.scene();copies=[a.copy() for a in (source,generated,mask)]
        a,ma=refine(source,generated,mask,194.);b,mb=refine(source,generated,mask,194.)
        np.testing.assert_array_equal(a,b);self.assertEqual(ma,mb)
        for original,actual in zip(copies,(source,generated,mask)):np.testing.assert_array_equal(original,actual)

    def test_missing_context_abstains_instead_of_replicating_evidence(self):
        source=np.full((32,32,3),150,np.uint8);mask=np.ones((32,32),bool)
        result,meta=refine(source,source.copy(),mask,32.)
        self.assertFalse(meta['applied']);np.testing.assert_array_equal(result,source)

    def test_hole_is_not_treated_as_an_outer_silhouette(self):
        source,generated,mask=self.scene();mask[120:135,150:170]=False
        result,meta=refine(source,generated,mask,194.)
        self.assertFalse(meta['applied']);self.assertEqual(meta['reason'],'unsupported_contour')
        np.testing.assert_array_equal(result,generated)

    def test_region_adapter_preserves_permission_and_deferred_labels(self):
        source,generated,mask=self.scene();labels=mask.astype(np.uint16)
        labels[10:30,10:30]=2
        result,meta=refine_regions(source,generated,mask,labels)
        self.assertGreater(meta['corrected_components'],0)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        self.assertTrue(all(r['region_id']==1 for r in meta['regions']))
        with patch('photo_silhouette_appearance_v21.MAX_PERMISSION_PIXELS',10):
            result,meta=refine_regions(source,generated,mask,labels)
        np.testing.assert_array_equal(result,generated)
        self.assertEqual(meta['regions'][0]['reason'],'appearance_size_limit_V19_retained')
        bad=mask.copy();bad[0,0]=True
        with self.assertRaises(ValueError):refine_regions(source,generated,bad,labels)

    def test_memory_and_input_contract_before_allocation(self):
        huge=np.broadcast_to(True,(4096,4096));rgb=np.broadcast_to(np.uint8(1),(4096,4096,3))
        with patch('photo_silhouette_appearance_v21.ndimage.label',side_effect=AssertionError('allocation')):
            with self.assertRaises(ValueError):refine(rgb,rgb,huge,100.)
        source,generated,mask=self.scene()
        for width in (0.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):refine(source,generated,mask,width)
        with self.assertRaises(ValueError):refine(source.astype(float),generated,mask,194.)
        with self.assertRaises(ValueError):refine(source,generated,mask.astype(np.uint8),194.)


if __name__=='__main__':unittest.main()
