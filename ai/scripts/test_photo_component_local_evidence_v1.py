import concurrent.futures
import unittest
from unittest.mock import patch
import cv2,numpy as np
import photo_component_local_evidence_v1 as local
import photo_learned_pad_pipeline_v8 as pipeline
import photo_body_observation_seed_v1 as seeds
import photo_region_pipeline_v1 as shared
from contactless_ridge_pitch import estimate_ridge_pitch
from diagnose_ridge_measurement_noise import two_scale_measurement


class LocalEvidenceTests(unittest.TestCase):
    def test_component_observation_rejections_have_pitch_quality_category(self):
        from photo_quality_gate import state
        for reason in ['component_local_pitch_unobserved','component_local_seed_unavailable']:
            self.assertEqual(state(reason),'REJECT_PITCH_UNOBSERVED')

    def grouped(self,mask,reason=None):
        return dict(labels=mask.astype(np.uint16),records=[dict(plan=dict(component=1,status='planned',reject_reason=reason,
            working_scale=1.,mask_pixels=int(mask.sum())),reason=reason,owner=np.ones_like(mask),
            association=dict(candidate_id='same-owner'),candidate_id='same-owner')])

    def test_disconnected_permissions_cannot_share_one_authorization_and_tiny_pixels_remain(self):
        mask=np.zeros((80,100),bool);mask[10:50,10:40]=True;mask[60:70,60:70]=True;mask[75,95]=True
        with patch.object(local,'partition',return_value=self.grouped(mask)):
            result=local.connected_partition(mask,[])
        self.assertEqual(len(result['records']),3)
        np.testing.assert_array_equal(result['labels']>0,mask)
        self.assertEqual([r['plan']['mask_pixels'] for r in result['records']],[1200,100,1])
        self.assertEqual(len({r['candidate_id'] for r in result['records']}),3)
        self.assertTrue(all(r['association']['permission_component'] for r in result['records']))

    def test_rejected_owner_remains_rejected_and_excess_components_reject_without_filtering(self):
        mask=np.zeros((40,40),bool);mask[::2,::2]=True
        with patch.object(local,'partition',return_value=self.grouped(mask,'learned_body_owner_unavailable')):
            with self.assertRaisesRegex(ValueError,'resource_limit'):local.connected_partition(mask,[])
        mask[:]=False;mask[2:5,2:5]=True;mask[8:10,8:10]=True
        with patch.object(local,'partition',return_value=self.grouped(mask,'learned_body_owner_ambiguous')):
            result=local.connected_partition(mask,[])
        self.assertTrue(all(r['reason']=='learned_body_owner_ambiguous' for r in result['records']))

    def test_rotated_profile_footprint_must_fit_even_when_tensor_window_is_inside(self):
        permission=np.zeros((200,200),bool);permission[76:124,76:124]=True;normal=np.zeros((200,200),np.float32)
        self.assertFalse(local.profile_supported(permission,normal,100,100))
        permission[60:140,60:140]=True
        self.assertTrue(local.profile_supported(permission,normal,100,100))
        normal[:]=np.pi/4;self.assertTrue(local.profile_supported(permission,normal,100,100))
        permission[100,100]=False;self.assertFalse(local.profile_supported(permission,normal,100,100))

    def test_full_permission_retains_original_pitch_math(self):
        _,x=np.indices((512,512));gray=np.rint(128+60*np.sin(x*2*np.pi/10)).astype(np.uint8)
        mask=np.ones((512,512),bool)
        self.assertEqual(local.estimate_local_pitch(gray,mask,mask),estimate_ridge_pitch(gray,mask))
        self.assertEqual(local.two_scale_local(gray,mask,mask),two_scale_measurement(gray,mask))

    def test_all_four_preprocessing_branches_receive_local_permission(self):
        rgb=np.full((100,100,3),120,np.uint8);mask=np.zeros((100,100),bool);mask[20:30,20:30]=True;seen=[]
        def measure(frame,roi):
            seen.append(roi.copy());return dict(status='insufficient_periodic_patches',pitch=None,count=0,measurements=[],physical_dpi_known=False)
        with (patch.object(local,'prepare_fingerprint',return_value=({'roi':np.ones((512,512),bool)},None,None)),
              patch.object(local,'estimate_ridge_pitch',side_effect=measure)):
            pitch,report,_=local.observed_component_pitch(rgb,[0,0,100,100],mask)
        allowed=cv2.resize(mask.astype(np.uint8),(512,512),interpolation=cv2.INTER_NEAREST)>0
        self.assertIsNone(pitch);self.assertEqual(len(seen),4)
        for roi in seen:np.testing.assert_array_equal(roi,allowed)
        self.assertTrue(report['profile_sampling_inside_permission_required'])

    def test_external_ridges_cannot_supply_pitch_for_uniform_small_permission(self):
        _,x=np.indices((512,512));gray=np.rint(128+60*np.sin(x*2*np.pi/10)).astype(np.uint8)
        gray[:,:160]=128;rgb=np.repeat(gray[:,:,None],3,axis=2);mask=np.zeros(gray.shape,bool);mask[100:164,40:104]=True
        with patch.object(local,'prepare_fingerprint',return_value=({'roi':np.ones((512,512),bool)},None,None)):
            pitch,report,_=local.observed_component_pitch(rgb,[0,0,512,512],mask)
        self.assertIsNone(pitch)
        self.assertTrue(all(a['measurement'].get('count',0)==0 for a in report['attempts'][:2]))

    def test_EXIF_1_to_8_and_fractional_resize_keep_permission_aligned(self):
        rgb=np.full((80,100,3),120,np.uint8);mask=np.zeros((80,100),bool);mask[15:45,20:50]=True;body=np.ones_like(mask)
        for orientation in range(1,9):
            seen=[]
            def observer(image,box,allowed):seen.append(allowed.copy());return None,{},None
            def proposals(*args):return [dict(box=[4,4,36,36],side=32,fragment=1)]
            _,geometry=seeds.prepare_region(rgb,rgb[:,:,0],mask,body,orientation,'source',
                dict(working_scale=1.17,component=1),dict(axis_native_yx=[1.,0.]),_proposals=proposals,_pitch_observer=observer)
            h,w=geometry['working_shape'];expected=cv2.resize(shared.orient(mask.astype(np.uint8),orientation),(w,h),interpolation=cv2.INTER_NEAREST)>0
            self.assertEqual(len(seen),1);np.testing.assert_array_equal(seen[0],expected)


