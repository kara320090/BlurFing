"""Synthetic coordinate/ownership invariants, no real accuracy claims."""
import unittest
from unittest.mock import patch
import numpy as np
import photo_observed_boundary_proposals_v1 as proposals
from test_photo_terminal_branch_candidates_v1 import finger


class HalfplaneTests(unittest.TestCase):
    def test_native_pixel_centers_have_no_second_half_pixel_or_rounding(self):
        support=np.ones((6,7),bool)
        affine=np.array([[.7,0,-.15],[0,.6,-.2],[0,0,1.]])
        actual=proposals.clip_native_axial_halfplane(support,affine,1)
        expected=np.zeros_like(support);expected[:3]=True # .6*2-.2 == 1
        np.testing.assert_array_equal(actual,expected)
        np.testing.assert_array_equal(support,np.ones_like(support))

    def test_oblique_halfplane_and_mask_holes_preserved(self):
        support=np.ones((5,6),bool);support[1,1]=False
        affine=np.array([[1,-.5,2],[.5,1,0],[0,0,1.]])
        result=proposals.clip_native_axial_halfplane(support,affine,2)
        y,x=np.indices(support.shape)
        np.testing.assert_array_equal(result,support&(.5*x+y<=2))

    def test_malformed_and_nonfinite_affine_rejected(self):
        support=np.ones((6,7),bool)
        for affine in [np.eye(2),np.full((3,3),np.nan),np.zeros((3,3)),np.eye(3,dtype=complex)]:
            with self.assertRaises(ValueError):proposals.clip_native_axial_halfplane(support,affine,1)
        for row in [True,-1,np.nan,1.2]:
            with self.assertRaises(ValueError):proposals.clip_native_axial_halfplane(support,np.eye(3),row)
        with self.assertRaises(ValueError):proposals.clip_native_axial_halfplane(support.astype(np.uint8),np.eye(3),1)
        enormous=np.eye(3);enormous[1,0]=np.finfo(float).max
        with self.assertRaises(ValueError):proposals.clip_native_axial_halfplane(support,enormous,1)

    def test_allocation_guard_precedes_native_temporaries(self):
        huge=np.broadcast_to(np.array(True),(40000,1))
        with patch.object(proposals.np,'zeros_like',side_effect=AssertionError('must preflight')):
            with self.assertRaisesRegex(ValueError,'adapter_memory_limit_exceeded'):
                proposals.clip_native_axial_halfplane(huge,np.eye(3),1)


class ProposalTests(unittest.TestCase):
    def test_uniform_input_has_no_boundary_fallback_or_renderer_binding(self):
        body=finger();rgb=np.full((*body.shape,3),120,np.uint8)
        result=proposals.propose(rgb,body,np.zeros_like(body))
        self.assertFalse(result['mask'].any());self.assertTrue(result['regions'])
        self.assertTrue(all(r['mask'] is None for r in result['regions']))
        self.assertFalse(result['renderer_binding_allowed']);self.assertFalse(result['approved_for_use'])

    def test_unobserved_neighbor_still_blocks_shared_context_pixels(self):
        body=np.ones((10,10),bool);rgb=np.full((10,10,3),120,np.uint8)
        left=np.zeros_like(body);left[:,:4]=True;right=np.zeros_like(body);right[:,6:]=True
        contexts=[np.zeros_like(body),np.zeros_like(body)];contexts[0][:,:7]=True;contexts[1][:,3:]=True
        parent_rows=[dict(candidate_id=name,mask=mask,semantic_tip_overlap_pixels=0)
            for name,mask in [('a',left),('b',right)]]
        parent=dict(mask=left|right,regions=parent_rows)
        report=dict(pad_mask_pixel_sha256=proposals.context._pixel_sha(parent['mask']),rows=[
            dict(candidate_id='a',pad_frame=dict(touches=False),boundary=dict(status='observed',reason=None,
                 evidence=dict(selected_row=5),mapping=dict(encoded_source_to_axial_affine=np.eye(3).tolist()))),
            dict(candidate_id='b',pad_frame=dict(touches=True),boundary=dict(status='unobserved',reason='unobserved'))])
        def stream(*args):return iter(zip(parent_rows,contexts))
        before=body.copy(),rgb.copy()
        with patch.object(proposals.context,'diagnose',return_value=report), \
             patch.object(proposals.branch,'estimate',return_value=parent), \
             patch.object(proposals.context,'_contexts',side_effect=stream):
            result=proposals.propose(rgb,body,np.zeros_like(body))
        expected=np.zeros_like(body);expected[:6,:3]=True
        np.testing.assert_array_equal(result['mask'],expected)
        self.assertIsNone(result['regions'][1]['mask']);self.assertEqual(result['ambiguous_full_context_pixels'],40)
        self.assertFalse(result['semantic_tip_used_for_selection']);self.assertFalse(result['frame_used_for_selection'])
        np.testing.assert_array_equal(body,before[0]);np.testing.assert_array_equal(rgb,before[1])


if __name__=='__main__':unittest.main()
