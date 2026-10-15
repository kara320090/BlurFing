import unittest
from unittest.mock import patch
import numpy as np
import cv2
import photo_multiscale_observation_seeds_v1 as multi
import photo_spatial_observation_seeds_v1 as spatial
import photo_learned_pad_pipeline_v10 as pipeline
import photo_region_pipeline_v1 as shared
import test_photo_component_local_evidence_v1 as bindings


class MultiscaleTests(unittest.TestCase):
    def fixture(self):
        body=np.zeros((200,160),bool);body[10:190,20:140]=True
        mask=np.zeros_like(body);mask[30:150,40:120]=True
        return mask,body

    def test_complete_prefix_and_exact_largest_square(self):
        mask,body=self.fixture();before=body.copy();prefix=spatial.proposals(mask,body);rows=multi.proposals(mask,body)
        self.assertEqual(rows[:len(prefix)],prefix);self.assertGreater(len(rows),len(prefix));self.assertLessEqual(len(rows),24)
        self.assertEqual(rows,multi.proposals(mask,body));self.assertEqual(len(rows),len({tuple(r['box']) for r in rows}))
        for row in rows:
            y,x=row['center_yx'];a,b,c,d=row['box']
            self.assertTrue(mask[y,x]);self.assertTrue(body[b:d,a:c].all());self.assertEqual(c-a,d-b)
            self.assertTrue(0<=a<c<=body.shape[1] and 0<=b<d<=body.shape[0])
            if row.get('scale_rule')=='largest_contained_square':
                half=row['side']//2+1
                self.assertFalse(0<=x-half and 0<=y-half and x+half<=body.shape[1] and y+half<=body.shape[0] and body[y-half:y+half,x-half:x+half].all())
        np.testing.assert_array_equal(body,before)

    def test_internal_hole_and_raster_edge_never_enter_window(self):
        mask,body=self.fixture();body[90:93,82:84]=False;mask&=body
        for row in multi.proposals(mask,body):
            a,b,c,d=row['box'];self.assertTrue(body[b:d,a:c].all())
        full=np.ones((80,70),bool)
        for row in multi.proposals(full,full):
            a,b,c,d=row['box'];self.assertTrue(0<=a<c<=70 and 0<=b<d<=80)

    def test_invalid_and_no_eligible_inputs(self):
        mask=np.zeros((30,30),bool);mask[2,2]=True
        self.assertEqual(multi.proposals(mask,mask),[])
        with self.assertRaises(ValueError):multi.proposals(mask.astype(np.uint8),mask)

    def test_maximal_square_matches_exhaustive_nonconvex_geometry(self):
        yy,xx=np.mgrid[:50,:60]
        bodies=[np.ones((50,60),bool), (xx+yy>15)&(xx+yy<85),
                ~((xx>25)&(yy<22)),~((xx>22)&(xx<29)&(yy>20)&(yy<28))]
        for body in bodies:
            mask=body.copy();prefix=spatial.proposals(mask,body);rows=multi.proposals(mask,body)
            for row in prefix:
                y,x=row['center_yx'];bound=min(x,y,60-x,50-y)
                largest=max(h for h in range(1,bound+1) if body[y-h:y+h,x-h:x+h].all())
                if largest>row['side']//2:
                    self.assertIn([x-largest,y-largest,x+largest,y+largest],[r['box'] for r in rows])

    def test_additional_scale_after_EXIF_and_fractional_resize(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8)
        for orientation in range(1,9):
            upright=shared.orient(mask,orientation);shape,_=shared.validate_resize(*upright.shape,1.17)
            permission=cv2.resize(upright.astype(np.uint8),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
            owners=cv2.resize(shared.orient(body,orientation).astype(np.uint8),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
            prefix=spatial.proposals(permission,owners);calls=[]
            def observe(frame,box,allowed):
                self.assertEqual(frame.shape[:2],tuple(shape));np.testing.assert_array_equal(allowed,permission)
                calls.append(list(box));return (8.,{'scale':'added'},None) if len(calls)>len(prefix) else (None,{},None)
            with patch.object(pipeline,'observed_component_pitch',side_effect=observe),patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
                artifact,_=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,orientation,'0'*64,dict(working_scale=1.17,component=1),dict(axis_native_yx=[1.,0.]))
            self.assertEqual(calls[:len(prefix)],[r['box'] for r in prefix]);self.assertEqual(artifact['regions'][0]['working_seed'],calls[-1])

    def test_all_prior_failures_then_new_scale_is_observed(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8)
        prefix=spatial.proposals(mask,body);calls=[]
        def observer(frame,box,allowed):
            calls.append(list(box));np.testing.assert_array_equal(allowed,mask)
            return (8.,{'selected':'larger'},None) if len(calls)>len(prefix) else (None,{},None)
        with patch.object(pipeline,'observed_component_pitch',side_effect=observer),patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
            artifact,geometry=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,1,'0'*64,dict(working_scale=1.,component=1),dict(axis_native_yx=[1.,0.]))
        self.assertEqual(calls[:len(prefix)],[r['box'] for r in prefix]);self.assertEqual(len(calls),len(prefix)+1)
        self.assertEqual(artifact['regions'][0]['working_seed'],calls[-1]);self.assertFalse(geometry['permission_mask_expanded'])

    def test_first_prior_success_does_not_probe_new_scales(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8);calls=[]
        def observer(*args):calls.append(True);return 8.,{'selected':'original'},None
        with patch.object(pipeline,'observed_component_pitch',side_effect=observer),patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
            artifact,_=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,1,'0'*64,dict(working_scale=1.,component=1),dict(axis_native_yx=[1.,0.]))
        self.assertEqual(len(calls),1);self.assertEqual(artifact['regions'][0]['working_seed'],spatial.proposals(mask,body)[0]['box'])


class MultiscaleRendererBindings(bindings.RendererBindingTests):
    def setUp(self):
        binding=patch.object(bindings,'pipeline',pipeline);binding.start();self.addCleanup(binding.stop)


if __name__=='__main__':unittest.main()
