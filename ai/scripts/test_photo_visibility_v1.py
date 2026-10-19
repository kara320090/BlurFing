import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image, ImageOps

from photo_pad_annotation_v1 import digest, write_json, make_server
from photo_visibility_annotation_v1 import Project, ASSETS
from photo_visibility_diagnostic_v1 import pitch_consensus, preprocess, MCLFIQ, bind_upright_coordinates


def fixture(root, orientation=1, role='synthetic_fixture'):
    root.mkdir(exist_ok=True)
    rgb=np.zeros((80,120,3),np.uint8);rgb[:]=[182,130,99];rgb[10:50,10:40]=[210,150,110]
    im=Image.fromarray(rgb);exif=Image.Exif();exif[274]=orientation
    source=root/'source.png';im.save(source,exif=exif)
    mask=np.zeros((80,120),np.uint8);mask[10:50,10:40]=255;mask[20:60,65:100]=255
    mp=root/'mask.png';Image.fromarray(mask).save(mp)
    with Image.open(source) as loaded:upright=np.asarray(ImageOps.exif_transpose(loaded).convert('RGB'))
    roster=root/'roster.json'
    write_json(roster,dict(version='visibility_roster_v1',data_role=role,sources=[dict(source_id='SYNTH-001',
        source_path=str(source),source_sha256=digest(source.read_bytes()),mask_path=str(mp),mask_sha256=digest(mp.read_bytes()),
        width=120,height=80,exif_orientation=orientation,encoded_RGB_sha256=digest(rgb.tobytes()),
        upright_RGB_sha256=digest(upright.tobytes()),split_role='synthetic_fixture')]))
    return Project(roster,root/'state')


class VisibilityAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.p=fixture(self.root);self.sid='SYNTH-001'

    def payload(self, reviewed=False):
        return dict(base_revision=0,status='reviewed' if reviewed else 'draft',attest_original_reviewed=reviewed,
            attest_grouping_reviewed=reviewed,groups=[dict(component_ids=[1],label='visible',reasons=[],evidence_box=[15,15,30,35]),
            dict(component_ids=[2],label='uncertain',reasons=['blur'],evidence_box=None)])

    def test_all_exif_orientations_keep_mask_registered(self):
        for orientation in range(1,9):
            p=fixture(self.root/str(orientation),orientation);rgb,mask=p.arrays(self.sid)
            marked=(rgb==[210,150,110]).all(axis=2)
            self.assertEqual(int(marked.sum()),1200);self.assertTrue(mask[marked].all())
            self.assertEqual(mask.shape,rgb.shape[:2])
            with Image.open(io.BytesIO(p.image(self.sid+'-overlay'))) as overlay:
                np.testing.assert_array_equal(np.asarray(overlay)[:,:,3]>0,mask)

    def test_draft_is_not_human_GT_and_not_exported(self):
        r=self.p.save(self.sid,self.payload());self.assertFalse(r['human_GT'])
        with self.assertRaisesRegex(ValueError,'no_reviewed'):self.p.export()

    def test_missing_attestation_rejected_and_synthetic_never_human(self):
        p=self.payload(True);p['attest_original_reviewed']=False
        with self.assertRaisesRegex(ValueError,'attestation'):self.p.save(self.sid,p)
        p['attest_original_reviewed']=True;r=self.p.save(self.sid,p);self.assertFalse(r['human_GT'])

    def test_real_role_explicit_review_is_human(self):
        p=fixture(self.root/'human-contract',role='diagnostic_development')
        self.assertTrue(p.save(self.sid,self.payload(True))['human_GT'])

    def test_visible_requires_native_in_mask_evidence(self):
        for box in [None,[0,0,20,20],[15,15,16,16],[15.,15,30,35],[15,15,130,35]]:
            p=self.payload(True);p['groups'][0]['evidence_box']=box
            with self.assertRaises(ValueError):self.p.save(self.sid,p)

    def test_unknown_or_unlabeled_is_not_a_negative(self):
        p=self.payload();p['groups'][0].update(label=None,evidence_box=None)
        self.assertIsNone(self.p.save(self.sid,p)['groups'][0]['label'])
        p.update(base_revision=1,status='reviewed',attest_original_reviewed=True,attest_grouping_reviewed=True)
        with self.assertRaisesRegex(ValueError,'label'):self.p.save(self.sid,p)

    def test_uncertain_requires_reason(self):
        p=self.payload(True);p['groups'][1]['reasons']=[]
        with self.assertRaisesRegex(ValueError,'reason'):self.p.save(self.sid,p)

    def test_group_partition_cannot_drop_or_double_count_fragments(self):
        for members in [[1],[1,1],[1,3]]:
            p=self.payload();p['groups']=[dict(component_ids=members,label=None,evidence_box=None)]
            with self.assertRaises(ValueError):self.p.save(self.sid,p)
        p=self.payload();p['groups']=[dict(component_ids=[1,2],label=None,evidence_box=None)]
        self.assertEqual(len(self.p.save(self.sid,p)['groups']),1)

    def test_conflict_and_orphan_revision_preserved(self):
        r=self.p.save(self.sid,self.payload())
        with self.assertRaisesRegex(ValueError,'revision_conflict'):self.p.save(self.sid,self.payload())
        folder=self.p.state/'annotations'/self.sid;(folder/'rev-000002.json').write_text('orphan')
        p=self.payload();p['base_revision']=r['revision'];r=self.p.save(self.sid,p)
        self.assertEqual(r['revision'],3);self.assertEqual((folder/'rev-000002.json').read_text(),'orphan')

    def test_source_and_mask_mutation_cannot_hide_in_cache(self):
        for key in ['source_path','mask_path']:
            p=fixture(self.root/key);p.arrays(self.sid);path=Path(p.sources[self.sid][key]);path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaises(ValueError):p.save(self.sid,self.payload())

    def test_export_labels_only_with_hash_binding(self):
        self.p.save(self.sid,self.payload(True));r=self.p.export();path=self.p.state/'exports'/r['filename']
        self.assertEqual(digest(path.read_bytes()),r['sha256'])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.namelist(),['visibility_labels.json'])
            record=json.loads(z.read(z.namelist()[0]))['records'][0]
            self.assertFalse(record['human_GT']);self.assertEqual(record['mask_sha256'],self.p.sources[self.sid]['mask_sha256'])

    def test_second_project_cannot_write_while_first_holds_lock(self):
        other=Project(self.p.roster_path,self.p.state)
        with self.p.writing():
            with self.assertRaisesRegex(ValueError,'another_review_write'):other.save(self.sid,self.payload())
        self.assertEqual(other.save(self.sid,self.payload())['revision'],1)

    def test_loopback_assets_session_and_POST_origin(self):
        server,url=make_server(self.p,assets=ASSETS,export_prefix='BlurFing_visibility_GT_')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            page=urllib.request.urlopen(url).read();self.assertIn('지문 가시성'.encode(),page)
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url.split('/s/')[0]+'/api/project')
            request=urllib.request.Request(url+'api/save/'+self.sid,data=json.dumps(self.payload()).encode(),headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request)
        finally:server.shutdown();server.server_close();thread.join()


