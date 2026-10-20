import unittest
from unittest.mock import patch
import numpy as np
from scipy import ndimage
from scipy.special import ndtr
from photo_skin_seam_v22 import refine,refine_regions,_quadratic,_material,_material_design


class SkinSeamTests(unittest.TestCase):
    def test_old_boundary_shading_is_not_reintroduced_as_ridge_relief(self):
        from test_photo_silhouette_appearance_v21 import SilhouetteTests
        from photo_silhouette_appearance_v21 import refine as silhouette
        source,generated,mask=SilhouetteTests.scene()
        distance=ndimage.distance_transform_edt(mask)
        ring=mask&(distance>=3)&(distance<=7)
        generated[ring]=np.maximum(generated[ring].astype(int)-35,0).astype(np.uint8)
        old,_=silhouette(source,generated,mask,194.)
        new,meta=silhouette(source,generated,mask,194.,texture_mode='interior_envelope')
        self.assertTrue(meta['applied'])
        self.assertTrue(meta['generated_interior_envelope'])
        self.assertLess(abs(new[ring].astype(float)-source[ring]).mean(),
                        abs(old[ring].astype(float)-source[ring]).mean()*.7)
        np.testing.assert_array_equal(new[distance>=meta['correction_depth']],generated[distance>=meta['correction_depth']])
        np.testing.assert_array_equal(new[~mask],generated[~mask])

    @staticmethod
    def scene():
        y,x=np.mgrid[:256,:320]
        base=np.stack((160+.03*x,120+.02*y,100+.01*x),axis=2)
        source=np.floor(base+2*np.cos(x[...,None]*2*np.pi/8)+.5).astype(np.uint8)
        mask=((x-160)/92)**2+((y-128)/90)**2<1
        generated=source.copy()
        values=base-18.+2*np.sin(y[...,None]*2*np.pi/11)
        generated[mask]=np.floor(values[mask]+.5).astype(np.uint8)
        return source,generated,mask

    def test_coarse_material_seam_recovers_without_source_alpha(self):
        source,generated,mask=self.scene();result,meta=refine(source,generated,mask,184.)
        self.assertTrue(meta['applied'])
        distance=ndimage.distance_transform_edt(mask);edge=mask&(distance<4)
        self.assertLess(abs(result[edge].astype(float)-source[edge]).mean(),
                        abs(generated[edge].astype(float)-source[edge]).mean()*.6)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        np.testing.assert_array_equal(result[distance>=meta['correction_depth']],generated[distance>=meta['correction_depth']])
        self.assertEqual(meta['source_pixel_alpha'],0.)
        self.assertFalse(meta['permission_geometry_changed'])
        # Synthetic fine detail is retained; matching coarse color is not copying RGB.
        self.assertGreater(np.any(result[edge]!=source[edge],axis=1).mean(),.8)

    def test_sharp_silhouette_and_narrow_crease_do_not_fit_smooth_material(self):
        t=np.linspace(-16,16,65)
        step=80+80*ndtr(t[:,None])
        crease=150-30*np.exp(-t[:,None]**2/2)
        self.assertIsNone(_quadratic(np.broadcast_to(step,(65,3)),t,16.))
        self.assertIsNone(_quadratic(np.broadcast_to(crease,(65,3)),t,16.))
        profile=150+t[:,None]+t[:,None]**2*.03
        self.assertIsNotNone(_quadratic(np.broadcast_to(profile,(65,3)),t,16.))

    def test_determinism_immutability_and_rotation(self):
        source,generated,mask=self.scene();copies=[a.copy() for a in (source,generated,mask)]
        a,ma=refine(source,generated,mask,184.);b,mb=refine(source,generated,mask,184.)
        np.testing.assert_array_equal(a,b);self.assertEqual(ma,mb)
        for old,new in zip(copies,(source,generated,mask)):np.testing.assert_array_equal(old,new)
        rotated,meta=refine(np.rot90(source),np.rot90(generated),np.rot90(mask),184.)
        self.assertTrue(meta['applied'])
        self.assertLess(abs(a.astype(float)-np.rot90(rotated,-1)).mean(),.5)

    def test_broad_fold_model_recovers_shape_but_rejects_ridge_train(self):
        t=np.linspace(-32,32,65)
        profile=150+.05*t[:,None]-18*np.exp(-.5*((t[:,None]-2)/8)**2)
        profile=np.broadcast_to(profile,(65,3))
        model=_material(profile,t,32.)
        self.assertEqual(model['kind'],'broad_fold')
        self.assertAlmostEqual(model['center'],2.,places=2)
        self.assertAlmostEqual(model['sigma'],8.,places=2)
        np.testing.assert_allclose(_material_design(t,32.,model)@model['coeff'],profile,atol=.01)
        ridges=np.broadcast_to(150+12*np.cos(t[:,None]*2*np.pi/8),(65,3))
        self.assertIsNone(_material(ridges,t,32.))
        narrow=np.broadcast_to(150-25*np.exp(-.5*(t[:,None]/1.5)**2),(65,3))
        self.assertIsNone(_material(narrow,t,32.))

    def test_context_and_holes_abstain(self):
        source=np.full((32,32,3),150,np.uint8);mask=np.ones((32,32),bool)
        result,meta=refine(source,source,mask,32.)
        self.assertFalse(meta['applied']);np.testing.assert_array_equal(result,source)
        source,generated,mask=self.scene();mask[125:130,155:160]=False
        result,meta=refine(source,generated,mask,184.)
        self.assertFalse(meta['applied']);np.testing.assert_array_equal(result,generated)

    def test_adapter_keeps_deferred_regions_and_checks_bounds(self):
        source,generated,mask=self.scene();labels=mask.astype(np.uint16);labels[8:20,8:20]=2
        result,meta=refine_regions(source,generated,mask,labels)
        self.assertGreater(meta['corrected_components'],0)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        self.assertTrue(all(r['region_id']==1 for r in meta['regions']))
        with patch('photo_skin_seam_v22.MAX_PERMISSION_PIXELS',10):
            result,meta=refine_regions(source,generated,mask,labels)
        np.testing.assert_array_equal(result,generated)
        huge=np.broadcast_to(True,(4096,4096));rgb=np.broadcast_to(np.uint8(1),(4096,4096,3))
        with patch('photo_skin_seam_v22.ndimage.label',side_effect=AssertionError('allocation')):
            with self.assertRaises(ValueError):refine(rgb,rgb,huge,100.)
        for width in (0.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):refine(source,generated,mask,width)


if __name__=='__main__':unittest.main()
