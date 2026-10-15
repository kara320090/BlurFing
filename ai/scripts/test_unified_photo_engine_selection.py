"""Synthetic transport/selection tests; no models, biometrics or scores."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import numpy as np
from PIL import Image
import protect_fingerprint as api


class PhotoEngineTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.source=self.root/'source.png'
        Image.new('RGB',(80,60),(180,100,80)).save(self.source)
        self.before=self.source.read_bytes();self.models=self.root/'private model'
        self.registry=self.root/'registry.json'

    def fake_entry(self):
        entry=types.ModuleType('synthetic_photo_entry')
        def canonical(source):
            with Image.open(source) as im:
                rgb=np.asarray(im.convert('RGB')).copy();orientation=im.getexif().get(274,1)
            return rgb,dict(original_source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),source_exif_orientation=orientation)
        def run(source,*args,**kwargs):
            rgb,identity=canonical(source);output=Path(args[-1]);output.mkdir(parents=True,exist_ok=False)
            exif=Image.Exif();exif[274]=identity['source_exif_orientation'];Image.fromarray(rgb).save(output/'returned.png',exif=exif)
            report=dict(status='partial_success',fingerprints_detected=2,fingerprints_transformed=1,fingerprints_rejected=1,
                input_identity=identity,
                regions=[dict(status='transformed'),dict(status='rejected',reason='synthetic_rejection')],
                output_path=str((output/'returned.png').resolve()),RGB_outside_accepted_permission_preserved=True,
                development_replay=kwargs['development_replay'],independent_final_test=False,approved_for_protection=False,
                permission_source='synthetic_only',V6_learned_pad_model_used=len(args)==3,semantic_segmentation_required=True)
            (output/'result.private.json').write_text(json.dumps(report),encoding='utf-8')
            return rgb,report
        entry.canonical_rgb=Mock(side_effect=canonical);entry.run=Mock(side_effect=run)
        return entry

    def invoke(self,engine,entry,**options):
        module=('protect_photo_whole_pad_context_native_v1' if engine=='native_v12' else 'protect_photo_distal_native_v1')
        config=dict(photo_engine=engine,consumed_registry=self.registry)
        if engine=='native_v12':config['photo_model']=self.models
        config.update(options)
        with patch.dict(sys.modules,{module:entry}):return api.protect_image(self.source,self.root/'output',**config)

    def test_native_explicit_and_common_result_partial_state(self):
        entry=self.fake_entry();rgb,result=self.invoke('native_v12',entry)
        self.assertEqual(entry.run.call_args.args,(self.source,self.models,self.registry,self.root/'output'))
        self.assertFalse(entry.run.call_args.kwargs['development_replay']);self.assertFalse(entry.run.call_args.kwargs['detect_only'])
        self.assertEqual(result['status'],'partial_success');self.assertEqual(result['fingerprints_rejected'],1)
        self.assertEqual(result['schema_version'],'unified-fingerprint-v2');self.assertEqual(result['image_width'],80)
        self.assertEqual(result['image_height'],60);self.assertEqual(result['photo_engine'],'native_v12')
        self.assertFalse(result['privacy_validated']);self.assertFalse(result['PHOTO_PROTECTION_PRODUCTION_READY'])
        self.assertFalse(result['independent_validation_complete']);self.assertTrue(result['exterior_preserved'])
        self.assertEqual(json.loads((self.root/'output/result.json').read_text(encoding='utf-8')),result)
        self.assertEqual(self.source.read_bytes(),self.before)

    def test_distal_uses_registry_without_model_and_no_native_entry(self):
        entry=self.fake_entry()
        with patch.dict(sys.modules,{'protect_photo_whole_pad_context_native_v1':None}):
            _,result=self.invoke('distal_v13',entry)
        self.assertEqual(entry.run.call_args.args,(self.source,self.registry,self.root/'output'))
        self.assertFalse(result['V6_learned_pad_model_used']);self.assertTrue(result['semantic_segmentation_required'])
        self.assertEqual(result['photo_engine'],'distal_v13')

    def test_explicit_development_replay_is_not_independent(self):
        entry=self.fake_entry();_,result=self.invoke('native_v12',entry,development_replay=True)
        self.assertTrue(entry.run.call_args.kwargs['development_replay']);self.assertFalse(result['independent_final_test'])

    def test_detect_only_and_zero_strength_are_forwarded(self):
        for options in (dict(detect_only=True),dict(strength=0.)):
            with self.subTest(options=options):
                entry=self.fake_entry();output=self.root/'output'
                if output.exists():output.rename(self.root/('old_'+str(len(list(self.root.iterdir())))))
                self.invoke('native_v12',entry,**options)
                self.assertTrue(entry.run.call_args.kwargs['detect_only'])

    def test_RGBA_delegates_before_legacy_RGB_L_restriction(self):
        Image.new('RGBA',(80,60),(180,100,80,200)).save(self.source)
        entry=self.fake_entry();_,result=self.invoke('native_v12',entry)
        self.assertEqual(entry.canonical_rgb.call_count,1);self.assertEqual(result['input_type'],'photo')

    def test_encoded_EXIF_dimensions_are_not_transposed_by_adapter(self):
        exif=Image.Exif();exif[274]=6;Image.new('RGB',(80,60),(180,100,80)).save(self.source,exif=exif)
        entry=self.fake_entry();_,result=self.invoke('native_v12',entry)
        self.assertEqual((result['image_width'],result['image_height']),(80,60))
        self.assertEqual(result['source_exif_orientation'],6)

    def test_missing_config_wrong_types_and_implicit_options_rejected_before_decode(self):
        cases=[dict(photo_engine='bad'),dict(photo_engine=True),dict(development_replay=1),
            dict(photo_engine='native_v12'),dict(photo_engine='distal_v13'),
            dict(photo_engine='distal_v13',photo_model='model',consumed_registry='registry'),
            dict(photo_engine='native_v12',photo_model=True,consumed_registry='registry'),
            dict(photo_engine='native_v12',photo_model='model',consumed_registry=''),
            dict(photo_model='model'),dict(development_replay=True),dict(detect_only=1)]
        for options in cases:
            with self.subTest(options=options),self.assertRaises(ValueError):api.protect_image(self.root/'missing.png',**options)

    def test_hand_runtime_is_not_silently_combined(self):
        with self.assertRaisesRegex(ValueError,'hand_SAM'):
            api.protect_fingerprint(self.source,photo_runtime=object(),photo_engine='native_v12',photo_model='model',consumed_registry='registry')

    def test_fresh_output_failure_is_not_reused(self):
        (self.root/'output').mkdir();(self.root/'output/sentinel').write_text('keep')
        with self.assertRaises(FileExistsError):self.invoke('native_v12',self.fake_entry())
        self.assertEqual((self.root/'output/sentinel').read_text(),'keep')

    def test_actual_native_failure_propagates_without_alternate_engine(self):
        entry=self.fake_entry();entry.run.side_effect=RuntimeError('synthetic_native_failure')
        with patch.dict(sys.modules,{'protect_photo_distal_native_v1':None}),self.assertRaisesRegex(RuntimeError,'synthetic_native_failure'):
            self.invoke('native_v12',entry)
        self.assertEqual(entry.run.call_count,1);self.assertEqual(self.source.read_bytes(),self.before)

    def test_changed_source_between_route_and_engine_does_not_publish_unified_success(self):
        entry=self.fake_entry();run=entry.run.side_effect
        def changed(*args,**kwargs):
            result=run(*args,**kwargs)
            Image.new('RGB',(80,60),(30,40,50)).save(self.source)
            return result
        entry.run.side_effect=changed
        with self.assertRaisesRegex(RuntimeError,'source_changed_between'):self.invoke('native_v12',entry)
        self.assertFalse((self.root/'output/result.json').exists())

    def test_engine_identity_mismatch_cannot_be_relabelled_as_routed_source(self):
        entry=self.fake_entry();run=entry.run.side_effect
        def mismatch(*args,**kwargs):
            rgb,report=run(*args,**kwargs);report['input_identity']['original_source_sha256']='0'*64
            return rgb,report
        entry.run.side_effect=mismatch
        with self.assertRaisesRegex(RuntimeError,'source_changed_between'):self.invoke('native_v12',entry)
        self.assertFalse((self.root/'output/result.json').exists())

    def test_unknown_and_scanner_do_not_call_photo_transform(self):
        yy,xx=np.indices((192,128));mask=((xx-64)/52)**2+((yy-96)/83)**2<1
        gray=np.full((192,128),255,np.uint8);gray[mask]=np.clip(128+70*np.sin(xx[mask]*2*np.pi/8),0,255)
        for image,expected in [(Image.new('L',(40,40),128),'unknown'),(Image.fromarray(gray),'fingerprint_image')]:
            with self.subTest(expected=expected):
                image.save(self.source);entry=self.fake_entry();output=self.root/'output'
                if output.exists():output.rename(self.root/('old_'+expected))
                _,result=self.invoke('native_v12',entry,detect_only=True)
                entry.run.assert_not_called();self.assertEqual(result['input_type'],expected)
                self.assertNotIn('photo_engine',result);self.assertEqual(result['fingerprints_transformed'],0)

    def test_legacy_default_never_imports_new_optional_runtimes(self):
        empty=dict(status='rejected',fingerprints_detected=0,fingerprints_transformed=0,fingerprints_rejected=0,regions=[])
        with patch.dict(sys.modules,{'protect_photo_whole_pad_context_native_v1':None,'protect_photo_distal_native_v1':None}),patch('photo_quality_gate.evaluate',return_value=(np.asarray(Image.open(self.source)).copy(),empty)):
            _,result=api.protect_image(self.source,self.root/'legacy')
        self.assertNotIn('photo_engine',result);self.assertEqual(result['status'],'rejected')

    def test_default_and_explicit_legacy_transport_are_identical(self):
        def evaluate(*args,**kwargs):
            return np.asarray(Image.open(self.source)).copy(),dict(status='rejected',fingerprints_detected=0,
                fingerprints_transformed=0,fingerprints_rejected=0,regions=[])
        with patch('photo_quality_gate.evaluate',side_effect=evaluate):
            first,one=api.protect_image(self.source,self.root/'legacy1')
            second,two=api.protect_image(self.source,self.root/'legacy2',photo_engine='legacy')
        self.assertEqual((self.root/'legacy1/returned.png').read_bytes(),(self.root/'legacy2/returned.png').read_bytes())
        np.testing.assert_array_equal(first,second)
        one.pop('output_path');two.pop('output_path');self.assertEqual(one,two)

    def test_cli_invalid_explicit_configuration_emits_JSON_error(self):
        script=Path(api.__file__)
        result=subprocess.run([sys.executable,str(script),'--input',str(self.source),'--photo-engine','distal_v13'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);payload=json.loads(result.stdout)
        self.assertEqual(payload['status'],'error');self.assertIn('registry',payload['reason'])


if __name__=='__main__':unittest.main()