class VisibilityDiagnosticTests(unittest.TestCase):
    def test_upright_crop_coordinates_not_mislabeled_as_encoded(self):
        observation=dict(bbox_encoded_source_xyxy=[0,0,80,100],levels=[dict(pitch=dict(
            coordinate_origin_encoded_source_xy=[0,0],patch_native_coordinates=[dict(center_encoded_source_xy=[10,20])]))])
        result=bind_upright_coordinates(observation,[300,400])
        self.assertEqual(result['bbox_upright_native_xyxy'],[300,400,380,500])
        self.assertEqual(result['levels'][0]['pitch']['patch_native_coordinates'][0]['center_upright_native_xy'],[310,420])
        self.assertNotIn('encoded_source',json.dumps(result))

    def test_no_pitch_or_failure_stays_unknown(self):
        self.assertIsNone(pitch_consensus(dict(levels=[]))['native_pitch'])
        self.assertEqual(pitch_consensus(dict(levels=[dict(pitch=dict(status='unobserved'))]))['status'],'unavailable')

    def test_resolution_disagreement_cannot_pick_best_scale(self):
        def level(p):return dict(pitch=dict(status='observed',patch_native_coordinates=[dict(autocorrelation_perpendicular_native_pixels=p,fft_perpendicular_native_pixels=p)]))
        self.assertEqual(pitch_consensus(dict(levels=[level(8),level(16)]))['reason'],'cross_resolution_pitch_disagreement')
        self.assertEqual(pitch_consensus(dict(levels=[level(9),level(9)]))['native_pitch'],9)

    def test_preprocess_finite_memory_and_input_preservation(self):
        rgb=np.full((100,80,3),128,np.uint8);mask=np.zeros((100,80),bool);mask[5:95,10:70]=True
        before=rgb.copy();out,meta=preprocess(rgb,mask,9)
        np.testing.assert_array_equal(before,rgb);self.assertEqual(out.dtype,np.uint8)
        self.assertFalse(meta['physical_DPI_known']);self.assertFalse(meta['distal_direction_verified'])
        for pitch in [float('nan'),float('inf'),0,-1,1e-10]:
            with self.assertRaises(ValueError):preprocess(rgb,mask,pitch)

    def runtime(self,root):
        model=root/'model.yaml';model.write_bytes(b'synthetic-test-model')
        exe=root/'nfiq2.exe';exe.write_bytes(b'test-double-not-an-executable')
        info=root/'model.txt';info.write_text('Path = '+str(model)+'\nHash = '+hashlib.md5(model.read_bytes()).hexdigest()+'\n')
        config=dict(executable=str(exe),model=str(model),model_info=str(info))
        for k in list(config):config[k+'_sha256']=digest(Path(config[k]).read_bytes())
        path=root/'runtime.json';write_json(path,config);return MCLFIQ(path)

    def test_runtime_zero_exit_with_error_is_never_score_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.runtime(Path(tmp));header='DEBUG | Model Hash: '+runtime.md5+'\n'
            for output,expected in [(header+'Error: extraction failed\n','unavailable'),(header+'57\n','scored'),('57\n','unavailable'),(header+'101\n','unavailable')]:
                with patch('photo_visibility_diagnostic_v1.subprocess.run',return_value=subprocess.CompletedProcess([],0,output,'')):
                    result=runtime.score(np.zeros((32,32),np.uint8));self.assertEqual(result['status'],expected)
                    if expected=='unavailable':self.assertIsNone(result['score'])

    def test_wrong_model_binding_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.runtime(Path(tmp));config=runtime.config;info=Path(config['model_info']);info.write_text('Path = default.yaml\nHash = invalid\n')
            config['model_info_sha256']=digest(info.read_bytes());write_json(Path(tmp)/'runtime.json',config)
            with self.assertRaisesRegex(ValueError,'binding'):MCLFIQ(Path(tmp)/'runtime.json')


if __name__=='__main__': unittest.main()
