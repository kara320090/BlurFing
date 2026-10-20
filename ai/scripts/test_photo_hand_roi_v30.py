import unittest
import numpy as np
from photo_hand_roi_v30 import hand_box


class HandROIBoxTests(unittest.TestCase):
    def test_whole_hand_and_margin_stay_in_native_coordinates(self):
        points=np.column_stack((np.linspace(.35,.52,21),np.linspace(.50,.70,21)))
        box=hand_box([dict(normalized_xy=points.tolist())],3000,4000)
        self.assertIsNotNone(box);x0,y0,x1,y1=box
        native=points*[3000,4000]
        self.assertLess(x0,native[:,0].min());self.assertGreater(x1,native[:,0].max())
        self.assertLess(y0,native[:,1].min());self.assertGreater(y1,native[:,1].max())
        self.assertLess((x1-x0)*(y1-y0),3000*4000*.65)

    def test_two_hand_union_is_not_one_fingertip_rectangle(self):
        a=dict(normalized_xy=np.full((21,2),[.25,.5]).tolist())
        b=dict(normalized_xy=np.full((21,2),[.65,.5]).tolist())
        box=hand_box([a,b],3000,4000)
        self.assertLessEqual(box[0],750);self.assertGreaterEqual(box[2],1950)
        self.assertEqual(hand_box([],3000,4000),None)
        points=np.column_stack((np.linspace(0,1,21),np.linspace(0,1,21)))
        self.assertIsNone(hand_box([dict(normalized_xy=points)],3000,4000))

    def test_invalid_observations_do_not_authorize_a_crop(self):
        for values in (np.zeros((20,2)),np.full((21,2),np.nan),[['x','y']]*21):
            with self.assertRaises(ValueError):hand_box([dict(normalized_xy=values)],3000,4000)


if __name__=='__main__':unittest.main()
