import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from PIL import Image
import photo_crease_pad_v1 as crease
import photo_rgb_body_refinement_v1 as edge
import photo_crease_native_adapter_v1 as adapter
from pad_refinement_data_contract_v2 import source_record,digest,verify_source


def fixture():
    yy,xx=np.mgrid[:300,:240]
    body=((np.abs(xx-120)<=48)&(yy>=80))|(((xx-120)**2+(yy-80)**2<=48**2)&(yy<=80))
    geometry=dict(joint_xy=[120.,210.],tip_xy=[120.,60.],axis_xy=[0.,-1.],reference_width=96.,distal_extent=178.)
    u=xx-120.;t=210.-yy;curve=-12.+.2*u+.6*u**2/96.
    value=155.+4*np.sin(t*2*np.pi/4)-35*np.exp(-.5*((t-curve)/2.4)**2)
    rgb=np.full((300,240,3),[40,80,110],np.uint8);rgb[body]=np.clip(value[body,None]+[30,0,-10],0,255).astype(np.uint8)
    return rgb,body,geometry


class CreaseTests(unittest.TestCase):
    def test_observed_curved_crease_ignores_fine_ridges_and_preserves_inputs(self):
        rgb,body,g=fixture();a=rgb.copy();b=body.copy();obs=crease.observe_crease(rgb,body,g)
        self.assertEqual(obs['status'],'observed');self.assertLess(abs(obs['offset_native_pixels']+12),4)
        self.assertLess(abs(obs['slope']-.2),.11);self.assertLess(abs(obs['curvature']-.6),.31)
        mask,_=crease.silhouette(body,g,obs)
        self.assertTrue(mask[32,120]);self.assertFalse(mask[260,120]);self.assertFalse(np.any(mask&~body))
        np.testing.assert_array_equal(rgb,a);np.testing.assert_array_equal(body,b)

    def test_blank_and_bad_geometry_cannot_invent_observed_joint(self):
        rgb,body,g=fixture();rgb[:]=150
        self.assertEqual(crease.observe_crease(rgb,body,g)['status'],'unobserved')
        for change in [dict(axis_xy=[0,0]),dict(axis_xy=[np.nan,1]),dict(reference_width=0),dict(distal_extent=np.inf),dict(distal_extent=1e9)]:
            with self.assertRaises(ValueError):crease.observe_crease(rgb,body,g|change)
        with self.assertRaises(ValueError):crease.observe_crease(rgb[:-1],body,g)
        with self.assertRaises(ValueError):crease.silhouette(body,g,dict(status='unobserved'))

    def test_90_degree_rotation_has_same_observation_and_permission(self):
        rgb,body,g=fixture();obs=crease.observe_crease(rgb,body,g);mask,_=crease.silhouette(body,g,obs)
        def rotate(p):return [p[1],239-p[0]]
        rotated=g|dict(joint_xy=rotate(g['joint_xy']),tip_xy=rotate(g['tip_xy']),axis_xy=[-1.,0.])
        b=np.rot90(body).copy();o=crease.observe_crease(np.rot90(rgb).copy(),b,rotated)
        self.assertAlmostEqual(o['offset_native_pixels'],obs['offset_native_pixels'])
        actual,_=crease.silhouette(b,rotated,o);np.testing.assert_array_equal(actual,np.rot90(mask))

    def test_detached_fragments_removed_by_tip_association_not_component_area(self):
        rgb,body,g=fixture();body[15:20,20:25]=True
        obs=crease.observe_crease(rgb,body,g);mask,details=crease.silhouette(body,g,obs)
        self.assertFalse(mask[15:20,20:25].any());self.assertGreaterEqual(details['detached_components_removed'],1)


