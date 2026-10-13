"""Synthetic geometry/metric tests only, never simulated pretrained accuracy."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from evaluate_model_segmentation_masks import extended_metrics, restore_probability_mask, binary_png, digest

class EvaluationTests(unittest.TestCase):
    def test_perfect_metrics(self):
        gt=np.zeros((20,40),bool);gt[2:10,2:10]=True;gt[2:10,25:33]=True
        m,c=extended_metrics(gt,gt)
        self.assertEqual(m['dice'],1);self.assertEqual(m['component_recall'],1);self.assertEqual(m['false_components'],0)
    def test_empty_prediction_is_missed(self):
        gt=np.ones((4,5),bool);m,_=extended_metrics(np.zeros_like(gt),gt)
        self.assertEqual(m['dice'],0);self.assertEqual(m['missed_gt_components'],1);self.assertEqual(m['gt_missed_pixel_ratio'],1)
    def test_merge_cannot_claim_two_components(self):
        gt=np.zeros((20,40),bool);gt[2:10,2:10]=True;gt[2:10,25:33]=True
        pred=gt.copy();pred[5,2:33]=True;m,_=extended_metrics(pred,gt)
        self.assertEqual(m['component_recall'],.5)
    def test_probability_inverse_rotation_and_threshold(self):
        p=np.zeros((8,6),np.float32);p[1:3,2:4]=1
        out=restore_probability_mask(p,(6,8),6)
        self.assertEqual(out.shape,(6,8));np.testing.assert_array_equal(out,np.rot90(p>0,1))
        self.assertFalse(restore_probability_mask(np.full((2,2),.5),(6,8),6).any())
    def test_probability_nan_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid_probability'):restore_probability_mask(np.array([[np.nan]]),(4,5),1)
    def test_probability_out_of_range_rejected(self):
        with self.assertRaises(ValueError):restore_probability_mask(np.array([[1.2]]),(4,5),1)
    def test_corrupt_shape_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'mask.png';Image.fromarray(np.zeros((4,5),np.uint8)).save(p)
            with self.assertRaisesRegex(ValueError,'mask_shape'):binary_png(p,(4,5),digest(p))
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):binary_png(p,(5,4),'0'*64)
    def test_nonbinary_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'mask.png';Image.fromarray(np.full((4,5),127,np.uint8)).save(p)
            with self.assertRaisesRegex(ValueError,'nonbinary'):binary_png(p,(5,4),digest(p))

if __name__=='__main__':unittest.main()
