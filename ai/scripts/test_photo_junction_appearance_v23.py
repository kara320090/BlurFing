import unittest
from unittest.mock import patch
import numpy as np
from scipy import ndimage
from scipy.special import ndtr
from photo_junction_appearance_v23 import cell_grid,design,fit_patch,refine,refine_regions


class JunctionTests(unittest.TestCase):
    def test_known_crossing_geometry_predicts_unseen_spatial_cells(self):
        radius=32.;cells=cell_grid(radius)
        q=np.array([.45,2.,1.3,1.8,-1.,8.])
        coeff=np.array([[60,70,75],[1,1,1],[0,0,0],[115,65,40],[1,1,1],[0,0,0],
                        [-12,-16,-18],[2,2,2],[-2,-2,-2],[-18,-16,-14]])
        means=(design(cells,q,radius)[0]@coeff).mean(axis=1)
        model=fit_patch(means,cells,radius)
        self.assertIsNotNone(model)
        self.assertEqual(model['kind'],'edge_and_crossing_fold')
        y,x=np.mgrid[-30:31:3,-30:31:3];points=np.column_stack((x.ravel(),y.ravel()))
        actual=design(points,q,radius)[0]@coeff
        predicted=design(points,model['q'],radius)[0]@model['coefficients']
        self.assertLess(np.sqrt(np.mean((actual-predicted)**2)),1.5)
        self.assertGreater(model['validation_cells'],25)

    def test_periodic_lines_and_flat_patch_are_not_a_junction(self):
        cells=cell_grid(32.)
        for means in (np.full((169,3),150.),np.broadcast_to(
                (150+20*np.cos(cells[...,0]*2*np.pi/8)*np.cos(cells[...,1]*2*np.pi/10)).mean(axis=1)[:,None],(169,3))):
            self.assertIsNone(fit_patch(means,cells,32.))

    def test_bounded_quadratic_is_not_rejected_for_large_canceling_coefficients(self):
        cells=cell_grid(32.);q=np.array([.2,1.,1.2])
        coeff=np.array([[200,210,200],[0,0,0],[0,0,0],[-100,-80,-70],
                        [80,60,60],[0,0,0],[-70,-50,-50],[0,0,0],[0,0,0]])
        means=(design(cells,q,32.)[0]@coeff).mean(axis=1)
        model=fit_patch(means,cells,32.)
        self.assertIsNotNone(model)
        actual=design(cells,model['q'],32.)[0]@model['coefficients']
        self.assertLess(np.sqrt(np.mean((actual.mean(axis=1)-means)**2)),1.)

    @staticmethod
    def scene():
        y,x=np.mgrid[:256,:320]
        skin=ndtr((x-70-.18*(y-128))/1.3)
        fold=np.exp(-.5*((y-174-.3*(x-70))/7.)**2)
        base=np.array([60.,70.,75.])+skin[...,None]*np.array([115.,65.,40.])
        base-=skin[...,None]*fold[...,None]*np.array([18.,16.,14.])
        source=base+skin[...,None]*2*np.cos(y[...,None]*2*np.pi/8)
        mask=(x>=63)&(x<210)&(y>45)&(y<182)
        generated=source.copy()
        generated[mask]=np.broadcast_to([175.,135.,115.],source.shape)[mask]+2*np.sin(x[mask,None]*2*np.pi/11)
        cast=lambda a:np.clip(np.floor(a+.5),0,255).astype(np.uint8)
        return cast(source),cast(generated),mask

    def test_known_junction_recovery_and_permission_preservation(self):
        source,generated,mask=self.scene();result,meta=refine(source,generated,mask,147.)
        self.assertTrue(meta['applied'])
        y,x=np.mgrid[:256,:320];corner=mask&(x<95)&(y>158)
        self.assertLess(abs(result[corner].astype(float)-source[corner]).mean(),
                        abs(generated[corner].astype(float)-source[corner]).mean()*.75)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        deep=ndimage.distance_transform_edt(mask)>=meta['correction_depth']
        np.testing.assert_array_equal(result[deep],generated[deep])
        self.assertFalse(meta['permission_geometry_changed'])
        self.assertGreater(np.any(result[mask]!=source[mask],axis=1).mean(),.8)

    def test_determinism_rotation_and_input_immutability(self):
        source,generated,mask=self.scene();old=[a.copy() for a in (source,generated,mask)]
        a,ma=refine(source,generated,mask,147.);b,mb=refine(source,generated,mask,147.)
        np.testing.assert_array_equal(a,b);self.assertEqual(ma,mb)
        for before,after in zip(old,(source,generated,mask)):np.testing.assert_array_equal(before,after)
        rotated,mr=refine(np.rot90(source),np.rot90(generated),np.rot90(mask),147.)
        self.assertTrue(mr['applied'])
        self.assertLess(abs(a.astype(float)-np.rot90(rotated,-1)).mean(),1.)

    def test_holes_missing_context_and_size_limits_keep_previous(self):
        source=np.full((32,32,3),150,np.uint8);mask=np.ones((32,32),bool)
        result,meta=refine(source,source,mask,32.)
        self.assertFalse(meta['applied']);np.testing.assert_array_equal(result,source)
        source,generated,mask=self.scene();mask[100:105,100:105]=False
        result,meta=refine(source,generated,mask,147.)
        self.assertFalse(meta['applied']);np.testing.assert_array_equal(result,generated)
        labels=mask.astype(np.uint16)
        with patch('photo_junction_appearance_v23.MAX_PERMISSION_PIXELS',10):
            result,meta=refine_regions(source,generated,mask,labels)
        np.testing.assert_array_equal(result,generated)
        huge=np.broadcast_to(True,(4096,4096));rgb=np.broadcast_to(np.uint8(1),(4096,4096,3))
        with patch('photo_junction_appearance_v23.ndimage.label',side_effect=AssertionError('allocation')):
            with self.assertRaises(ValueError):refine(rgb,rgb,huge,100.)
        for width in (0.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):refine(source,generated,mask,width)

    def test_adapter_keeps_deferred_label(self):
        source,generated,mask=self.scene();labels=mask.astype(np.uint16)
        labels[10:20,10:20]=2
        # Isolate geometry from the separate residual-warning abstention test.
        with patch('photo_synthetic_residual_audit_v1.inspect_region',return_value=dict(windows=[],review_flags=0)):
            result,meta=refine_regions(source,generated,mask,labels)
        self.assertGreater(meta['corrected_components'],0)
        np.testing.assert_array_equal(result[~mask],generated[~mask])
        self.assertTrue(all(r['region_id']==1 for r in meta['regions']))
        bad=mask.copy();bad[0,0]=True
        with self.assertRaises(ValueError):refine_regions(source,generated,bad,labels)

    def test_new_residual_warning_retains_previous_pixels(self):
        source,generated,mask=self.scene()
        clear=dict(windows=[],review_flags=0)
        warning=dict(windows=[dict(bbox=[0,0,32,32],copy_review_flag=True)],review_flags=1)
        with patch('photo_synthetic_residual_audit_v1.inspect_region',side_effect=[clear,warning]):
            result,meta=refine_regions(source,generated,mask,mask.astype(np.uint16))
        np.testing.assert_array_equal(result,generated)
        self.assertEqual(meta['corrected_components'],0)
        self.assertEqual(meta['regions'][0]['reason'],'new_residual_review_warning_previous_retained')


if __name__=='__main__':unittest.main()