class RendererBindingTests(unittest.TestCase):
    def scoped(self,value=120):
        rgb=np.full((100,100,3),value,np.uint8);mask=np.zeros((100,100),bool);mask[30:70,30:70]=True
        artifact=dict(working_shape=[100,100],working_scale=1.,exif_orientation=1,body=np.ones_like(mask),coarse_mask=mask,
            regions=[dict(working_seed=[30,30,70,70],working_scope=[20,20,80,80],padding=dict(bottom=0,right=0),pitch_measurement={'scope':'local'})])
        geometry=dict(scope=dict(bbox_encoded_original=[0,0,100,100]),observed_pitch_working=8.)
        with patch.object(pipeline,'prepare_body_scale',return_value=(artifact,geometry,{},None)):
            _,_,_,render=pipeline.prepare_scoped_region(rgb,rgb[:,:,0],mask,mask,1,'sha',{}, {})
        return rgb,mask,artifact,render

    def test_renderer_remeasurement_is_local_and_alias_restores_on_exception(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        rgb,mask,artifact,render=self.scoped();before=frozen.observed_seed_pitch
        def observer(image,box,permission):
            np.testing.assert_array_equal(permission,mask);return 8.,{'scope':'local'},np.zeros((512,512),np.uint8)
        def bad(image,*args):
            frozen.observed_seed_pitch(image,[30,30,70,70]);raise RuntimeError('injected renderer failure')
        with patch.object(pipeline,'observed_component_pitch',side_effect=observer),patch.object(pipeline,'render',side_effect=bad):
            with self.assertRaisesRegex(RuntimeError,'injected'):render([1.,0.])
        self.assertIs(frozen.observed_seed_pitch,before)

    def test_renderer_cannot_bypass_or_change_preflight_evidence(self):
        rgb,mask,artifact,render=self.scoped()
        with patch.object(pipeline,'render',return_value=(rgb.copy(),{})):
            with self.assertRaisesRegex(ValueError,'not_called'):render([1.,0.])
        import transform_automatic_fingerprint_poc_v4 as frozen
        def bad(image,*args):frozen.observed_seed_pitch(image,[30,30,70,70]);return image.copy(),{}
        with patch.object(pipeline,'render',side_effect=bad),patch.object(pipeline,'observed_component_pitch',return_value=(9.,{'scope':'local'},None)):
            with self.assertRaisesRegex(ValueError,'remeasurement_mismatch'):render([1.,0.])

    def test_parallel_bindings_restore_and_only_copy_their_component_pixels(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        cases=[self.scoped(100),self.scoped(180)];before=frozen.observed_seed_pitch
        def observer(image,box,permission):return 8.,{'scope':'local'},np.zeros((512,512),np.uint8)
        def render(image,*args):
            frozen.observed_seed_pitch(image,[30,30,70,70]);return np.full_like(image,220),{}
        with patch.object(pipeline,'render',side_effect=render),patch.object(pipeline,'observed_component_pitch',side_effect=observer):
            with concurrent.futures.ThreadPoolExecutor(2) as pool:outputs=list(pool.map(lambda c:c[3]([1.,0.])[0],cases))
        for (original,mask,_,_),out in zip(cases,outputs):
            np.testing.assert_array_equal(out[~mask],original[~mask]);self.assertTrue(np.all(out[mask]==220))
        self.assertIs(frozen.observed_seed_pitch,before)


if __name__=='__main__':unittest.main()
