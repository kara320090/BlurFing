import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
import photo_rejection_resolution_v1 as resolution


class RejectionResolutionTests(unittest.TestCase):
    def fixture(self):
        rgb=np.full((40,60,3),[121,142,164],np.uint8)
        labels=np.zeros((40,60),np.uint16);labels[3:17,4:20]=1;labels[4:22,30:50]=2
        allowed=labels>0;accepted=labels==1;returned=rgb.copy();returned[accepted]=[163,132,118]
        rows=[]
        for i in (1,2):
            rows.append(dict(region_id=i,candidate_id='owner-'+str(i),mask_pixels=int((labels==i).sum()),
                mask_pixel_sha256=resolution.pixel_hash(labels==i),status='transformed' if i==1 else 'rejected',
                reason=None if i==1 else 'insufficient_features'))
        rows[0]['renderer_details']=dict(regions=[dict(applied=True,returned_RGB_structure_check=dict(structure_change_passed=True))])
        rows[1]['renderer_details']=dict(regions=[dict(applied=False,structure_check=dict(reason='insufficient_features',minutiae=dict(before_count=34,after_count=2)))])
        report=dict(regions=rows,status='partial_success',fingerprints_transformed=1,fingerprints_rejected=1,
            prediction_pixel_sha256=resolution.pixel_hash(allowed),returned_RGB_sha256=resolution.pixel_hash(returned))
        return rgb,returned,allowed,accepted,labels,report

    def test_actual_mask_coverage_without_false_native_success(self):
        args=self.fixture();pins=[a.copy() for a in args[:-1]];before=copy.deepcopy(args[-1])
        rgb,returned,permission,accepted,labels,report=args
        covered,fallback,info=resolution.cover_rejected(*args)
        np.testing.assert_array_equal(fallback,labels==2)
        self.assertTrue((covered[fallback]==0).all())
        np.testing.assert_array_equal(covered[accepted],returned[accepted])
        np.testing.assert_array_equal(covered[~permission],rgb[~permission])
        self.assertEqual(info['native_rejected_regions'],1);self.assertEqual(info['untreated_candidate_pixels'],0)
        self.assertFalse(info['rejected_transform_counted_as_success']);self.assertFalse(info['privacy_validated'])
        for actual,old in zip(args[:-1],pins):np.testing.assert_array_equal(actual,old)
        self.assertEqual(report,before)

    def test_rejected_source_pixels_cannot_leak_through_solid_fill(self):
        args=self.fixture();out,_,_=resolution.cover_rejected(*args)
        rgb,returned,permission,accepted,labels,report=args
        rgb[labels==2]=[250,80,12];returned[labels==2]=rgb[labels==2]
        report['returned_RGB_sha256']=resolution.pixel_hash(returned)
        again,_,_=resolution.cover_rejected(*args)
        np.testing.assert_array_equal(out,again)

    def test_no_fallback_can_conceal_processing_errors_or_unknown_rejections(self):
        for update in [dict(error='RuntimeError'),dict(reject_reason='bad_contract'),dict(detect_only=True)]:
            args=self.fixture();args[-1].update(update)
            with self.assertRaisesRegex(ValueError,'report_contract'):resolution.cover_rejected(*args)
        args=self.fixture();args[-1]['regions'][1]['reason']='some_new_error'
        with self.assertRaisesRegex(ValueError,'normal_quality_rejection'):resolution.cover_rejected(*args)
        args=self.fixture();args[-1]['regions'][1]['error']='OSError'
        args[-1]['regions'][1]['reason']='extractor_unavailable'
        with self.assertRaisesRegex(ValueError,'processing_error: region 2: OSError: extractor_unavailable'):
            resolution.cover_rejected(*args)

    def test_tampered_hashes_masks_and_fake_success_are_rejected(self):
        args=self.fixture();args[1][39,59]=0
        with self.assertRaisesRegex(ValueError,'partition_contract'):resolution.cover_rejected(*args)
        args=self.fixture();args[-1]['regions'][1]['mask_pixel_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'binding_mismatch'):resolution.cover_rejected(*args)
        args=self.fixture();args[-1]['regions'][0]['renderer_details']['regions'][0]['returned_RGB_structure_check']['structure_change_passed']=False
        with self.assertRaisesRegex(ValueError,'unverified_transform'):resolution.cover_rejected(*args)
        args=self.fixture();args[3][5,31]=True
        with self.assertRaisesRegex(ValueError,'accepted_contract'):resolution.cover_rejected(*args)

    def test_feature_failure_explanation_distinguishes_original_from_transformed(self):
        for before,after,expected in [(0,0,'original_and_returned_features_insufficient'),(8,30,'original_features_insufficient'),(34,2,'returned_features_insufficient')]:
            report=self.fixture()[-1];check=report['regions'][1]['renderer_details']['regions'][0]['structure_check']
            check['minutiae']=dict(before_count=before,after_count=after)
            self.assertEqual(resolution.explain_regions(report)['regions'][1]['cause'],expected)

    def test_empty_detection_is_not_success_and_already_black_is_still_handled(self):
        rgb=np.zeros((10,10,3),np.uint8);mask=np.zeros((10,10),bool);labels=np.zeros((10,10),np.uint16)
        report=dict(status='rejected',regions=[],fingerprints_transformed=0,fingerprints_rejected=0,
            prediction_pixel_sha256=resolution.pixel_hash(mask),returned_RGB_sha256=resolution.pixel_hash(rgb))
        out,_,info=resolution.cover_rejected(rgb,rgb,mask,mask,labels,report)
        self.assertEqual(info['status'],'no_candidates');self.assertFalse(info['candidate_area_handled'])
        args=self.fixture();args[0][args[4]==2]=0;args[1][args[4]==2]=0
        args[-1]['returned_RGB_sha256']=resolution.pixel_hash(args[1])
        _,_,info=resolution.cover_rejected(*args)
        self.assertEqual(info['solid_redaction_pixels'],360)

    def test_saved_alternative_preserves_native_output_and_EXIF(self):
        from photo_source_rgb_v1 import canonical_rgb
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);args=self.fixture();source=out/'source.png';exif=Image.Exif();exif[274]=6
            Image.fromarray(args[0]).save(source,exif=exif)
            _,identity=canonical_rgb(source)
            protected=out/'protected.png';Image.fromarray(args[1]).save(protected,exif=exif)
            before=protected.read_bytes()
            details=resolution.save_resolution_artifacts(source,identity,*args,out)
            self.assertEqual(protected.read_bytes(),before)
            with Image.open(out/'covered.png') as image:
                self.assertEqual(image.getexif()[274],6)
                np.testing.assert_array_equal(np.asarray(image)[args[4]==2],0)
            self.assertEqual(details['resolution']['native_transform_status'],'partial_success')
            self.assertTrue((out/'resolution.html').is_file())
            with self.assertRaises(FileExistsError):resolution.save_resolution_artifacts(source,identity,*args,out)


if __name__=='__main__':unittest.main()
