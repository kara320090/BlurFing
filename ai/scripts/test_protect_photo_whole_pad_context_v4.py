import unittest
from unittest.mock import patch
import test_protect_photo_learned_v1 as original
import protect_photo_whole_pad_context_v4 as pipeline


class ContextPhotoInputContracts(unittest.TestCase):
    def setUp(self):
        binding=patch.object(original,'pipeline',pipeline);binding.start();self.addCleanup(binding.stop)
    test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF=original.PhotoEntryTests.test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF
    test_unsupported_depth_and_invalid_EXIF_reject_without_output=original.PhotoEntryTests.test_unsupported_depth_and_invalid_EXIF_reject_without_output
    test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker=original.PhotoEntryTests.test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker

    def test_truthy_detect_only_stops_before_IO(self):
        with self.assertRaisesRegex(ValueError,'must_be_boolean'):
            pipeline.run('unused','unused','unused','unused',detect_only='false')


if __name__=='__main__': unittest.main()
