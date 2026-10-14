"""Synthetic ownership/geometry regression, not anatomical accuracy evidence."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from scipy import ndimage
from finger_body_distal_estimator import estimate,validate_candidate_context_allocation
from photo_candidate_context_v1 import candidate_contexts, plan_candidate_scale


def parent(pad, body, index=1):
    return dict(candidate_id=f'body-0001-part-{index:04d}', mask=pad, body_mask=body,
                component=1, watershed_part=index, major_axis_yx=[1,0], working_scale=1.,
                metadata_coordinate_system='working_image_pixels',
                context_coordinate_system='encoded_original_pixels', reject_reason=None)


class EstimatorContextTests(unittest.TestCase):
    def test_context_budget_planned_before_native_mask_and_geometry_allocation(self):
        audit=validate_candidate_context_allocation(4000,3000,4)
        self.assertLess(audit['estimated_total_bytes'],audit['max_estimated_bytes'])
        with self.assertRaisesRegex(ValueError,'candidate_context_memory_limit_exceeded'):
            validate_candidate_context_allocation(4000,3000,100)
        body,tip=self.masks()
        with patch('finger_body_distal_estimator.MAX_ESTIMATED_WORKING_BYTES',1), \
             patch('finger_body_distal_estimator.component_pad',side_effect=AssertionError('must fail before geometry')):
            with self.assertRaisesRegex(ValueError,'candidate_context_memory_limit_exceeded'):
                estimate(body,tip,preserve_candidates=True)

    def masks(self):
        body=np.zeros((250,200),bool)
        body[40:240,25:75]=True;body[40:240,125:175]=True;body[200:240,25:175]=True
        tip=np.zeros_like(body);tip[40:65,25:75]=True;tip[40:65,125:175]=True
        return body,tip

    def test_default_geometry_and_metadata_unchanged_with_optional_context(self):
        body,tip=self.masks();snapshots=body.copy(),tip.copy()
        default=estimate(body,tip);context=estimate(body,tip,preserve_candidates=True)
        np.testing.assert_array_equal(default['mask'],context['mask'])
        self.assertEqual(len(context['regions']),2)
        excluded={'candidate_id','body_mask','watershed_part','context_coordinate_system'}
        for old,new in zip(default['regions'],context['regions']):
            self.assertEqual(set(old),set(new)-excluded)
            for key in old:
                if isinstance(old[key],np.ndarray):np.testing.assert_array_equal(old[key],new[key])
                else:self.assertEqual(old[key],new[key])
        contexts=candidate_contexts(context,body)
        self.assertEqual([r['candidate_id'] for r in contexts],['body-0001-part-0001','body-0001-part-0002'])
        self.assertFalse(np.any(contexts[0]['body']&contexts[1]['body']))
        np.testing.assert_array_equal(contexts[0]['body']|contexts[1]['body'],body)
        np.testing.assert_array_equal(body,snapshots[0]);np.testing.assert_array_equal(tip,snapshots[1])

    def test_downsampled_context_is_native_observed_subset_and_deterministic(self):
        body,tip=self.masks();body=cv2.resize(body.astype('uint8'),(803,1003),interpolation=cv2.INTER_NEAREST)>0
        tip=cv2.resize(tip.astype('uint8'),(803,1003),interpolation=cv2.INTER_NEAREST)>0
        first=estimate(body,tip,preserve_candidates=True);second=estimate(body,tip,preserve_candidates=True)
        rows=candidate_contexts(first,body)
        for a,b in zip(first['regions'],second['regions']):
            self.assertEqual(a['candidate_id'],b['candidate_id'])
            np.testing.assert_array_equal(a['body_mask'],b['body_mask'])
            if a.get('mask') is not None:np.testing.assert_array_equal(a['mask'],b['mask'])
        self.assertTrue(all(not np.any(r['body']&~body) for r in rows))
        np.testing.assert_array_equal(first['mask'],estimate(body,tip)['mask'])

    def test_geometry_rejected_candidate_still_has_identity_and_body(self):
        body=np.zeros((100,100),bool);body[20:80,20:80]=True
        result=estimate(body,np.zeros_like(body),preserve_candidates=True)
        rows=candidate_contexts(result,body)
        self.assertEqual(len(rows),1);self.assertIsNotNone(rows[0]['reject_reason'])
        self.assertIsNone(rows[0]['pad']);np.testing.assert_array_equal(rows[0]['body'],body)


class CandidateOwnershipTests(unittest.TestCase):
    def fixture(self):
        first=np.zeros((512,640),bool);first[150:350,120:320]=True
        second=np.zeros_like(first);second[150:350,320:520]=True
        body1=np.zeros_like(first);body1[:,100:320]=True
        body2=np.zeros_like(first);body2[:,320:540]=True
        return first,second,body1,body2

    def test_touching_candidates_keep_two_ids_even_when_union_is_connected(self):
        a,b,ba,bb=self.fixture();self.assertEqual(ndimage.label(a|b)[1],1)
        rows=candidate_contexts(dict(mask=a|b,regions=[parent(a,ba),parent(b,bb,2)]),ba|bb)
        self.assertEqual(len(rows),2);self.assertTrue(all(r['reject_reason'] is None for r in rows))
        np.testing.assert_array_equal(rows[0]['pad'],a);np.testing.assert_array_equal(rows[1]['pad'],b)

    def test_disconnected_pieces_keep_one_candidate_and_scale(self):
        a,_,ba,_=self.fixture();plan=plan_candidate_scale(a,1)
        fragmented=a.copy();fragmented[10,150]=True
        row=candidate_contexts(dict(mask=fragmented,regions=[parent(fragmented,ba)]),ba)[0]
        self.assertEqual(row['candidate_id'],'body-0001-part-0001')
        fragmented_plan=plan_candidate_scale(fragmented,1)
        self.assertEqual(fragmented_plan['native_fragment_count'],2)
        self.assertEqual(fragmented_plan['working_scale'],plan['working_scale'])
        self.assertEqual(fragmented_plan['working_shape'],plan['working_shape'])
        self.assertEqual(int(row['pad'].sum()),int(a.sum())+1)

    def test_pad_overlap_rejects_every_involved_candidate_without_assigning_owner(self):
        a,b,ba,bb=self.fixture();b[:,319]|=a[:,319];bb[:,319]=ba[:,319]
        rows=candidate_contexts(dict(mask=a|b,regions=[parent(a,ba),parent(b,bb,2)]),ba|bb)
        self.assertEqual([r['reject_reason'] for r in rows],['candidate_pad_ownership_overlap']*2)

    def test_body_overlap_rejected_even_if_pads_are_disjoint(self):
        a,b,ba,bb=self.fixture();ba[-5:,320:330]=True
        rows=candidate_contexts(dict(mask=a|b,regions=[parent(a,ba),parent(b,bb,2)]),ba|bb)
        self.assertEqual([r['reject_reason'] for r in rows],['candidate_body_ownership_overlap']*2)

    def test_invalid_identity_union_and_body_are_contract_errors(self):
        a,b,ba,bb=self.fixture()
        variants=[dict(mask=a|b,regions=[parent(a,ba),parent(b,bb)]),
                  dict(mask=a|b,regions=[parent(a,ba)]),
                  dict(mask=a,regions=[parent(a,b)])]
        for result in variants:
            with self.assertRaises(ValueError):candidate_contexts(result,ba|bb)

    def test_tiny_candidate_resource_failure_does_not_affect_other_plan(self):
        a,_,_,_=self.fixture();tiny=np.zeros_like(a);tiny[10,10]=True
        large=plan_candidate_scale(a,2);small=plan_candidate_scale(tiny,1)
        self.assertEqual(large['status'],'planned')
        self.assertEqual(small['reject_reason'],'adapter_memory_limit_exceeded')
        for invalid in [np.zeros((2,2),bool),np.ones((2,2),np.uint8),np.ones((2,),bool)]:
            with self.assertRaises(ValueError):plan_candidate_scale(invalid,1)


if __name__=='__main__':unittest.main()
