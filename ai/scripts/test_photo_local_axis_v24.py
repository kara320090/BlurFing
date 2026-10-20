import unittest
from unittest.mock import patch
import numpy as np
from photo_local_axis_v24 import local_geometry,recover


class LocalAxisTests(unittest.TestCase):
    def fixture(self):
        y,x=np.indices((180,240))
        pad=((x-120)/18)**2+((y-45)/35)**2<=1
        owner=pad|((x>=100)&(x<=140)&(y>=45)&(y<=140))
        owner|=(y>=110)&(y<=160)&(x>=15)&(x<=225)  # wide fist, vertical finger
        return owner,pad

    def test_wide_parent_does_not_turn_vertical_finger_sideways(self):
        owner,pad=self.fixture();geo=local_geometry(owner,pad)
        self.assertLess(abs(geo['axis_xy'][0]),.01)
        self.assertLess(geo['axis_xy'][1],-.99)
        self.assertLess(geo['reference_width'],60)
        self.assertFalse(geo['whole_hand_major_axis_used'])
        rotated=local_geometry(np.rot90(owner).copy(),np.rot90(pad).copy())
        self.assertAlmostEqual(rotated['reference_width'],geo['reference_width'])
        np.testing.assert_allclose(rotated['axis_xy'],[geo['axis_xy'][1],-geo['axis_xy'][0]],atol=1e-8)

    def test_recovery_needs_observed_crease_and_only_changes_failed_owner(self):
        owner,pad=self.fixture();rgb=np.full((*owner.shape,3),140,np.uint8)
        context=dict(candidate_id='finger',body=owner,pad=pad)
        base=pad.copy();boundary=np.zeros_like(base)
        with patch('photo_local_axis_v24.observe_crease',return_value={'status':'unobserved'}):
            result,allowed,report=recover(rgb,base,boundary,[context],{'finger'})
        np.testing.assert_array_equal(result,base);self.assertFalse(allowed.any())
        self.assertFalse(report['regions'][0]['recovered'])
        with patch('photo_local_axis_v24.observe_crease',side_effect=AssertionError('must not run')):
            result,allowed,_=recover(rgb,base,boundary,[context],set())
        np.testing.assert_array_equal(result,base)
        with self.assertRaisesRegex(ValueError,'support_missing'):
            local_geometry(pad,pad)


if __name__=='__main__':
    unittest.main()
