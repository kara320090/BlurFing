"""Synthetic metric and encoded-coordinate checks; no private input required."""
import unittest
import numpy as np
from PIL import Image
from evaluate_detector_ground_truth import metrics, encoded

class MetricsTests(unittest.TestCase):
    def test_empty_prediction_is_miss_not_perfect_precision(self):
        gt=np.ones((4,5),bool);m=metrics(np.zeros_like(gt),gt)
        self.assertEqual(m['iou'],0);self.assertEqual(m['recall'],0)
        self.assertIsNone(m['precision']);self.assertIsNone(m['leakage_fraction'])
    def test_counts_and_leakage(self):
        gt=np.array([[1,1],[0,0]],bool);pred=np.array([[1,0],[1,0]],bool);m=metrics(pred,gt)
        self.assertAlmostEqual(m['iou'],1/3);self.assertEqual(m['precision'],.5)
        self.assertEqual(m['recall'],.5);self.assertEqual(m['false_positive_rate'],.5)
        self.assertEqual(m['leakage_fraction'],.5);self.assertEqual(m['mask_area_ratio'],1)
    def test_shape_mismatch(self):
        with self.assertRaisesRegex(ValueError,'shape_mismatch'):metrics(np.zeros((3,4),bool),np.zeros((4,3),bool))
    def test_exif_inverse_all_orientations(self):
        source=np.zeros((5,7),np.uint8);source[1,2]=255;source[3,5]=255
        methods={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
        for ori in range(1,9):
            with self.subTest(orientation=ori):
                image=Image.fromarray(source)
                if ori in methods:image=image.transpose(methods[ori])
                np.testing.assert_array_equal(encoded(np.asarray(image)>0,ori),source>0)

if __name__=='__main__':unittest.main()