class EdgeTests(unittest.TestCase):
    def test_owner_gaps_restored_only_with_unique_local_assignment(self):
        from photo_native_partition_edges_v1 import restore_edges
        body=np.ones((60,80),bool);a=np.zeros_like(body);b=a.copy();a[10:40,10:25]=True;b[10:40,28:45]=True
        contexts=[dict(body=m,reason=None,reject_reason=None,parent=dict(working_scale=.5)) for m in [a,b]]
        rows=restore_edges(contexts,body)
        self.assertTrue(rows[0]['body'][20,8]);self.assertTrue(rows[1]['body'][20,46])
        self.assertFalse(rows[0]['body'][20,26]);self.assertFalse(rows[1]['body'][20,26])
        self.assertFalse(rows[0]['body'][59,79]);self.assertFalse(np.any(rows[0]['body']&rows[1]['body']))
        np.testing.assert_array_equal(contexts[0]['body'],a)

    def test_real_grabcut_repairs_bounded_silhouette_deterministically(self):
        rgb,truth,g=fixture();body=cv2.erode(truth.astype(np.uint8),np.ones((7,7),np.uint8))>0
        rows=dict(candidates=[dict(candidate_id='synthetic',status='rounded_cap_applied',geometry=g)])
        source=rgb.copy();original=body.copy();a,metadata=edge.refine_body(rgb,body,rows);b,other=edge.refine_body(rgb,body,rows)
        np.testing.assert_array_equal(a,b);self.assertEqual(metadata,other)
        np.testing.assert_array_equal(rgb,source);np.testing.assert_array_equal(body,original)
        self.assertGreater((a&truth).sum(),(body&truth).sum());self.assertFalse(np.any(a&~truth))
        np.testing.assert_array_equal(a[290:],body[290:])

    def test_empty_seed_and_large_window_are_explicit_unchanged(self):
        rgb,body,g=fixture();empty=np.zeros_like(body)
        rows=dict(candidates=[dict(candidate_id='synthetic',status='rounded_cap_applied',geometry=g)])
        actual,report=edge.refine_body(rgb,empty,rows)
        self.assertFalse(actual.any());self.assertEqual(report['candidates'][0]['status'],'unchanged_seed_unavailable')
        with patch.dict(edge.CONFIG,max_window_pixels=1):
            actual,report=edge.refine_body(rgb,body,rows)
        np.testing.assert_array_equal(actual,body);self.assertIn('resource_limit',report['candidates'][0]['status'])


class DerivedContractTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.rgb,self.body,self.geometry=fixture();source=self.root/'source.png';Image.fromarray(self.rgb).save(source)
        sem=self.root/'original';sem.mkdir();Image.fromarray(self.body.astype(np.uint8)*255).save(sem/'body.png')
        Image.fromarray(np.zeros(self.body.shape,np.uint8)).save(sem/'tip.png')
        payload=dict(source_sha256=digest(source),coordinate_system='encoded_original_pixels',body_sha256=digest(sem/'body.png'),
            tip_sha256=digest(sem/'tip.png'),body_classes=[1,2],tip_class=2,minimum_votes=2)
        (sem/'semantics.json').write_text(json.dumps(payload));self.original=source_record(source,'SYNTH',sem,self.rgb)

    def derived(self):
        # Real edge refinement and lineage writer; stub only detector discovery
        # to isolate the data contract from a learned model or human labels.
        rounding=dict(candidates=[dict(candidate_id='synthetic',status='rounded_cap_applied',geometry=self.geometry)])
        with patch.object(adapter,'estimate',return_value=dict(mask=np.zeros_like(self.body))),patch.object(adapter,'crease_pads',return_value=(self.body.copy(),{})):
            record,mask,meta,pose=adapter.prepare(self.original,self.rgb,self.body,rounding,None,self.root/'derived')
        return record

    def test_derived_masks_have_explicit_provenance_and_training_is_forbidden(self):
        record=self.derived();verify_source(record,'inference');verify_source(self.original,'inference')
        semantic=json.loads(Path(record['semantics_path']).read_text())
        self.assertFalse(semantic['raw_COLFISPOOF_output']);self.assertNotIn('body_classes',semantic)
        self.assertEqual(semantic['original_source_record'],self.original)
        with self.assertRaisesRegex(ValueError,'inference_only'):verify_source(record,'training')

    def test_source_and_derived_pixel_tampering_rejected(self):
        record=self.derived();bad=record|dict(source_id='DIFFERENT')
        with self.assertRaisesRegex(ValueError,'lineage_mismatch'):verify_source(bad,'inference')
        path=Path(record['body_path']);Image.fromarray(np.zeros_like(self.body,np.uint8)).save(path)
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):verify_source(record,'inference')

    def test_parent_provenance_change_and_nested_derivation_rejected(self):
        record=self.derived();path=Path(record['semantics_path']);semantic=json.loads(path.read_text())
        semantic['edge_refinement']['input_RGB_sha256']='0'*64
        path.write_text(json.dumps(semantic));record['semantics_sha256']=digest(path)
        with self.assertRaisesRegex(ValueError,'provenance_mismatch'):verify_source(record,'inference')
        parent=Path(self.original['semantics_path']);raw=json.loads(parent.read_text());raw['kind']=adapter.KIND;parent.write_text(json.dumps(raw))
        semantic['original_source_record']['semantics_sha256']=digest(parent)
        path.write_text(json.dumps(semantic));record['semantics_sha256']=digest(path)
        with self.assertRaisesRegex(ValueError,'nested'):verify_source(record,'inference')


if __name__=='__main__':unittest.main()
