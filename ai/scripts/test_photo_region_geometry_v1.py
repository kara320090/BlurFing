"""Synthetic invariance contracts for opt-in geometry observations only."""
import unittest
import numpy as np
from photo_region_scale_plan_v1 import plan_region_scales
from contactless_finger_width_axis_v1 import estimate_finger_width_axis
from contactless_finger_width import estimate_finger_width


class RegionScaleTests(unittest.TestCase):
    def test_tiny_fragments_cannot_change_valid_region_plan(self):
        mask=np.zeros((512,512),bool);mask[150:350,150:350]=True
        expected=plan_region_scales(mask)['regions'][0]
        for count in [1,2,5,10]:
            noisy=mask.copy()
            for i in range(count):noisy[10,10+i*10]=True
            plan=plan_region_scales(noisy)
            main=next(r for r in plan['regions'] if r['bbox']==[150,150,350,350])
            self.assertEqual(main['working_scale'],expected['working_scale'])
            self.assertEqual(main['working_shape'],expected['working_shape'])
            self.assertEqual(main['status'],'planned')
            self.assertEqual(plan['detected_component_count'],count+1)
            self.assertTrue(all(r['reject_reason']=='adapter_memory_limit_exceeded' for r in plan['regions'] if r is not main))

    def test_frame_touching_mask_has_finite_observed_diameter(self):
        plan=plan_region_scales(np.ones((200,200),bool));region=plan['regions'][0]
        self.assertTrue(np.isfinite(region['working_scale']));self.assertEqual(region['observed_native_diameter'],200)

    def test_empty_foreground_and_invalid_contracts(self):
        self.assertEqual(plan_region_scales(np.zeros((64,64),bool))['regions'],[])
        for mask in [np.zeros((0,5),bool),np.zeros((5,5),np.uint8),np.zeros((5,),bool)]:
            with self.assertRaises(ValueError):plan_region_scales(mask)


class AxisWidthTests(unittest.TestCase):
    def image(self):
        image=np.full((1024,1024,3),35,np.uint8);image[:,312:712]=[180,100,85]
        return image

    def test_axis_observation_preserves_quarter_turn_width(self):
        image=self.image();box=[412,412,612,612]
        for turn,axis in enumerate([(1,0),(0,1),(-1,0),(0,-1)]):
            result=estimate_finger_width_axis(np.rot90(image,turn).copy(),box,axis)
            self.assertEqual(result['status'],'estimated');self.assertEqual(result['width'],400)
        self.assertEqual(estimate_finger_width(image,box)['width'],400)
        self.assertIsNone(estimate_finger_width(np.rot90(image).copy(),box)['width'])

    def test_diagonal_observed_width_and_source_preservation(self):
        y,x=np.indices((1024,1024));axis=np.array([1,1])/np.sqrt(2)
        image=np.full((1024,1024,3),35,np.uint8)
        image[np.abs((x-y)/np.sqrt(2))<200]=[180,100,85];before=image.copy()
        result=estimate_finger_width_axis(image,[412,412,612,612],axis)
        self.assertEqual(result['status'],'estimated');self.assertLessEqual(abs(result['width']-400),3)
        np.testing.assert_array_equal(image,before)

    def test_axis_normalization_and_invalid_values(self):
        image=self.image();box=[412,412,612,612]
        self.assertEqual(estimate_finger_width_axis(image,box,(9,0))['width'],400)
        for axis in [(0,0),(1,),[np.nan,1],[np.inf,1]]:
            with self.assertRaises(ValueError):estimate_finger_width_axis(image,box,axis)

    def test_boundary_rejection_is_diagnosed_without_relaxing_criteria(self):
        image=np.full((1024,1024,3),[180,100,85],np.uint8)
        result=estimate_finger_width_axis(image,[412,412,612,612],(1,0))
        self.assertEqual(result['status'],'insufficient_boundary_rows')
        self.assertIsNone(result['width']); self.assertEqual(len(result['rejected_samples']),7)
        self.assertTrue(all(r['reason']=='skin_interval_touches_sample_boundary' for r in result['rejected_samples']))


if __name__=='__main__':unittest.main()
