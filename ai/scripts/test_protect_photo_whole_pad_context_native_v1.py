import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_protect_photo_learned_v1 as original
import protect_photo_whole_pad_context_native_v1 as pipeline


class NativeDecisionInputContracts(unittest.TestCase):
    def setUp(self):
        binding=patch.object(original,'pipeline',pipeline);binding.start();self.addCleanup(binding.stop)
    test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF=original.PhotoEntryTests.test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF
    test_unsupported_depth_and_invalid_EXIF_reject_without_output=original.PhotoEntryTests.test_unsupported_depth_and_invalid_EXIF_reject_without_output
    test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker=original.PhotoEntryTests.test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker

    def test_invalid_detect_only_stops_both_entrypoints_before_IO(self):
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):pipeline.run('unused','unused','unused','unused',detect_only='false')
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):pipeline.protect_bundle('unused','unused','unused',detect_only='false')
        with self.assertRaisesRegex(ValueError,'development_replay_flag_must_be_boolean'):
            pipeline.run('unused','unused','unused','unused',development_replay='false')

    def test_consumed_source_is_rejected_by_default_before_model_or_worker(self):
        from test_pad_refinement_tiles_v3 import TileFixture
        fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        source=Path(fixture.inputs[0]['source_path']);fixture.registry[0].update(pipeline.image_identity(source))
        registry=fixture.root/'registry.json';registry.write_text(json.dumps(fixture.registry))
        output=fixture.root/'result'
        with patch.object(pipeline,'load_model') as model,patch.object(pipeline.subprocess,'run') as worker:
            with self.assertRaisesRegex(ValueError,'consumed_source_or_decoded_pixels_forbidden'):
                pipeline.run(source,fixture.root/'model',registry,output)
        self.assertFalse(output.exists());model.assert_not_called();worker.assert_not_called()

    def test_bundle_calls_V12_on_bound_permission_and_retains_development_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'output';source=dict(source_id='INPUT',source_path='unused')
            mask=np.ones((16,16),bool);returned=np.full((16,16,3),120,np.uint8);calls=[]
            def infer(folder,inputs,out):
                out.mkdir(parents=True);Image.fromarray(mask.astype(np.uint8)*255).save(out/'INPUT.png')
                return dict(input_manifest_sha256='manifest',model_sha256='model',rows=[dict(source_id='INPUT',prediction_sha256='png')])
            def evaluate(actual,permission,sha,*,detect_only):
                calls.append(actual);np.testing.assert_array_equal(permission,mask)
                self.assertEqual(sha,pipeline.pixel_hash(mask));self.assertTrue(detect_only)
                return returned,dict(status='detected',fingerprints_transformed=0)
            with (patch.object(pipeline,'infer',side_effect=infer),patch.object(pipeline,'json_snapshot',return_value=({'sources':[source]},'manifest')),
                  patch.object(pipeline,'read_mask',return_value=mask),patch.object(pipeline,'native_shape',return_value=(16,16)),
                  patch.object(pipeline,'evaluate_learned_mask',side_effect=evaluate),patch.object(pipeline,'save_result'),
                  patch.object(pipeline,'unchanged'),patch.object(pipeline,'check_tiles')):
                report=pipeline.protect_bundle(root,root,output,True)
            self.assertEqual(calls,[source]);self.assertEqual(report['version'],pipeline.PIPELINE_VERSION)
            self.assertFalse(report['default_pipeline_enabled']);self.assertFalse(report['independent_final_test'])
            self.assertFalse(report['rows'][0]['GT_used']);self.assertTrue((output/'protection.private.json').is_file())

    def test_existing_bundle_output_stops_before_prediction(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(pipeline,'infer') as infer:
            with self.assertRaises(FileExistsError):pipeline.protect_bundle(tmp,tmp,tmp)
            infer.assert_not_called()


if __name__=='__main__':unittest.main()
