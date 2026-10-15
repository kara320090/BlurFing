import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import torch
import test_protect_photo_learned_v1 as original
import protect_photo_whole_pad_v2 as pipeline
import infer_whole_pad_target_v4 as infer
from train_whole_pad_target_v4 import PROTOCOL,PROTOCOL_SHA256,code_hashes


class WholePadEntryTests(unittest.TestCase):
    def test_truthy_spatial_flag_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):pipeline.run('unused','unused','unused','unused',spatial_observation='false')
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):infer.protect_bundle('unused','unused','unused',spatial_observation='false')
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):infer.protect_bundle('unused','unused','unused',multiscale_observation='false')
        with self.assertRaisesRegex(ValueError,'conflicting'):pipeline.run('unused','unused','unused','unused',spatial_observation=True,multiscale_observation=True)
        with self.assertRaisesRegex(ValueError,'conflicting'):infer.protect_bundle('unused','unused','unused',spatial_observation=True,multiscale_observation=True)

    def test_V3_or_incomplete_config_cannot_load_as_V4(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'final_config.private.json').write_text(json.dumps(dict(training_complete=True)))
            with patch.object(infer,'load_checkpoint') as load:
                with self.assertRaisesRegex(ValueError,'V4_development'):infer.load_model(folder)
            load.assert_not_called()

    def test_fresh_loader_sets_same_determinism_and_checks_config_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);config=dict(training_complete=True,development_only=True,approved_for_inference=False,
                independent_final_test=False,protocol=dict(PROTOCOL),protocol_sha256=PROTOCOL_SHA256,
                source_code_sha256=code_hashes(),threshold=.5,model_sha256='0'*64)
            (folder/'final_config.private.json').write_text(json.dumps(config))
            threads=torch.get_num_threads();deterministic=torch.are_deterministic_algorithms_enabled()
            try:
                torch.set_num_threads(2);torch.use_deterministic_algorithms(False)
                def load(*args):
                    self.assertEqual(torch.get_num_threads(),8);self.assertTrue(torch.are_deterministic_algorithms_enabled());return object()
                with patch.object(infer,'load_checkpoint',side_effect=load):infer.load_model(folder)
            finally:torch.set_num_threads(threads);torch.use_deterministic_algorithms(deterministic)


class WholePadInputContracts(unittest.TestCase):
    def setUp(self):
        binding=patch.object(original,'pipeline',pipeline);binding.start();self.addCleanup(binding.stop)
    test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF=original.PhotoEntryTests.test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF
    test_unsupported_depth_and_invalid_EXIF_reject_without_output=original.PhotoEntryTests.test_unsupported_depth_and_invalid_EXIF_reject_without_output
    test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker=original.PhotoEntryTests.test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker


if __name__=='__main__':unittest.main()
