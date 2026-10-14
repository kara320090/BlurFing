"""Synthetic cue agreement and conservative rejection, no private images."""
import unittest
import json
import numpy as np
import cv2
from scipy.ndimage import gaussian_filter1d
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

    def test_same_RGB_mask_gap_cannot_create_appearance_transition(self):
        g,m,w,c,v=self.inputs();g[:]+=20*np.sin(np.arange(100)[None,:]*2);g[152:156]-=45
        m[156:186]=False;w[156:186]=0
        smooth=cv2.GaussianBlur(g,(0,0),2.5)
        residual=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=18)-smooth
        for row in range(len(g)):
            xs=np.flatnonzero(m[row])
            if not len(xs):continue
            a,b=np.percentile(xs,[20,80]).astype(int);values=residual[row,a:b+1]
            c[row]=np.median(values);v[row]=np.mean(values>2)
        c=gaussian_filter1d(c,1.5)
        observed=observe_proximal_boundary(g,m,w,0,239,100,c,v)
        self.assertFalse(observed['observed'])
        self.assertTrue(any(q.get('reject_reason')=='appearance_window_mask_support_unavailable'
                            for q in observed['candidates']))
        control=observe_proximal_boundary(g,np.ones_like(m),np.full(240,100.),0,239,100,c,v)
        self.assertFalse(control['observed'])
        json.dumps(observed,allow_nan=False)

    def test_validity_uses_exact_smoothing_footprint_and_preserves_other_rows(self):
        for hole in [50,129,130,179,180]:
            with self.subTest(hole=hole):
                g,m,w,c,v=self.inputs();g[:155]+=20*np.sin(np.arange(100)[None,:]*2)
                c[155]=8;v[155]=1;m[hole]=False;w[hole]=0
                result=observe_proximal_boundary(g,m,w,0,239,100,c,v)
                candidate=next(q for q in result['candidates'] if q['row']==155 and q['slope']==0)
                self.assertEqual(candidate['observation_valid'],hole not in [130,179])
                self.assertEqual(result['observed'],hole not in [130,179])
                self.assertEqual(result['appearance_smoothing_radius_rows'],10)

    def test_central_span_background_is_not_foreground_appearance(self):
        g=np.full((240,200),120,np.float32);x=np.arange(200)[None,:]
        columns=(np.arange(200)<51)|(np.arange(200)>=150)
        g[:,columns]+=(20*np.sin(x*2))[:,columns];g[152:156]-=45
        mask=np.zeros(g.shape,bool);mask[:156,:80]=True;mask[156:,:10]=True;mask[156:,190:]=True
        widths=np.array([np.ptp(np.flatnonzero(row))+1 for row in mask],float)
        smooth=cv2.GaussianBlur(g,(0,0),2.)
        response=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=14.4)-smooth
        crease,coverage=np.zeros(240),np.zeros(240)
        for row in range(240):
            a,b=np.percentile(np.flatnonzero(mask[row]),[20,80]).astype(int)
            values=response[row,a:b+1];crease[row]=np.median(values);coverage[row]=np.mean(values>2)
        crease=gaussian_filter1d(crease,1.2)
        result=observe_proximal_boundary(g,mask,widths,0,239,80.,crease,coverage)
        self.assertFalse(result['observed'])
        self.assertFalse(any(result['raw_valid_mask_rows'][156:]))
        self.assertTrue(any(q.get('observation_valid') is False for q in result['candidates']))

    def test_invalid_profiles_ranges_and_nonfinite_inputs_rejected(self):
        g,m,w,c,v=self.inputs()
        bad=[(g,m,w[:-1],0,239,100,c,v),
             (g,m,w,0,240,100,c,v),(g,m,w,0,239,0,c,v),
             (g,m,w,0,239,float('nan'),c,v),(g,m,w,False,239,100,c,v),
             (g,m.astype(np.uint8),w,0,239,100,c,v),
             (g.astype(np.uint8),m,w,0,239,100,c,v)]
        nan_gray=g.copy();nan_gray[10,10]=np.nan;bad.append((nan_gray,m,w,0,239,100,c,v))
        nan_width=w.copy();nan_width[10]=np.inf;bad.append((g,m,nan_width,0,239,100,c,v))
        bad_coverage=v.copy();bad_coverage[10]=2;bad.append((g,m,w,0,239,100,c,bad_coverage))
        for args in bad:
            with self.assertRaises(ValueError):observe_proximal_boundary(*args)
        with self.assertRaisesRegex(ValueError,'proximal_chroma_contract_mismatch'):
            observe_proximal_boundary(g,m,w,0,239,100,c,v,np.zeros((2,2)))
        for chroma in [np.full(g.shape,1e308),np.full(g.shape,np.finfo(np.float32).max,np.float32)]:
            with self.assertRaisesRegex(ValueError,'proximal_chroma_numeric_overflow'):
                observe_proximal_boundary(g,m,w,0,239,100,c,v,chroma)
