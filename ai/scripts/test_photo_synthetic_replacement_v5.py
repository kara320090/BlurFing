import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v4 import local_appearance,boundary_geometry
from photo_synthetic_replacement_v5 import render,macro_creases,appearance_groups,independent_variation
from replace_photo_synthetic_v1 import run


class VariableRidgesCreaseTests(unittest.TestCase):
    def fixture(self,crease=True):
        yy,xx=np.mgrid[:900,:650]
        mask=((xx-325)/270)**2+((yy-450)/425)**2<1
        _,_,u,v,w,h=geometry(mask)
        flat=160+10*u-8*v*v;line=.38+.10*u+.04*u*u
        known=flat-(22*np.exp(-.5*((v-line)/.045)**2) if crease else 0)
        truth=np.column_stack([known+25,known,known-15])
        rgb=np.full((900,650,3),80,np.uint8)
        rgb[mask]=np.clip(truth+3*np.sin(yy[mask,None]*2*np.pi/8),0,255).astype(np.uint8)
        return rgb,mask,mask.astype(np.uint16),truth,(u,v,w,h)

    def test_known_curved_crease_recovered_with_less_error(self):
        rgb,mask,_,truth,geometry_args=self.fixture()
        u,v,w,h=geometry_args;base,_,_=local_appearance(rgb[mask],u,v,w,h)
        correction,strength,meta=macro_creases(rgb[mask],base,u,v,w,h)
        old=float(np.sqrt(np.mean((base-truth)**2)))
        new=float(np.sqrt(np.mean((base+correction[:,None]-truth)**2)))
        self.assertLess(new,old*.85,(old,new))
        self.assertEqual(len(meta['curves']),1)
        curve=meta['curves'][0];c=curve['quadratic_v_from_u']
        x=np.linspace(-.7,.7,30)
        self.assertLess(np.abs(c[0]+c[1]*x+c[2]*x*x-(.38+.1*x+.04*x*x)).max(),.04)
        self.assertGreater(strength.max(),.8)

    def test_fine_ridges_or_flat_skin_do_not_become_macro_creases(self):
        rgb,mask,_,_,(u,v,w,h)=self.fixture(crease=False)
        for pixels in [rgb[mask],np.full((mask.sum(),3),150,np.uint8)]:
            base,_,_=local_appearance(pixels,u,v,w,h)
            correction,strength,meta=macro_creases(pixels,base,u,v,w,h)
            self.assertEqual(meta['curves'],[])
            self.assertFalse(correction.any());self.assertFalse(strength.any())

    def test_independent_warp_is_reproducible_nonfolding_and_nonuniform(self):
        y,x=np.mgrid[:512,:512];field=np.sin(2*np.pi*y/9).astype(np.float32)
        a,contrast,meta=independent_variation(field,9,22)
        b,same,_=independent_variation(field,9,22)
        c,other,_=independent_variation(field,9,23)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(contrast,same)
        self.assertFalse(np.array_equal(a,c))
        self.assertLessEqual(meta['displacement_gradient_bound'],.280001)
        self.assertGreater(contrast.std(),.15)
        self.assertTrue(np.isfinite(a).all())
        self.assertGreater(np.abs(a-field).mean(),.1)

    def test_new_partition_permutation_and_background_invariance(self):
        rgb,mask,labels,_,(u,v,w,h)=self.fixture()
        yy,xx=np.nonzero(mask);local=mask[yy.min():yy.max()+1,xx.min():xx.max()+1]
        distance,sector=boundary_geometry(local);groups=appearance_groups(u,v,w,h,distance,sector)
        shuffled=rgb.copy();p=rgb[mask].copy();rng=np.random.default_rng(77)
        for group in np.unique(groups):
            take=groups==group;p[take]=p[take][rng.permutation(take.sum())]
        shuffled[mask]=p;shuffled[~mask]=(0,255,0)
        before=rgb.copy();a,meta=render(rgb,mask,labels,seed=100)
        b,_=render(shuffled,mask,labels,seed=100)
        np.testing.assert_array_equal(a[mask],b[mask]);np.testing.assert_array_equal(rgb,before)
        np.testing.assert_array_equal(a[~mask],rgb[~mask]);np.testing.assert_array_equal(b[~mask],shuffled[~mask])
        self.assertFalse(np.array_equal(p,rgb[mask]));self.assertFalse(meta['privacy_validated'])
        self.assertEqual(meta['source_alpha_inside_mask'],0.)

    def test_visible_continuous_ridges_and_seed_changes(self):
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture();rgb[:]=(185,155,140)
        a,ma=render(rgb,mask,labels,seed=321);b,_=render(rgb,mask,labels,seed=322)
        value=a[:,:,0].astype(float)-185;inner=mask[:-1]&mask[1:]
        self.assertGreater(value[mask].std(),1.3)
        self.assertGreater(np.corrcoef(value[:-1][inner],value[1:][inner])[0,1],.5)
        self.assertFalse(np.array_equal(a[mask],b[mask]))
        self.assertEqual(ma['unresolved_texture_regions'],0)
        self.assertEqual(ma['macro_crease_count'],0)

    def test_translation_and_accepted_png_binding(self):
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        rgb,mask,labels,_=SyntheticV2Tests().fixture()
        a,_=render(rgb,mask,labels,seed=4)
        padded=np.pad(rgb,((13,0),(21,0),(0,0)));m=np.pad(mask,((13,0),(21,0)))
        b,_=render(padded,m,m.astype(np.uint16),seed=4)
        np.testing.assert_array_equal(a[mask],b[m])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,cache,rgb,mask,accepted,native,_,profile=SyntheticReplacementTests().cached(root,accepted=True)
            result,meta=run(source,cache,root/'v5',seed=4,renderer='v5')
            np.testing.assert_array_equal(result[accepted],native[accepted])
            np.testing.assert_array_equal(result[~mask],rgb[~mask])
            with Image.open(root/'v5/synthetic.png') as image:
                np.testing.assert_array_equal(np.array(image),result)
                self.assertEqual(image.getexif()[274],6);self.assertEqual(image.info['icc_profile'],profile)
            self.assertEqual(meta['synthetic_renderer'],'v5')
            with self.assertRaises(FileExistsError):run(source,cache,root/'v5',renderer='v5')

    def test_empty_tiny_holes_and_resource_contracts(self):
        rgb=np.full((60,60,3),100,np.uint8);mask=np.zeros((60,60),bool)
        out,meta=render(rgb,mask,mask.astype(np.uint16),seed=0)
        np.testing.assert_array_equal(out,rgb);self.assertEqual(meta['replacement_regions'],0)
        mask[5,5]=True
        out,meta=render(rgb,mask,mask.astype(np.uint16),seed=0)
        self.assertEqual(meta['unresolved_texture_regions'],1)
        mask[10:50,10:50]=True;mask[5,5]=False;mask[25:35,25:35]=False
        out,meta=render(rgb,mask,mask.astype(np.uint16),seed=0)
        np.testing.assert_array_equal(out[~mask],rgb[~mask])
        for seed in [True,-1,2**128,float('nan')]:
            with self.assertRaises(ValueError):render(rgb,mask,mask.astype(np.uint16),seed=seed)
        for limit,reason in [('MAX_REGION_PIXELS','pixel_limit'),('MAX_BOUNDING_PIXELS','bbox_pixel_limit')]:
            with patch('photo_synthetic_replacement_v5.'+limit,3):
                with self.assertRaisesRegex(ValueError,reason):render(rgb,mask,mask.astype(np.uint16),seed=0)
        mask[29:32]=False
        with self.assertRaisesRegex(ValueError,'connected'):render(rgb,mask,mask.astype(np.uint16),seed=0)


if __name__=='__main__':
    cv2.setNumThreads(4)
    unittest.main()
