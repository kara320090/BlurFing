import unittest
import numpy as np
from scipy import ndimage
from photo_generated_detail_v27 import render
from photo_synthetic_replacement_v19 import render as legacy


class GeneratedDetailTests(unittest.TestCase):
    def scene(self):
        rgb=np.full((150,220,3),[206,151,143],np.uint8)
        labels=np.zeros(rgb.shape[:2],np.uint16)
        labels[15:135,10:100]=1;labels[15:135,120:210]=2
        return rgb,labels

    def test_only_designated_generated_surface_changes_and_outside_is_exact(self):
        rgb,labels=self.scene();before=rgb.copy();mask=labels>0
        reference,_=legacy(rgb,mask,labels,seed=123)
        actual,report=render(rgb,mask,labels,seed=123,detail_regions=[1])
        np.testing.assert_array_equal(actual[labels==2],reference[labels==2])
        np.testing.assert_array_equal(actual[~mask],rgb[~mask])
        np.testing.assert_array_equal(rgb,before)
        self.assertTrue(np.any(actual[labels==1]!=reference[labels==1]))
        self.assertFalse(report['generated_detail_policy']['original_fingerprint_reconstruction'])
        self.assertFalse(report['generated_detail_policy']['source_ridge_pixels_used'])
        # Inspect actual quantized output in the interior, not just a success flag.
        interior=ndimage.binary_erosion(labels==1,iterations=12)
        def energy(image):
            gray=image.astype(float).mean(axis=2)
            band=ndimage.gaussian_filter(gray,.65)-ndimage.gaussian_filter(gray,3.2)
            return float(np.std(band[interior]))
        self.assertGreater(energy(actual),energy(reference)*1.5)
        self.assertGreater(energy(actual),1.)

    def test_empty_selection_preserves_legacy_pixels_and_report(self):
        rgb,labels=self.scene();expected,old=legacy(rgb,labels>0,labels,seed=123)
        actual,new=render(rgb,labels>0,labels,seed=123)
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(old,new)

    def test_selected_region_route_uses_preferred_material_and_preserves_other_region(self):
        from photo_visibility_reviewed_apply_v1 import render_selected_regions
        rgb,labels=self.scene();before=rgb.copy();selected=[1,2]
        rows=[dict(region_id=rid,status='pending_render') for rid in selected]
        expected,_=render(rgb,labels>0,labels,seed=123,detail_regions=[1])
        actual,applied,report=render_selected_regions(
            rgb,labels,selected,rows,seed=123,generated_detail_regions=[1])
        np.testing.assert_array_equal(actual,expected)
        np.testing.assert_array_equal(applied,labels>0)
        np.testing.assert_array_equal(actual[~applied],rgb[~applied])
        np.testing.assert_array_equal(rgb,before)
        self.assertEqual(rows,[dict(region_id=rid,status='pending_render') for rid in selected])
        policy=report['renderer']['generated_detail_policy']
        self.assertEqual(policy['region_ids'],[1])
        self.assertEqual(policy['version'],'visible_generated_surface_detail_v27_experimental')

    def test_invalid_selection_and_seed_are_rejected(self):
        rgb,labels=self.scene()
        for selected in ([1,1],[True],[0],[-1],[1.5],'1'):
            with self.assertRaises(ValueError):render(rgb,labels>0,labels,detail_regions=selected)
        for seed in (-1,True,2**128):
            with self.assertRaises(ValueError):render(rgb,labels>0,labels,seed=seed,detail_regions=[1])


if __name__=='__main__':unittest.main()
