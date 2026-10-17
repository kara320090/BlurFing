"""Camera-pixel contrast, tiling, generated-only data flow and saved contracts."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from PIL import Image
from photo_native_texture_stats_v1 import observe,equalize_generated,missing_gains,kernel,SIGMAS
from photo_synthetic_replacement_v2 import geometry


class NativeTextureTests(unittest.TestCase):
    def plane(self,h=256,w=240):
        local=np.ones((h,w),bool);y,x=np.nonzero(local)
        return local,2*x/(w-1)-1,2*y/(h-1)-1

    def test_camera_pixel_period_survives_large_bounding_box(self):
        measurements=[]
        for size in (640,1280):
            local,u,v=self.plane(size,size)
            y,x=np.indices(local.shape)
            gray=np.floor(150+12*np.sin(x*2*np.pi/6.7)+.5).astype(np.uint8)
            pixels=np.repeat(gray[:,:,None],3,axis=2).reshape(-1,3)
            stats,meta=observe(pixels,local,u,v,size,size)
            measurements.append(stats.mean(axis=(0,1)))
            self.assertEqual(meta['analysis_scale'],1.)
            self.assertLessEqual(max(meta['maximum_filtered_tile_shape']),376)
        np.testing.assert_allclose(measurements[0][:2],measurements[1][:2],rtol=.08,atol=.03)

    def test_observer_halo_and_sampling_are_tile_partition_independent(self):
        local,u,v=self.plane(192,224)
        pixels=np.random.default_rng(3).integers(100,180,(local.sum(),3),dtype=np.uint8)
        a,meta=observe(pixels,local,u,v,224,192,tile=64)
        b,_=observe(pixels,local,u,v,224,192,tile=128)
        np.testing.assert_allclose(a,b,atol=1e-5)
        self.assertLessEqual(meta['maximum_statistics'],192)
        self.assertFalse(meta['source_filtered_raster_exported'])
        json.dumps(meta)

    def test_known_generated_sinusoid_has_expected_finite_kernel_gain(self):
        local,u,v=self.plane(160,192);y,x=np.nonzero(local)
        detail=np.sin(x*2*np.pi/8)
        delta=equalize_generated(detail,local,u,v,np.ones((1,1,4)))
        def response(s):
            k=kernel(s);axis=np.arange(-(len(k)//2),len(k)//2+1)
            return float(k@np.cos(axis*2*np.pi/8))
        inside=(x>62)&(x<129)&(y>62)&(y<98)
        np.testing.assert_allclose(delta[inside],detail[inside]*(response(SIGMAS[0])-response(SIGMAS[-1])),atol=1e-6)

    def test_missing_gain_is_bounded_and_does_not_boost_excess_bands(self):
        target=np.array([[[.4,.8,1.6,4.]]]);existing=np.array([[[.8,.4,.4,0.]]])
        np.testing.assert_array_equal(missing_gains(target,existing),[[[0.,1.,2.,2.]]])

    def test_generated_material_has_no_tile_seams_and_replays(self):
        local,u,v=self.plane(193,227);gains=np.array([[[.2,.5,1.,1.5]]])
        detail=np.random.default_rng(321).normal(size=local.sum())
        a=equalize_generated(detail,local,u,v,gains,tile=64)
        b=equalize_generated(detail,local,u,v,gains,tile=128)
        np.testing.assert_allclose(a,b,atol=1e-6)
        np.testing.assert_array_equal(a,equalize_generated(detail,local,u,v,gains,tile=64))
        self.assertGreater(float(np.std(a)),.05)

    def test_actual_RGB8_completion_reduces_known_middle_band_deficit(self):
        from photo_synthetic_replacement_v18 import render
        y,x=np.mgrid[:320,:256];mask=((x-128)/110)**2+((y-160)/145)**2<1
        rng=np.random.default_rng(45)
        detail=12*cv2.GaussianBlur(rng.normal(size=mask.shape).astype(np.float32),(0,0),1.3)
        detail+=25*cv2.GaussianBlur(rng.normal(size=mask.shape).astype(np.float32),(0,0),4.)
        rgb=np.clip(np.floor(np.array([170,135,125])+detail[:,:,None]+.5),0,255).astype(np.uint8)
        a,meta=render(rgb,mask,mask.astype(np.uint16),seed=211)
        item=meta['regions'][0]['camera_band_completion']
        target,before,after=[np.array(item[k]) for k in ('target','before','after')]
        self.assertLess(np.mean((after[:,:,1:]-target[:,:,1:])**2),np.mean((before[:,:,1:]-target[:,:,1:])**2)*.7)
        self.assertTrue(item['measurement_after_RGB8_quantization'])
        np.testing.assert_array_equal(a[~mask],rgb[~mask])

    def test_v18_actual_saved_RGB_native_metadata_and_fresh_output(self):
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        from replace_photo_synthetic_v1 import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,cache,rgb,mask,accepted,native,_,icc=SyntheticReplacementTests().cached(root,accepted=True)
            a,meta=run(source,cache,root/'out',renderer='v18',seed=91)
            b,_=run(source,cache,root/'replay',renderer='v18',seed=91)
            np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(a[accepted],native[accepted])
            np.testing.assert_array_equal(a[~mask],rgb[~mask])
            with Image.open(root/'out/synthetic.png') as im:
                np.testing.assert_array_equal(a,np.array(im));self.assertEqual(im.info['icc_profile'],icc)
                self.assertEqual(im.getexif()[274],6)
            self.assertFalse(meta['production_approved']);self.assertEqual(meta['synthetic_renderer'],'v18')
            with self.assertRaises(FileExistsError):run(source,cache,root/'out',renderer='v18')

    def test_v18_translation_and_background_do_not_affect_generated_region(self):
        from photo_synthetic_replacement_v18 import render
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture()
        a,_=render(rgb,mask,labels,seed=14)
        shifted=np.pad(rgb,((11,0),(17,0),(0,0)));m=np.pad(mask,((11,0),(17,0)))
        shifted[~m]=[0,255,0];b,_=render(shifted,m,m.astype(np.uint16),seed=14)
        np.testing.assert_array_equal(a[mask],b[m]);np.testing.assert_array_equal(b[~m],shifted[~m])

    def test_resource_and_nonfinite_contracts_fail_before_unbounded_filtering(self):
        huge=np.broadcast_to(np.bool_(True),(8192,8192))
        with patch('photo_native_texture_stats_v1.np.nonzero',side_effect=AssertionError('too early')):
            with self.assertRaises(ValueError):observe(np.zeros((1,3),np.uint8),huge,np.zeros(1),np.zeros(1),1,1)
        with self.assertRaises(ValueError):missing_gains(np.full((1,1,4),np.nan),np.ones((1,1,4)))
        local,u,v=self.plane(40,40);u[0]=np.nan
        with self.assertRaises(ValueError):equalize_generated(np.ones(local.sum()),local,u,v,np.ones((1,1,4)))

    def test_fixed_summaries_cannot_transfer_source_ridge_phase(self):
        import photo_synthetic_replacement_v18 as module
        local,u,v=self.plane(80,80);mask=local;labels=mask.astype(np.uint16)
        a=np.full((80,80,3),120,np.uint8);b=np.random.default_rng(9).integers(0,255,a.shape,dtype=np.uint8)
        def previous(rgb,mask,labels,seed=None):
            yy,xx=np.indices(mask.shape)
            field=np.repeat((150+3*np.sin(xx*2*np.pi/9))[:,:,None],3,axis=2).astype(np.uint8)
            return field,dict(seed=seed,regions=[dict(region_id=1,texture_style={})],source_dependency='fixture')
        calls=[]
        def fixed(*args,**kw):
            wanted=len(calls)%3==0;calls.append(1)
            return np.full((1,1,4),.8 if wanted else .1),dict(populated_cells=1)
        with patch.object(module,'previous_render',side_effect=previous),patch.object(module,'observe',side_effect=fixed), \
             patch.object(module,'photographic_skin',return_value=(np.full((mask.sum(),3),150.),{})), \
             patch.object(module,'boundary_ribbon',side_effect=lambda base,*args:(base,{})):
            x,_=module.render(a,mask,labels,seed=7);y,_=module.render(b,mask,labels,seed=7)
        np.testing.assert_array_equal(x,y);self.assertGreater(float(x.std()),.3)


if __name__=='__main__':
    cv2.setNumThreads(4)
    unittest.main()
