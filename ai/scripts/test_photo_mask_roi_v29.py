import unittest
import numpy as np
from scipy import ndimage
from photo_lossless_io_v29 import lossless_io
import photo_mask_roi_v29 as original


class SparseMaskTests(unittest.TestCase):
    def test_exact_labels_distances_and_holes_including_all_image_edges(self):
        for edge in range(5):
            mask=np.zeros((700,900),bool)
            y,x=[(200,300),(0,300),(550,300),(200,0),(200,750)][edge]
            mask[y:y+130,x:x+140]=True;mask[y+40:y+65,x+35:x+60]=False
            mask[y+20:y+24,x+20:x+24]=False
            for structure in (None,np.ones((3,3),np.uint8)):
                expected,count=original._label(mask,structure)
                dist=original._distance(mask);holes=original._holes(mask,structure)
                with lossless_io():
                    actual,n=ndimage.label(mask,structure)
                    np.testing.assert_array_equal(actual,expected);self.assertEqual(n,count)
                    np.testing.assert_array_equal(ndimage.distance_transform_edt(mask),dist)
                    np.testing.assert_array_equal(ndimage.binary_fill_holes(mask,structure),holes)

    def test_empty_dense_and_index_output_fallbacks(self):
        for mask in (np.zeros((500,700),bool),np.ones((500,700),bool)):
            expected=original._distance(mask,return_indices=True)
            with lossless_io():
                actual=ndimage.distance_transform_edt(mask,return_indices=True)
                for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)
                labels,n=ndimage.label(mask)
                old,c=original._label(mask);np.testing.assert_array_equal(labels,old);self.assertEqual(n,c)
        self.assertFalse(original.enabled.get())

    def test_small_integer_membership_matches_numpy_for_masks_and_labels(self):
        rng=np.random.default_rng(18)
        for dtype in (np.uint8,np.uint16,np.int32):
            array=rng.integers(0,256,(500,700),dtype=dtype)
            for values in ([0,255],[1],[3,5,7],[],[0,1,2,3,4],[-1,999999]):
                for invert in (False,True):
                    expected=original._isin(array,values,invert=invert)
                    with lossless_io():actual=np.isin(array,values,invert=invert)
                    np.testing.assert_array_equal(actual,expected)


if __name__=='__main__':unittest.main()
