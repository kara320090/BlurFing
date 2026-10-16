import unittest
import numpy as np
from finger_body_distal_estimator import estimate
from photo_owner_hole_completion_v1 import complete_owner_holes


class OwnerHoleTests(unittest.TestCase):
    def fixture(self):
        y,x=np.indices((200,200))
        body=(((x-45)**2+(y-45)**2<=23**2)|((abs(x-45)<=23)&(y>=45))|
              ((x-145)**2+(y-45)**2<=23**2)|((abs(x-145)<=23)&(y>=45)))
        tip=body&(y<65);coarse=estimate(body,tip)['mask'];base=coarse.copy()
        base[40:47,39:45]=False;return base,coarse,body,tip

    def test_hole_fills_without_merging_two_fingers_or_losing_pixels(self):
        base,coarse,body,tip=self.fixture();before=base.copy()
        result,report=complete_owner_holes(base,coarse,body,tip,fill_holes=True)
        self.assertTrue(result[42,41]);self.assertFalse(result[:,95].any())
        self.assertFalse(np.any(base&~result));self.assertFalse(np.any(result&~body))
        np.testing.assert_array_equal(base,before);self.assertTrue(report['review_required'])

    def test_open_notch_is_not_filled_and_disabled_is_exact(self):
        base,coarse,body,tip=self.fixture();base[:47,39:45]=False
        result,_=complete_owner_holes(base,coarse,body,tip,fill_holes=True)
        self.assertFalse(result[42,41]);np.testing.assert_array_equal(result,base)
        result,_=complete_owner_holes(*self.fixture(),fill_holes=False)
        np.testing.assert_array_equal(result,self.fixture()[0])

    def test_all_quarter_turns_and_horizontal_mirror_preserve_hole_result(self):
        arrays=self.fixture();expected,_=complete_owner_holes(*arrays,fill_holes=True)
        for k in range(4):
            rotated=[np.rot90(a,k).copy() for a in arrays]
            rotated[1]=estimate(rotated[2],rotated[3])['mask']
            result,_=complete_owner_holes(*rotated,fill_holes=True)
            np.testing.assert_array_equal(result,np.rot90(expected,k))
        mirrored=[a[:,::-1].copy() for a in arrays];mirrored[1]=estimate(mirrored[2],mirrored[3])['mask']
        result,_=complete_owner_holes(*mirrored,fill_holes=True)
        np.testing.assert_array_equal(result,expected[:,::-1])

    def test_no_prediction_stays_empty_and_risk_is_explicit(self):
        base,coarse,body,tip=self.fixture();base[:]=False
        result,report=complete_owner_holes(base,coarse,body,tip,fill_holes=True)
        self.assertFalse(result.any());self.assertTrue(report['review_required'])
        self.assertGreater(report['coarse_pixels_not_covered'],0)
        self.assertTrue(all(r['candidate_has_no_protection'] for r in report['candidates']))

    def test_contracts_reject_stale_coarse_invalid_flags_and_exterior(self):
        arrays=list(self.fixture());arrays[1]=arrays[1].copy();arrays[1][42,41]^=True
        with self.assertRaisesRegex(ValueError,'coarse_binding'):complete_owner_holes(*arrays)
        with self.assertRaisesRegex(ValueError,'boolean'):complete_owner_holes(*self.fixture(),fill_holes=1)
        arrays=list(self.fixture());arrays[0][0,0]=True
        with self.assertRaisesRegex(ValueError,'outside_observed'):complete_owner_holes(*arrays)


if __name__=='__main__':unittest.main()
