"""Functional structure gate contracts, not privacy/security success tests."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
import fingerprint_structure_check as structure


def features(count):
    return [dict(x=20+i*20,y=40,type='ending') for i in range(count)]


class FunctionalGateTests(unittest.TestCase):
    def test_feature_loss_does_not_become_protection_success(self):
        for count in [0,6,9]:
            result=structure.assess_structure(features(13),features(count),.99)
            self.assertFalse(result['structure_change_passed'])
            self.assertEqual(result['reason'],'insufficient_features')
            self.assertFalse(result['privacy_validated'])
            self.assertFalse(result['identity_matching_performed'])

    def test_unchanged_points_rejected_even_if_skeleton_changes(self):
        result=structure.assess_structure(features(13),features(13),.99)
        self.assertTrue(result['normal_features']);self.assertFalse(result['structure_change_passed'])
        self.assertEqual(result['minutiae']['similarity'],1.)

    def boundary_case(self):
        before=features(10);after=copy.deepcopy(before);after[-1]['y']+=20
        return before,after

    def test_current_count_dice_and_skeleton_boundaries(self):
        before,after=self.boundary_case()
        result=structure.assess_structure(before,after,.05)
        self.assertTrue(result['structure_change_passed'])
        self.assertEqual(result['minutiae']['similarity'],.9)
        self.assertEqual(result['minutiae']['added']+result['minutiae']['removed'],2)
        self.assertFalse(structure.assess_structure(before,after,.0499)['structure_change_passed'])

    def test_one_to_one_matching_and_feature_order(self):
        before,after=self.boundary_case();saved=copy.deepcopy((before,after))
        expected=structure.assess_structure(before,after,.05)
        shuffled=structure.assess_structure(before[::-1],after[::-1],.05)
        self.assertEqual(expected,shuffled);self.assertEqual((before,after),saved)
        # Duplicates cannot consume the same target feature twice.
        result=structure.assess_structure(features(1)*10,features(1),.99)
        self.assertEqual(result['minutiae']['matched'],1)

    def test_radius_is_measured_in_canonical_pixels(self):
        before=features(10);after=copy.deepcopy(before)
        for point in after:point['x']+=6
        self.assertEqual(structure.assess_structure(before,after,.5)['minutiae']['matched'],10)
        for point in after:point['x']+=.001
        self.assertEqual(structure.assess_structure(before,after,.5)['minutiae']['matched'],0)

    def test_point_types_are_part_of_the_structural_comparison(self):
        before=features(10);after=[p|dict(type='bifurcation') for p in before]
        result=structure.assess_structure(before,after,.5)
        self.assertEqual(result['minutiae']['matched'],0)
        self.assertTrue(result['structure_change_passed']);self.assertFalse(result['privacy_validated'])

    def test_nonfinite_skeleton_fraction_does_not_pass(self):
        before,after=self.boundary_case()
        self.assertFalse(structure.assess_structure(before,after,float('nan'))['structure_change_passed'])


class ExtractorAssociationTests(unittest.TestCase):
    def test_reversed_extractor_order_keeps_original_and_modified_keys(self):
        image=np.full((300,300,3),[180,100,85],np.uint8)
        skeleton=np.eye(512,dtype=bool)
        def extractor(images,pairs,**kwargs):
            self.assertEqual(set(images),{'Original','Modified'});self.assertEqual(pairs,[])
            with Image.open(images['Original']) as frame:size=frame.width
            self.assertEqual(size,200)
            rows=[]
            for key,count in [('Modified',6),('Original',13)]:
                rows.append(dict(key=key,status='ok',template=dict(width=size,height=size,
                    positionsX=list(range(10,10+count)),positionsY=[20]*count,types=['E']*count)))
            return dict(images=rows)
        with tempfile.TemporaryDirectory() as folder,patch.object(structure,'OUT',Path(folder)), \
             patch.object(structure,'estimate_finger_width',return_value=dict(status='estimated',width=400)), \
             patch.object(structure,'prepare_fingerprint',return_value=(dict(skeleton_full=skeleton),[],{})), \
             patch.object(structure,'run_matcher_job',extractor):
            result=structure.check_structure_change(image,image.copy(),[50,50,250,250])
        self.assertEqual(result['minutiae']['before_count'],13)
        self.assertEqual(result['minutiae']['after_count'],6)
        self.assertAlmostEqual(result['points_before'][0]['x'],10*512/200)
        self.assertEqual(result['points_before'][0]['type'],'ending')
        self.assertEqual(result['reason'],'insufficient_features')


if __name__=='__main__':unittest.main()
