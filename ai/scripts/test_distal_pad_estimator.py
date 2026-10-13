"""Synthetic optional-crease policy tests; no private annotations."""
import unittest
import numpy as np
from distal_pad_estimator_experimental import select_distal_extent


def region(crease=False):
    n=240;energy=np.full(n,10.);energy[155:]=3.;coherence=np.full(n,.8);coherence[155:]=.3;width=np.full(n,100.);width[155:]=125.;distance=np.full(n,80.);distance[155:]=100.
    signals=dict(texture_energy=energy,orientation_coherence=coherence,width=width,distance_width=distance,crease_response=np.zeros(n),crease_coverage=np.zeros(n))
    return dict(quality=dict(RGB_tip_hint_used=True,reject_reasons=[],crease_observed=crease),width_profile=dict(median_native=100),proximal_boundary=dict(signals={k:v.tolist() for k,v in signals.items()},analysis_to_native_scale=1.,tip_axial_row=0,search_rows=[110,239],diagnostic_peak_rows=dict(texture=[155])))

class DistalTests(unittest.TestCase):
    def test_optional_crease_accepts_texture_plus_geometry(self):
        r=select_distal_extent(region());self.assertIsNone(r['reject_reason']);self.assertEqual(r['source'],'multicue_distal_transition');self.assertNotIn('crease',r['contributing_cues'])
    def test_geometry_alone_not_fallback_approval(self):
        r=region();r['proximal_boundary']['signals']['texture_energy']=[10.]*240;r['proximal_boundary']['signals']['orientation_coherence']=[.8]*240
        self.assertIsNotNone(select_distal_extent(r)['reject_reason'])
    def test_texture_alone_insufficient(self):
        r=region();r['proximal_boundary']['signals']['width']=[100.]*240;r['proximal_boundary']['signals']['distance_width']=[80.]*240
        self.assertIsNotNone(select_distal_extent(r)['reject_reason'])
    def test_missing_tip_rejected(self):
        r=region();r['quality']['RGB_tip_hint_used']=False
        self.assertIsNotNone(select_distal_extent(r)['reject_reason'])
    def test_existing_crease_preserved(self):
        r=select_distal_extent(region(True));self.assertTrue(r['retain_existing_mask'])
    def test_deterministic_decision(self):
        self.assertEqual(select_distal_extent(region()),select_distal_extent(region()))

    def test_existing_overlap_rejection_not_overridden(self):
        r=region(True);r['quality']['reject_reason']='overlapping_pad_candidates'
        self.assertEqual(select_distal_extent(r)['reject_reason'],'overlapping_pad_candidates')
