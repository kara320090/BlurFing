import unittest
from unittest.mock import patch
import numpy as np
import photo_learned_pad_pipeline_v3 as pipeline


class BodyScaleAdapterTests(unittest.TestCase):
    def test_body_scale_reaches_prepare_without_fragment_renormalization(self):
        rgb=np.zeros((201,201,3),np.uint8);body=np.zeros((201,201),bool);body[10:191,80:120]=True
        pad=np.zeros_like(body);pad[100:103,90:93]=True;gray=np.zeros_like(body,dtype=np.uint8)
        association=dict(axis_native_yx=[1.,0.]);full=dict(component=7,working_scale=200.)
        def prepare(local,gray,mask,owner,orientation,sha,plan,axis):
            self.assertEqual(plan['working_scale'],10.);self.assertEqual(plan['normalization']['observed_native_body_width'],40.)
            self.assertEqual(plan['component'],7);self.assertEqual(plan['mask_pixels'],9)
            return None,dict(reject_reason='coarse_pad_too_small_for_seed')
        with patch.object(pipeline.base.shared,'prepare_region',side_effect=prepare):
            artifact,geometry,plan,render=pipeline.prepare_scoped_region(rgb,gray,pad,body,1,'0'*64,full,association)
        self.assertIsNone(artifact);self.assertEqual(plan['working_scale'],10.);self.assertEqual(geometry['normalization']['coordinate_system'],'encoded_original_pixels')

    def test_unobserved_native_body_boundary_stops_before_crop_or_pitch(self):
        rgb=np.zeros((40,50,3),np.uint8);body=np.ones((40,50),bool);pad=np.zeros_like(body);pad[20,25]=True
        with patch.object(pipeline,'body_crop') as crop:
            artifact,geometry,plan,render=pipeline.prepare_scoped_region(rgb,np.zeros_like(body,np.uint8),pad,body,1,'0'*64,
                dict(component=1,working_scale=200.),dict(axis_native_yx=[1.,0.]))
        crop.assert_not_called();self.assertEqual(plan['reject_reason'],'native_body_width_boundary_unobserved')


if __name__=='__main__':unittest.main()
