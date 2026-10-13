"""Public-source smoke tests use synthetic arrays only, no images in Git."""
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
from canonical_fingerprint_roi import canonical_roi
from fingerprint_input_router import route_input
from scanner_fingerprint_detector import detect_scanner
from external_fingerphoto_detector import hand_prompts,detect_photo
from scanner_renderer_experimental import render_scanner
from protect_fingerprint import protect_fingerprint


def synthetic_ridges():
    yy,xx=np.indices((192,128));mask=((xx-64)/52)**2+((yy-96)/83)**2<1;gray=np.full((192,128),255,np.uint8);gray[mask]=np.clip(128+70*np.sin(xx[mask]*2*np.pi/8),0,255);return np.repeat(gray[:,:,None],3,axis=2)

class FrontendTests(unittest.TestCase):
    def test_uniform_unknown(self):self.assertEqual(route_input(np.full((80,100,3),128,np.uint8))['input_type'],'UNKNOWN')
    def test_rgb_photo(self):self.assertEqual(route_input(np.full((80,100,3),[180,100,80],np.uint8))['input_type'],'PHOTO')
    def test_grayscale_scanner(self):self.assertEqual(route_input(synthetic_ridges())['input_type'],'FINGERPRINT_IMAGE')
    def test_photo_dependency_fail_closed(self):
        regions,d=detect_photo(synthetic_ridges(),'0'*64);self.assertEqual(regions,[]);self.assertEqual(d['status'],'blocked')
    def test_native_canonical_contract_and_hash_mismatch(self):
        rgb=synthetic_ridges();r,_=detect_scanner(rgb,'0'*64);r[0].validate(rgb,'0'*64)
        with self.assertRaises(ValueError):r[0].validate(rgb,'1'*64)
    def test_mask_nonbinary_reject(self):
        rgb=synthetic_ridges();r,_=detect_scanner(rgb,'0'*64);r[0].binary_mask[0,0]=42
        with self.assertRaises(ValueError):r[0].validate(rgb,'0'*64)
    def test_empty_mask_reject(self):
        rgb=synthetic_ridges();r,_=detect_scanner(rgb,'0'*64);r[0].binary_mask[:]=0
        with self.assertRaises(ValueError):r[0].validate(rgb,'0'*64)
    def test_landmark_prompt_geometry(self):
        points=np.full((21,2),.5)
        for t,d,p in [(4,3,2),(8,7,6),(12,11,10),(16,15,14),(20,19,18)]:points[t]=[.5,.2];points[d]=[.5,.35];points[p]=[.5,.5]
        prompts=hand_prompts(points,(300,200));self.assertEqual(len(prompts),5)
        for p in prompts:self.assertEqual(p['labels'][0],1);self.assertTrue(np.all(p['labels'][1:]==0));self.assertEqual(p['axis'],[0.,-1.])
    def test_invalid_landmarks(self):
        with self.assertRaises(ValueError):hand_prompts(np.zeros((20,2)),(100,100))
    def test_strength_zero(self):
        rgb=synthetic_ridges();r,_=detect_scanner(rgb,'0'*64);out,d=render_scanner(rgb,r[0],0);np.testing.assert_array_equal(out,rgb);self.assertFalse(d['applied'])
    def test_API_requires_structure_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.png';Image.fromarray(synthetic_ridges()).save(p);out,d=protect_fingerprint(p,Path(td)/'out',experimental_scanner=True);self.assertEqual(d['fingerprints_transformed'],0);self.assertEqual(d['transform']['reason'],'scanner_structure_guard_required')
    def test_API_source_and_EXIF_preserved_on_photo(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.jpg';exif=Image.Exif();exif[274]=6;Image.new('RGB',(80,60),(180,100,80)).save(p,exif=exif);before=p.read_bytes();out,d=protect_fingerprint(p,Path(td)/'out');self.assertEqual(d['status'],'blocked');self.assertEqual(p.read_bytes(),before)
            with Image.open(d['output_path']) as im:self.assertEqual(im.getexif()[274],6);self.assertEqual(im.size,(80,60))
    def test_API_unknown_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.png';Image.new('L',(40,40),128).save(p);out,d=protect_fingerprint(p,Path(td)/'out');self.assertEqual(d['input_type'],'unknown');self.assertTrue((out==128).all())
    def test_API_cannot_overwrite_output(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.png';Image.new('L',(40,40),128).save(p);protect_fingerprint(p,Path(td)/'out')
            with self.assertRaises(FileExistsError):protect_fingerprint(p,Path(td)/'out')
    def test_scanner_repeat_mask(self):
        rgb=synthetic_ridges();a,_=detect_scanner(rgb,'0'*64);b,_=detect_scanner(rgb,'0'*64);np.testing.assert_array_equal(a[0].binary_mask,b[0].binary_mask)

    def test_photo_EXIF_mask_mapping_with_injected_runtime(self):
        class Runtime:
            def landmarks(self,rgb):
                points=np.full((21,2),.5)
                for t,d,p in [(4,3,2),(8,7,6),(12,11,10),(16,15,14),(20,19,18)]:points[t]=[.5,.2];points[d]=[.5,.35];points[p]=[.5,.5]
                return [points]
            def set_image(self,rgb):self.shape=rgb.shape[:2]
            def predict(self,prompt):return np.ones(self.shape,bool)
        rgb=synthetic_ridges()
        def quality(gray,mask):return mask,dict(status='ridge_observed',credible_fraction=1.,pitch_native=8.,orientation=0.)
        with patch('external_fingerphoto_detector.ridge_evidence',side_effect=quality):regions,d=detect_photo(rgb,'0'*64,6,Runtime())
        self.assertTrue(regions)
        for r in regions:self.assertEqual(r.binary_mask.shape,rgb.shape[:2]);r.validate(rgb,'0'*64)
    def test_structure_exception_returns_original(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.png';Image.fromarray(synthetic_ridges()).save(p)
            def fail(a,b):raise RuntimeError('synthetic failure')
            out,d=protect_fingerprint(p,Path(td)/'out',experimental_scanner=True,structure_guard=fail)
            np.testing.assert_array_equal(out,synthetic_ridges());self.assertEqual(d['fingerprints_transformed'],0);self.assertFalse(d['transform']['structure_check']['structure_change_passed'])

    def test_CLI_child_progress_cannot_corrupt_JSON_stdout(self):
        import subprocess,sys
        import protect_fingerprint
        module_dir=str(Path(protect_fingerprint.__file__).parent)
        code="import sys,subprocess;sys.path.insert(0,"+repr(module_dir)+");from protect_fingerprint import cli_progress_to_stderr\nwith cli_progress_to_stderr(): subprocess.run([sys.executable,'-c',\"print('child-progress')\"],check=True)\nprint('{}')"
        r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
        self.assertEqual(r.stdout.strip(),'{}');self.assertIn('child-progress',r.stderr)

    def test_photo_runtime_failure_returns_original(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.png';Image.new('RGB',(80,60),(180,100,80)).save(p)
            with patch('protect_fingerprint.detect_photo',side_effect=RuntimeError('synthetic failure')):out,d=protect_fingerprint(p,Path(td)/'out')
            self.assertEqual(d['status'],'blocked');self.assertEqual(d['fingerprints_transformed'],0);self.assertTrue((out==np.array([180,100,80])).all())

    def test_full_frame_ridges_can_form_full_scanner_ROI(self):
        yy,xx=np.indices((192,192));gray=np.rint(128+70*np.sin(xx*2*np.pi/8)).astype(np.uint8);rgb=np.repeat(gray[:,:,None],3,axis=2)
        regions,d=detect_scanner(rgb,'0'*64);self.assertTrue(regions);self.assertGreater((regions[0].binary_mask>0).mean(),.98)
