"""Synthetic cue agreement and conservative rejection, no private images."""
import unittest
import numpy as np
from proximal_boundary_evidence import observe_proximal_boundary

class ProximalTests(unittest.TestCase):
    def inputs(self):
        mask=np.ones((240,100),bool);gray=np.full(mask.shape,120,np.float32);widths=np.full(240,100.);crease=np.zeros(240);coverage=np.zeros(240)
        return gray,mask,widths,crease,coverage
    def test_uniform_rejects(self):
        g,m,w,c,v=self.inputs();r=observe_proximal_boundary(g,m,w,0,239,100,c,v)
        self.assertFalse(r['observed']);self.assertEqual(r['reject_reason'],'proximal_boundary_unobserved')
    def test_crease_alone_insufficient(self):
        g,m,w,c,v=self.inputs();c[155]=8;v[155]=1;r=observe_proximal_boundary(g,m,w,0,239,100,c,v)
        self.assertFalse(r['observed']);self.assertTrue(r['candidates'][0]['cues']['crease'])
    def test_multiple_appearance_cues_accept(self):
        g,m,w,c,v=self.inputs();g[:155]+=20*np.sin(np.arange(100)[None,:]*2);c[155]=8;v[155]=1
        r=observe_proximal_boundary(g,m,w,0,239,100,c,v)
        self.assertTrue(r['observed']);self.assertEqual(r['selected_row'],155)
    def test_repeat_and_finite_signals(self):
        g,m,w,c,v=self.inputs();a=observe_proximal_boundary(g,m,w,0,239,100,c,v);b=observe_proximal_boundary(g,m,w,0,239,100,c,v)
        self.assertEqual(a,b)
        for signal in a['signals'].values():self.assertTrue(np.isfinite(signal).all())
