"""Synthetic body/color association contracts; no private performance claims."""
import hashlib
import unittest
from unittest.mock import patch
import numpy as np
from contactless_finger_width_axis_v1 import estimate_finger_width_axis
from contactless_finger_width_body_v1 import estimate_finger_width_body
import photo_region_pipeline_v1 as v1
import photo_region_pipeline_v2 as v2


class BodyWidthTests(unittest.TestCase):
    def fixture(self, background=(170,120,95)):
        mask=np.zeros((1024,1024),bool);mask[:,312:712]=True
        rgb=np.full((1024,1024,3),background,np.uint8);rgb[mask]=[180,100,85]
        return rgb,mask,[412,412,612,612]

    def test_body_limits_skin_colored_background_without_new_threshold(self):
        rgb,body,box=self.fixture()
        self.assertIsNone(estimate_finger_width_axis(rgb,box,(1,0))['width'])
        result=estimate_finger_width_body(rgb,box,(1,0),body)
        self.assertEqual(result['status'],'estimated');self.assertEqual(result['width'],400)
        self.assertEqual(len(result['samples']),7);self.assertFalse(result['thresholds_changed'])
        self.assertTrue(all(r['skin_interval_limited_by_body'] for r in result['samples']))

    def test_background_quarter_turn_and_input_preservation(self):
        for background in [(35,35,35),(170,120,95),(255,240,230)]:
            rgb,body,box=self.fixture(background)
            hashes=[hashlib.sha256(a.tobytes()).hexdigest() for a in [rgb,body]]
            for turn,axis in enumerate([(1,0),(0,1),(-1,0),(0,-1)]):
                vector=np.array(axis,np.float64)*9;before=vector.copy()
                result=estimate_finger_width_body(np.rot90(rgb,turn).copy(),box,vector,np.rot90(body,turn).copy())
                self.assertEqual(result['status'],'estimated');self.assertEqual(result['width'],400)
                np.testing.assert_array_equal(vector,before)
            self.assertEqual(hashes,[hashlib.sha256(a.tobytes()).hexdigest() for a in [rgb,body]])

    def test_real_clipping_is_not_rescued_by_rgb_evidence(self):
        rgb,body,box=self.fixture();body[:,:312]=True
        result=estimate_finger_width_body(rgb,box,(1,0),body)
        self.assertIsNone(result['width']);self.assertEqual(len(result['rejected_samples']),7)
        self.assertTrue(all(r['reason']=='body_interval_touches_sample_boundary' for r in result['rejected_samples']))

    def test_mask_alone_cannot_supply_missing_color_evidence(self):
        rgb,body,box=self.fixture();rgb[body]=[120,120,120]
        result=estimate_finger_width_body(rgb,box,(1,0),body)
        self.assertIsNone(result['width'])
        self.assertTrue(all(r['reason']=='no_associated_skin_near_seed_center' for r in result['rejected_samples']))

    def test_padding_cannot_rescue_actual_image_clipping(self):
        rgb=np.full((1024,1024,3),[180,100,85],np.uint8)
        body=np.zeros((1024,1024),bool);body[:,150:512]=True
        box=[262,412,462,612]
        result=estimate_finger_width_body(rgb,box,(1,0),body,image_shape=(1024,512))
        self.assertIsNone(result['width'])
        self.assertTrue(all(r['reason']=='body_interval_touches_sample_boundary' for r in result['rejected_samples']))
        for shape in [(1024,0),(1024,1025),(1024.,512),[1024],None]:
            if shape is None:continue
            with self.assertRaises(ValueError):estimate_finger_width_body(rgb,box,(1,0),body,image_shape=shape)

    def test_disconnected_nearby_body_does_not_extend_interval(self):
        rgb,body,box=self.fixture();body[:,730:930]=True
        result=estimate_finger_width_body(rgb,box,(1,0),body)
        self.assertEqual(result['width'],400)

    def test_diagonal_sampling_retains_width_and_existing_iqr_rule(self):
        y,x=np.indices((1024,1024));body=np.abs((x-y)/np.sqrt(2))<200
        rgb=np.full((1024,1024,3),[170,120,95],np.uint8);rgb[body]=[180,100,85]
        result=estimate_finger_width_body(rgb,[412,412,612,612],(1,1),body)
        self.assertEqual(result['status'],'estimated');self.assertLessEqual(abs(result['width']-400),3)
        unstable=np.zeros((1024,1024),bool)
        for row in range(1024):
            width=200 if row<512 else 700;unstable[row,512-width//2:512+width//2]=True
        result=estimate_finger_width_body(np.full(rgb.shape,[180,100,85],np.uint8),[412,412,612,612],(1,0),unstable)
        self.assertEqual(result['status'],'unstable_boundary_width')

    def test_invalid_body_and_axis_contracts(self):
        rgb,body,box=self.fixture()
        for mask in [body.astype(np.uint8),body[:-1],np.zeros_like(body)]:
            with self.assertRaises(ValueError):estimate_finger_width_body(rgb,box,(1,0),mask)
        for axis in [(0,0),(1,),[np.nan,1],[np.inf,1]]:
            with self.assertRaises(ValueError):estimate_finger_width_body(rgb,box,axis,body)
        misplaced=np.zeros_like(body);misplaced[:,10:100]=True
        with self.assertRaisesRegex(ValueError,'seed_center'):estimate_finger_width_body(rgb,box,(1,0),misplaced)


class AssociationAndBindingTests(unittest.TestCase):
    def parent(self,mask):return dict(mask=mask,reject_reason=None)

    def test_disconnected_body_selection_is_explicit_and_native(self):
        body=np.zeros((64,64),bool);body[5:55,5:25]=True;body[5:55,40:60]=True
        first=np.zeros_like(body);first[10:30,10:20]=True
        second=np.zeros_like(body);second[10:30,45:55]=True
        selected,meta=v2.associated_body(body,second,dict(estimator_region_index=2),[self.parent(first),self.parent(second)])
        self.assertEqual(meta['native_body_component'],2);self.assertEqual(meta['estimator_region_index'],2)
        self.assertTrue(selected[50,50]);self.assertFalse(selected[50,15])

    def test_connected_multi_finger_parent_is_rejected(self):
        body=np.ones((64,64),bool);first=np.zeros_like(body);first[5:20,5:20]=True
        second=np.zeros_like(body);second[40:55,40:55]=True
        with self.assertRaisesRegex(ValueError,'multiple_or_unmatched'):
            v2.associated_body(body,first,dict(estimator_region_index=1),[self.parent(first),self.parent(second)])
        with self.assertRaisesRegex(ValueError,'association_contract'):
            v2.associated_body(np.zeros_like(body),first,dict(estimator_region_index=1),[])

    def test_v2_uses_shared_guard_and_explicit_version(self):
        with patch.object(v1,'protect_photo_regions',return_value=('image','report')) as api:
            self.assertEqual(v2.protect_photo_regions('source','fresh',detect_only=True),('image','report'))
        self.assertEqual(api.call_args.kwargs['_pipeline_version'],v2.VERSION)
        self.assertIs(api.call_args.kwargs['_region_renderer'],v2.render_body_region)
        self.assertTrue(api.call_args.kwargs['detect_only'])


if __name__=='__main__':unittest.main()
