import unittest
import cv2
import numpy as np
from finger_body_distal_estimator import estimate,component_pad

class BodyDistalTests(unittest.TestCase):
    def masks(self):
        body=np.zeros((200,100),np.uint8);cv2.rectangle(body,(30,70),(70,199),1,-1);cv2.ellipse(body,(50,70),(20,30),0,0,360,1,-1)
        tip=body.astype(bool)&(np.indices(body.shape)[0]<90)
        return body.astype(bool),tip
    def test_class_1_only_truncated_finger(self):
        body,_=self.masks();result=estimate(body,np.zeros(body.shape,bool));self.assertTrue(result['mask'].any());self.assertFalse((result['mask']&~body).any())
    def test_class_2_auxiliary_and_determinism(self):
        body,tip=self.masks();a=estimate(body,tip);b=estimate(body,tip);self.assertTrue(np.array_equal(a['mask'],b['mask']));self.assertFalse((tip&~a['mask']).any());self.assertFalse((a['mask']&~body).any())
    def test_empty_fail_closed(self):
        mask=np.zeros((100,100),bool);self.assertFalse(estimate(mask,mask)['mask'].any())
    def test_bad_tip_subset(self):
        body,tip=self.masks();tip[0,0]=True
        with self.assertRaises(ValueError):estimate(body,tip)
    def test_rotation_geometry(self):
        body,tip=self.masks();original=estimate(body,tip)['mask']
        for k in [1,2,3]:
            rotated=estimate(np.rot90(body,k).copy(),np.rot90(tip,k).copy())['mask'];back=np.rot90(rotated,-k);intersection=(back&original).sum();union=(back|original).sum();self.assertGreater(intersection/union,.95)

    def terminal_widening(self,rows):
        body=np.zeros((120,160),bool);body[:,30:130]=True
        if rows:body[-rows:,:]=True
        tip=np.zeros_like(body);tip[:10,50:110]=True
        return body,tip

    def test_last_complete_widening_window_trims_proximal_rows(self):
        body,tip=self.terminal_widening(6)
        mask,meta=component_pad(body,tip)
        self.assertAlmostEqual(meta['distal_extent'],114.5)
        self.assertTrue(mask[114].any());self.assertFalse(mask[115:].any())
        self.assertFalse((mask&~body).any());self.assertFalse((tip&~mask).any())
        np.testing.assert_array_equal(estimate(body,tip)['mask'],mask)

    def test_terminal_window_preserves_quarter_turns_and_native_contract(self):
        body,tip=self.terminal_widening(6);expected=estimate(body,tip)['mask']
        for turn in [1,2,3]:
            result=estimate(np.rot90(body,turn).copy(),np.rot90(tip,turn).copy())
            np.testing.assert_array_equal(np.rot90(result['mask'],-turn),expected)

    def test_incomplete_run_is_not_accepted_as_complete(self):
        for rows in [0,5]:
            body,tip=self.terminal_widening(rows);mask,meta=component_pad(body,tip)
            self.assertAlmostEqual(meta['distal_extent'],119.)
            self.assertTrue(mask[-1].any())
        body,tip=self.terminal_widening(7);_,meta=component_pad(body,tip)
        self.assertAlmostEqual(meta['distal_extent'],113.5)

if __name__=='__main__':unittest.main()
