import unittest
import numpy as np
from finger_body_distal_estimator import estimate
from photo_isolated_coarse_completion_v1 import complete_isolated_pad


class IsolatedCompletionTests(unittest.TestCase):
    def fixture(self):
        y,x=np.indices((200,160));body=((x-80)**2+(y-45)**2<=28**2)|((abs(x-80)<=28)&(y>=45))
        tip=body&(y<65);coarse=estimate(body,tip)['mask']
        learned=coarse.copy();learned[40:65,67:94]=False
        learned[125:130,75:85]=True
        return learned,coarse,body,tip

    def test_isolated_finger_restores_coarse_hole_and_preserves_learned_pixels(self):
        arrays=self.fixture();pins=[a.copy() for a in arrays]
        result,report=complete_isolated_pad(*arrays)
        self.assertTrue(result[50,80]);self.assertTrue(result[127,80])
        self.assertFalse(np.any(result&~arrays[2]));self.assertGreater(report['added_pixels'],0)
        self.assertEqual(report['status'],'isolated_coarse_added');self.assertFalse(report['anatomical_mask_coverage_verified'])
        for a,b in zip(arrays,pins):np.testing.assert_array_equal(a,b)

    def test_multiple_fingers_do_not_expand_into_palm_or_merge_permissions(self):
        learned,coarse,body,tip=self.fixture()
        body=np.concatenate((body,body),axis=1);tip=np.concatenate((tip,tip),axis=1)
        learned=np.concatenate((learned,learned),axis=1);coarse=estimate(body,tip)['mask']
        result,report=complete_isolated_pad(learned,coarse,body,tip)
        np.testing.assert_array_equal(result,learned);self.assertEqual(report['added_pixels'],0)
        self.assertEqual(report['reason'],'exactly_one_estimator_candidate_required')

    def test_no_frame_cut_is_ineligible_without_guessing_proximal_joint(self):
        learned,coarse,body,tip=self.fixture();body[-15:]=False;tip&=body;learned&=body
        coarse=estimate(body,tip)['mask'];result,report=complete_isolated_pad(learned,coarse,body,tip)
        np.testing.assert_array_equal(result,learned);self.assertEqual(report['reason'],'proximal_frame_cut_required')

    def test_quarter_turn_uses_encoded_pixel_axes(self):
        arrays=self.fixture();expected,_=complete_isolated_pad(*arrays)
        for k in range(4):
            rotated=[np.rot90(a,k).copy() for a in arrays]
            # Recompute the unchanged estimator at the new orientation, as the
            # real pipeline does; the completion must preserve all its pixels.
            rotated[1]=estimate(rotated[2],rotated[3])['mask']
            result,report=complete_isolated_pad(*rotated)
            self.assertEqual(report['status'],'isolated_coarse_added')
            self.assertFalse(np.any(rotated[0]&~result));self.assertFalse(np.any(rotated[1]&~result))
            self.assertTrue(result[np.rot90(np.indices(arrays[0].shape)[0]==50,k)&np.rot90(np.indices(arrays[0].shape)[1]==80,k)].all())

    def test_mask_binding_and_invalid_pixels_are_rejected(self):
        learned,coarse,body,tip=self.fixture()
        bad=coarse.copy();bad[50,80]=~bad[50,80]
        with self.assertRaisesRegex(ValueError,'coarse_binding'):complete_isolated_pad(learned,bad,body,tip)
        bad=learned.copy();bad[0,0]=True
        with self.assertRaisesRegex(ValueError,'outside_observed_body'):complete_isolated_pad(bad,coarse,body,tip)
        with self.assertRaisesRegex(ValueError,'mask_contract'):complete_isolated_pad(learned,coarse[:2],body,tip)
        with self.assertRaisesRegex(ValueError,'mask_contract'):complete_isolated_pad(learned.astype(np.uint8),coarse,body,tip)


if __name__=='__main__':unittest.main()
