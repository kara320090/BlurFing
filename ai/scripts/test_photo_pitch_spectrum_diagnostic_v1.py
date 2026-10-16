import unittest
import numpy as np
from photo_pitch_spectrum_diagnostic_v1 import diagnose_profile

class SpectrumTests(unittest.TestCase):
    def profile(self,period):return 130+50*np.cos(2*np.pi*np.arange(64)/period+.7)
    def test_known_sinusoid_peaks_are_within_one_frequency_bin(self):
        for period in [3.2,4.2,8.,12.5,23.8,26.4]:
            r=diagnose_profile(self.profile(period),period)
            self.assertLess(abs(r['dominant_bin']-64/period),1)
            self.assertFalse(r['fundamental_confirmed']);self.assertFalse(r['protection_gate_modified'])
    def test_short_period_double_alias_is_exposed_without_substitution(self):
        r=diagnose_profile(self.profile(3.2),6.36336812376976)
        self.assertEqual(r['dominant_bin'],20);self.assertEqual(r['longer_integer_harmonic_hypothesis'],2)
        self.assertGreater(abs(r['candidate_bin_offset']),8)
        self.assertEqual(r['candidate_period'],6.36336812376976)
        self.assertFalse(r['default_pitch_generated'])
    def test_brightness_polarity_amplitude_and_linear_ramp_do_not_shift_peak(self):
        a=self.profile(12.5);peak=diagnose_profile(a)['dominant_bin']
        for value in [a+60,-a,a*3,a+np.arange(64)*.2]:
            self.assertEqual(diagnose_profile(value)['dominant_bin'],peak)
    def test_flat_and_ramp_never_generate_period(self):
        for a in [np.ones(64)*130,np.arange(64)*.25+81,np.zeros(64)]:
            r=diagnose_profile(a,12.);self.assertEqual(r['status'],'unavailable');self.assertIsNone(r['dominant_spectral_period'])
    def test_large_second_harmonic_is_ambiguity_not_proof_of_wrong_fundamental(self):
        x=np.arange(64);a=128+10*np.cos(2*np.pi*x/16)+50*np.cos(2*np.pi*x/8)
        r=diagnose_profile(a,16.)
        self.assertEqual(r['dominant_bin'],8);self.assertFalse(r['fundamental_confirmed'])
        self.assertNotIn('rejected',r);self.assertNotIn('pitch_native',r)
    def test_bad_profile_and_candidate_contracts(self):
        for a in [np.ones((8,8)),np.ones(7),np.full(64,np.nan),np.ones(64,complex)]:
            with self.assertRaises(ValueError):diagnose_profile(a)
        for p in [True,0,-1,float('inf'),'12']:
            with self.assertRaises(ValueError):diagnose_profile(np.arange(64),p)
    def test_extreme_finite_amplitudes_are_safe_and_tiny_frequency_is_rejected(self):
        wave=np.cos(2*np.pi*np.arange(64)/8)
        with np.errstate(over='raise',invalid='raise',under='ignore'):
            for amplitude in [1e308,1e-300]:
                result=diagnose_profile(wave*amplitude,np.float32(8.))
                self.assertEqual(result['dominant_bin'],8)
                self.assertIs(type(result['candidate_period']),float)
        with self.assertRaisesRegex(ValueError,'representable_candidate_frequency'):
            diagnose_profile(wave,5e-324)

if __name__=='__main__':unittest.main()
