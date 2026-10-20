import copy
import hashlib
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from photo_automatic_v23 import observe, apply_candidates, transport, ENGINE
from photo_visibility_reviewed_apply_v1 import pixels
from photo_experimental_transport_v1 import png
from photo_automatic_v23 import PRECAUTIONARY_REASON


class AutomaticV23Tests(unittest.TestCase):
    def setUp(self):
        y,x=np.indices((160,180))
        self.rgb=np.stack([170+15*np.cos(x*2*np.pi/8)]*3,axis=-1).clip(0,255).astype(np.uint8)
        self.labels=np.zeros((160,180),np.uint16)
        self.labels[10:145,10:80]=1;self.labels[10:145,100:170]=2

    def test_raw_witness_positive_flat_and_outside_support(self):
        mask=self.labels==1
        value=observe(self.rgb,mask)
        self.assertTrue(value['observed'])
        self.assertFalse(value['human_GT'])
        flat=np.full_like(self.rgb,150)
        flat[~mask]=self.rgb[~mask]
        self.assertFalse(observe(flat,mask)['observed'])
        self.assertFalse(observe(flat,mask)['absence_inferred'])
        limited=observe(self.rgb,mask,max_windows=1)
        self.assertFalse(limited['observed'])
        self.assertTrue(limited['budget_exhausted'])

    def test_partial_atomic_application_and_wire_validation(self):
        boundary=self.labels==1
        before=pixels(self.rgb),pixels(self.labels)
        returned,applied,report=apply_candidates(self.rgb,self.labels,boundary,seed=19)
        self.assertTrue(applied.any())
        self.assertFalse(applied[self.labels==2].any())
        np.testing.assert_array_equal(returned[~applied],self.rgb[~applied])
        self.assertEqual(before,(pixels(self.rgb),pixels(self.labels)))
        self.assertFalse(report['human_reviewed'])
        self.assertEqual(report['regions'][1]['reason_code'],'REJECT_BOUNDARY_UNCERTAIN')
        self.assertNotIn('human_decision',report['regions'][0])
        content=png(self.rgb)
        wire=transport(self.rgb,returned,self.labels,applied,report,hashlib.sha256(content).hexdigest(),'test-auto',12)
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
        from experimental_photo_transport_v2 import UploadedPhoto,validate_transport,TransportValidationError
        upload=UploadedPhoto.decode(content)
        validate_transport(wire,upload,request_id='test-auto',engine=ENGINE)
        self.assertEqual(wire['status'],'partial_success')
        tampered=copy.deepcopy(wire);tampered['complete_photo_protection_verified']=True
        with self.assertRaises(TransportValidationError):
            validate_transport(tampered,upload,request_id='test-auto',engine=ENGINE)
        invalid=returned.copy();invalid[0,0]=0
        with self.assertRaisesRegex(ValueError,'preservation'):
            transport(self.rgb,invalid,self.labels,applied,report,upload.source_sha256,'test-auto',1)

    def test_no_candidate_no_witness_and_renderer_failure_are_not_success(self):
        empty=np.zeros_like(self.labels)
        for labels in (empty,self.labels):
            rgb=np.full_like(self.rgb,150)
            returned,applied,report=apply_candidates(rgb,labels,labels>0,seed=19)
            self.assertFalse(applied.any())
            np.testing.assert_array_equal(returned,rgb)
        with patch('photo_automatic_v23.render_selected_regions',side_effect=RuntimeError('render failed')):
            with self.assertRaisesRegex(RuntimeError,'render failed'):
                apply_candidates(self.rgb,self.labels,self.labels>0,seed=19)

    def test_precautionary_surface_renders_without_fabricating_a_raw_witness(self):
        rgb=np.full_like(self.rgb,150)
        surface=self.labels==1
        returned,applied,report=apply_candidates(rgb,self.labels,self.labels>0,seed=19,
                                               surface_permission=surface)
        self.assertTrue(applied[surface].all())
        self.assertFalse(applied[self.labels==2].any())
        self.assertFalse(report['evidence'][0]['observed'])
        self.assertEqual(report['evidence'][0]['visibility'],'uncertain')
        self.assertFalse(report['human_reviewed'])
        self.assertEqual(report['precautionary_applied_region_count'],1)
        self.assertIn('continuous_surface_policy',report['renderer'])
        self.assertFalse(report['renderer']['continuous_surface_policy']['natural_appearance_validated'])
        self.assertEqual(report['regions'][0]['reason_code'],PRECAUTIONARY_REASON)
        np.testing.assert_array_equal(returned[~applied],rgb[~applied])
        content=png(rgb)
        wire=transport(rgb,returned,self.labels,applied,report,hashlib.sha256(content).hexdigest(),'surface',12)
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
        from experimental_photo_transport_v2 import UploadedPhoto,validate_transport,TransportValidationError
        upload=UploadedPhoto.decode(content)
        validate_transport(wire,upload,request_id='surface',engine=ENGINE)
        warning='PRECAUTIONARY_SURFACE_WITHOUT_RIDGE_CONFIRMATION'
        self.assertIn(warning,wire['warnings'])
        hidden=copy.deepcopy(wire);hidden['warnings'].remove(warning)
        with self.assertRaises(TransportValidationError):
            validate_transport(hidden,upload,request_id='surface',engine=ENGINE)
        foreign=copy.deepcopy(wire);foreign.update(photo_engine='native_v12',method='photo_native_v12_experimental')
        with self.assertRaises(TransportValidationError):
            validate_transport(foreign,upload,request_id='surface',engine='native_v12')

    def test_surface_permission_must_cover_whole_component_and_cannot_escape_boundary(self):
        rgb=np.full_like(self.rgb,150)
        surface=self.labels==1;surface[20,20]=False
        returned,applied,report=apply_candidates(rgb,self.labels,self.labels>0,seed=19,
                                               surface_permission=surface)
        self.assertFalse(applied.any())
        np.testing.assert_array_equal(returned,rgb)
        invalid=(self.labels>0).copy();invalid[0,0]=True
        for permission in (invalid,surface.astype(np.uint8),surface[:-1]):
            with self.assertRaisesRegex(ValueError,'surface_permission_contract'):
                apply_candidates(rgb,self.labels,self.labels>0,surface_permission=permission)

    def test_strict_ridge_decision_is_unchanged_when_surface_permission_is_empty(self):
        old,old_mask,old_report=apply_candidates(self.rgb,self.labels,self.labels>0,seed=19)
        new,new_mask,new_report=apply_candidates(self.rgb,self.labels,self.labels>0,seed=19,
                                                surface_permission=np.zeros_like(self.labels,bool))
        np.testing.assert_array_equal(new,old)
        np.testing.assert_array_equal(new_mask,old_mask)
        self.assertEqual(new_report['regions'],old_report['regions'])

    def test_ambiguous_input_returns_original_without_running_detector(self):
        from photo_automatic_v23 import run
        from PIL import Image
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'input.png'
            rgb=np.full((80,96,3),140,np.uint8);Image.fromarray(rgb).save(source)
            registry=root/'registry.json';registry.write_text('{}',encoding='utf-8')
            model=root/'model';model.mkdir()
            (model/'final_config.private.json').write_text('{}',encoding='utf-8')
            (model/'final_context_whole_pad.pt').write_bytes(b'synthetic-unused-weight')
            with patch('pad_refinement_tiles_v3.validate_registry'), patch(
                    'photo_new_input_v23.propose',side_effect=AssertionError('unexpected inference')):
                target=run(source,root/'result',photo_model=model,consumed_registry=registry,request_id='ambiguous')
            wire=json.loads(target.read_text('utf-8'))
            self.assertEqual(wire['status'],'rejected')
            self.assertEqual(wire['candidate_components'],0)
            self.assertEqual(wire['source_RGB_sha256'],wire['returned_RGB_sha256'])
            self.assertFalse((target.parent/'INCOMPLETE.txt').exists())


if __name__=='__main__':
    unittest.main()
