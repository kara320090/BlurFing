import unittest
from unittest.mock import patch
import numpy as np
import photo_terminal_context_diagnostic_v1 as diagnostic
from test_photo_terminal_branch_candidates_v1 import finger,hand
import photo_terminal_branch_candidates_v2 as branch


class ContextTests(unittest.TestCase):
    def test_no_junction_halves_do_not_propagate_opposite_frame(self):
        body=finger();result=branch.estimate(body,body)
        contexts=list(diagnostic._contexts(body,result))
        self.assertEqual(len(contexts),1)
        parent,support=contexts[0]
        self.assertFalse(diagnostic._frame(support)['touches'])
        self.assertFalse(np.any(support&~body))
        self.assertTrue(np.any(parent['mask']&support))

    def test_frame_contacts_do_not_classify_or_remove_candidate(self):
        body=hand();rgb=np.full((*body.shape,3),120,np.uint8)
        expected=branch.estimate(body,body)['mask'].copy();before=rgb.copy(),body.copy()
        with patch.object(diagnostic,'observe_context_boundary',return_value=dict(status='unobserved')):
            result=diagnostic.diagnose(rgb,body,body)
        self.assertEqual(result['pad_mask_pixel_sha256'],diagnostic._pixel_sha(expected))
        self.assertTrue(all(r['anatomy_classification']=='unknown' for r in result['rows']))
        self.assertFalse(result['pad_mask_changed']);self.assertFalse(result['renderer_binding_allowed'])
        np.testing.assert_array_equal(rgb,before[0]);np.testing.assert_array_equal(body,before[1])

    def test_actual_anisotropic_resize_pixel_centers_and_inverse(self):
        resize,rotate=diagnostic._axis_mapping([37,51,1138,770],(470,720),[.6,.8])
        self.assertAlmostEqual(resize[0,0],720/1101);self.assertAlmostEqual(resize[1,1],470/719)
        points=np.array([[37,51,1],[1137,769,1],[381.25,415.75,1.]])
        affine=rotate@resize;result=points@affine.T
        np.testing.assert_allclose(result@np.linalg.inv(affine).T,points,atol=1e-10)
        mapped=points@resize.T
        self.assertAlmostEqual(mapped[0,0],.5*720/1101-.5)
        self.assertAlmostEqual(mapped[0,1],.5*470/719-.5)
        large=diagnostic._axis_mapping([0,0,120,240],(240,120),[1e308,0])[1]
        np.testing.assert_allclose(large,np.eye(3))

    def test_uniform_appearance_is_unobserved_with_valid_affine(self):
        body=finger();rgb=np.full((*body.shape,3),120,np.uint8)
        result=diagnostic.observe_context_boundary(rgb,body,[1,0])
        self.assertEqual(result['status'],'unobserved')
        self.assertIsNone(result['selected_boundary_source_xy_endpoints'])
        matrix=np.asarray(result['mapping']['encoded_source_to_axial_affine'])
        inverse=np.asarray(result['mapping']['axial_to_encoded_source_affine'])
        np.testing.assert_allclose(matrix@inverse,np.eye(3),atol=1e-10)

    def test_invalid_axis_or_support_rejected(self):
        body=finger();rgb=np.full((*body.shape,3),120,np.uint8)
        for axis in [[0,0],[np.nan,1],[1]]:
            with self.assertRaises(ValueError):diagnostic.observe_context_boundary(rgb,body,axis)
        with self.assertRaises(ValueError):diagnostic.observe_context_boundary(rgb,np.zeros_like(body),[1,0])

    def test_thin_valid_support_is_unobserved_without_aborting(self):
        for shape,axis in [((1,40),[1,0]),((40,1),[0,1])]:
            support=np.ones(shape,bool);rgb=np.full((*shape,3),120,np.uint8)
            result=diagnostic.observe_context_boundary(rgb,support,axis)
            self.assertEqual(result['status'],'unobserved')
            self.assertEqual(result['reason'],'context_axial_extent_unavailable')

    def test_support_lost_at_resize_is_unobserved(self):
        support=np.zeros((2000,2000),bool)
        support[[0,1001,1999,1001],[1001,0,1001,1999]]=True
        rgb=np.full((*support.shape,3),120,np.uint8)
        before=support.copy()
        result=diagnostic.observe_context_boundary(rgb,support,[1,0])
        self.assertEqual(result['status'],'unobserved')
        self.assertEqual(result['reason'],'context_support_lost_at_resize')
        self.assertFalse(result['mapping']['axial_mapping_available'])
        np.testing.assert_array_equal(support,before)

    def test_resource_preflight_precedes_hash_and_mask_scans(self):
        body=np.broadcast_to(np.array(True),(40000,1))
        rgb=np.broadcast_to(np.array([120,120,120],np.uint8),(40000,1,3))
        with patch.object(diagnostic,'_pixel_sha',side_effect=AssertionError('preflight before tobytes')):
            with self.assertRaisesRegex(ValueError,'adapter_memory_limit_exceeded'):
                diagnostic.diagnose(rgb,body,body)
        with self.assertRaisesRegex(ValueError,'adapter_memory_limit_exceeded'):
            diagnostic.observe_context_boundary(rgb,body,[1,0])


if __name__=='__main__':unittest.main()
