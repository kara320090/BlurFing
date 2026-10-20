import unittest
import cv2
import numpy as np
from colfispoof_raw_semantics import prepare,restore,vote_masks
from colfispoof_body_semantics import predict_body


class SamplingTests(unittest.TestCase):
    def test_selected_label_indices_exactly_reproduce_classify_then_nearest_resize(self):
        rng=np.random.default_rng(38)
        for height,width in ((33,77),(77,33),(55,55),(19,64)):
            rgb=np.zeros((height,width,3),np.uint8)
            rows=[rng.integers(0,5,(h,w),dtype=np.int64) for h,w in ((131,127),(128,133),(67,71),(115,121))]
            bodies=[];tips=[]
            for k,labels in enumerate(rows):
                _,g=prepare(np.rot90(rgb,-k).copy())
                bodies.append(restore(np.isin(labels,[1,2]).astype(np.uint8)*2,g,k));tips.append(restore(labels,g,k))
            class Model:
                def __init__(self):self.i=0
                def run(self,image):
                    row=rows[self.i];self.i+=1;return None,row
            class Runtime:pass
            runtime=Runtime();runtime.model=Model()
            actual=predict_body(runtime,rgb)
            np.testing.assert_array_equal(actual['body'],vote_masks(bodies))
            np.testing.assert_array_equal(actual['tip'],vote_masks(tips))


if __name__=='__main__':unittest.main()
