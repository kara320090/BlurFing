import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from pitch_free_artifacts_v1 import save_artifacts,candidate_application
from pad_refinement_data_contract_v2 import digest


class ArtifactTests(unittest.TestCase):
    def test_candidate_can_be_larger_than_applied_mask_without_implying_success(self):
        candidate=np.zeros((8,12),bool);candidate[1:7,2:10]=True
        final=np.zeros_like(candidate);final[1:4,2:10]=True;final[0,0]=True
        before=candidate.copy();report=candidate_application(candidate,final)
        self.assertEqual(report['candidate_pixels'],48)
        self.assertEqual(report['applied_candidate_pixels'],24)
        self.assertEqual(report['unapplied_candidate_pixels'],24)
        self.assertEqual(report['applied_outside_candidate_pixels'],1)
        self.assertEqual(report['candidate_applied_fraction'],.5)
        self.assertFalse(report['candidate_fully_applied'])
        self.assertFalse(report['GT_coverage_measured'])
        self.assertFalse(report['complete_fingerprint_protection_verified'])
        np.testing.assert_array_equal(candidate,before)

    def test_empty_candidate_is_not_perfect_coverage(self):
        empty=np.zeros((3,4),bool)
        report=candidate_application(empty,np.ones_like(empty))
        self.assertIsNone(report['candidate_applied_fraction'])
        self.assertFalse(report['candidate_fully_applied'])
        self.assertEqual(report['applied_outside_candidate_pixels'],12)
        with self.assertRaises(ValueError):candidate_application(empty,empty.T)
        with self.assertRaises(ValueError):candidate_application(empty,empty.astype(np.uint8))

    def test_exact_RGB_EXIF_mask_roundtrip_and_fresh_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rgb=np.arange(12*16*3,dtype=np.uint8).reshape(12,16,3)
            mask=np.zeros((12,16),bool);mask[2:6,3:8]=True;returned=rgb.copy();returned[mask]=0
            for orientation in range(1,9):
                exif=Image.Exif();exif[274]=orientation;source=root/'source.png';Image.fromarray(rgb).save(source,exif=exif)
                identity=dict(original_source_sha256=digest(source),source_exif_orientation=orientation)
                out=root/str(orientation);out.mkdir();before=source.read_bytes()
                result=save_artifacts(source,identity,rgb,mask,mask,returned,out)
                with Image.open(out/'protected.png') as im:
                    self.assertEqual(im.getexif()[274],orientation);np.testing.assert_array_equal(np.asarray(im),returned)
                    expected_size=ImageOps.exif_transpose(im).size
                with Image.open(out/'refined_mask.png') as im:
                    self.assertEqual(ImageOps.exif_transpose(im).size,expected_size)
                    np.testing.assert_array_equal(np.asarray(im)>0,mask)
                self.assertEqual(source.read_bytes(),before);self.assertTrue(result['review_required'])
                with self.assertRaises(FileExistsError):save_artifacts(source,identity,rgb,mask,mask,returned,out)


if __name__=='__main__':unittest.main()
