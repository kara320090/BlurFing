import unittest
import numpy as np
from scipy import ndimage
from photo_continuous_surface_v28 import render
from photo_synthetic_replacement_v19 import render as legacy


class ContinuousSurfaceTests(unittest.TestCase):
    def scene(self):
        rgb=np.full((150,220,3),[206,151,143],np.uint8)
        labels=np.zeros(rgb.shape[:2],np.uint16)
        labels[15:135,10:100]=1;labels[15:135,120:210]=2
        return rgb,labels

    def test_selected_surface_only_and_reproducible_generated_detail(self):
        rgb,labels=self.scene();before=rgb.copy();mask=labels>0
        old,_=legacy(rgb,mask,labels,seed=123)
        actual,report=render(rgb,mask,labels,seed=123,detail_regions=[1])
        again,_=render(rgb,mask,labels,seed=123,detail_regions=[1])
        np.testing.assert_array_equal(actual,again)
        np.testing.assert_array_equal(actual[labels==2],old[labels==2])
        np.testing.assert_array_equal(actual[~mask],rgb[~mask])
        np.testing.assert_array_equal(rgb,before)
        self.assertTrue(np.any(actual[labels==1]!=old[labels==1]))
        self.assertFalse(report['continuous_surface_policy']['original_fingerprint_reconstruction'])
        other,_=render(rgb,mask,labels,seed=124,detail_regions=[1])
        self.assertTrue(np.any(actual[labels==1]!=other[labels==1]))

    def test_actual_quantized_surface_has_detail_without_bright_relief_spikes(self):
        rgb,labels=self.scene()
        actual,report=render(rgb,labels>0,labels,seed=123,detail_regions=[1])
        interior=ndimage.binary_erosion(labels==1,iterations=12)
        delta=actual[interior].astype(float)-rgb[interior].astype(float)
        self.assertLessEqual(float(abs(delta).max()),7.)
        self.assertGreater(float(delta.mean(axis=1).std()),.4)
        self.assertLess(float(delta.mean(axis=1).std()),4.)
        material=report['regions'][0]['skin_surface']
        self.assertFalse(material['generated_pores'])
        self.assertFalse(material['specular_reflection'])
        self.assertFalse(material['generated_ridge_interruptions'])
        self.assertFalse(material['natural_appearance_validated'])

    def test_empty_selection_is_exact_legacy(self):
        rgb,labels=self.scene()
        old,old_report=legacy(rgb,labels>0,labels,seed=123)
        new,new_report=render(rgb,labels>0,labels,seed=123)
        np.testing.assert_array_equal(new,old)
        self.assertEqual(new_report,old_report)

    def test_invalid_selection_seed_and_labels(self):
        rgb,labels=self.scene()
        for selected in ([True],[0],[-1],[1.5],[1,1],[[1]],'1'):
            with self.assertRaises(ValueError):render(rgb,labels>0,labels,detail_regions=selected)
        for seed in (-1,True,2**128):
            with self.assertRaises(ValueError):render(rgb,labels>0,labels,seed=seed,detail_regions=[1])
        with self.assertRaises(ValueError):render(rgb,labels>0,labels.astype(float))


if __name__=='__main__':unittest.main()
