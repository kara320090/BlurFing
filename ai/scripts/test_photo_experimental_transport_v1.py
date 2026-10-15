"""Generated arrays and declared fake evidence test transport only, never AI scores."""
import base64
import copy
import hashlib
import io
import json
import struct
import unittest
import zlib
from unittest.mock import patch
import numpy as np
from PIL import Image
from photo_experimental_transport_v1 import validate_native_result,require_android_request_orientation,sha,ENTRYPOINTS,decode_request_png,png


class ExperimentalPhotoContractTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((12,16,3),120,np.uint8);self.returned=self.rgb.copy()
        self.labels=np.zeros((12,16),np.uint16);self.labels[2:7,2:7]=1;self.labels[3,3]=0;self.labels[8:10,10:14]=2
        self.permission=self.labels>0;self.returned[2,2]=121;self.source_sha='a'*64
        rows=[]
        for region in (1,2):
            mask=self.labels==region
            rows.append(dict(region_id=region,mask_pixel_sha256=sha(mask),mask_pixels=int(mask.sum()),
                status='transformed' if region==1 else 'rejected',quality_status='TRANSFORMED' if region==1 else 'REJECT_PITCH_UNOBSERVED',
                reason='C:\\PRIVATE\\never-expose-me.png',renderer_details=dict(structure_checked_on_actual_native_return=True,final_native_gate_authoritative=True,
                regions=[dict(structure_check=dict(structure_change_passed=True),returned_RGB_structure_check=dict(structure_change_passed=True))])))
        self.report=dict(single_photo_entrypoint=ENTRYPOINTS['native_v12'],status='partial_success',regions=rows,
            fingerprints_detected=2,fingerprints_transformed=1,fingerprints_rejected=1,changed_pixels=1,
            input_identity=dict(original_source_sha256=self.source_sha,canonical_RGB_sha256=sha(self.rgb),source_exif_orientation=1),
            coordinate_system='encoded_original_pixels',prediction_pixel_sha256=sha(self.permission),
            returned_RGB_sha256=sha(self.returned),approved_for_protection=False,privacy_validated=False)

    def validate(self,**kwargs):
        config=dict(source_sha256=self.source_sha,engine='native_v12',orientation=1);config.update(kwargs)
        return validate_native_result(self.rgb,self.returned,self.permission,self.labels,self.report,**config)

    def rehash(self):self.report['returned_RGB_sha256']=sha(self.returned);self.report['changed_pixels']=int(np.any(self.returned!=self.rgb,axis=2).sum())

    def test_partial_uses_exact_actual_masks_and_sanitized_bounds(self):
        result=self.validate();wire=result.response('synthetic-request',150)
        self.assertEqual(wire['status'],'partial_success');self.assertEqual(wire['transformed_components'],1)
        self.assertEqual(wire['rejected_components'],1);self.assertEqual(wire['result_kind'],'experimental')
        self.assertEqual(wire['accepted_permission_mask']['pixels'],24);self.assertEqual(wire['rejected_permission_mask']['pixels'],8)
        mask=np.asarray(Image.open(io.BytesIO(base64.b64decode(wire['accepted_permission_mask']['image_base64']))))>0
        np.testing.assert_array_equal(mask,self.labels==1)
        self.assertFalse(mask[3,3]);self.assertTrue(wire['bounds_are_not_filled_permission'])
        self.assertFalse(wire['privacy_validated']);self.assertFalse(wire['complete_photo_protection_verified'])
        self.assertIsNone(wire['evaluation']);self.assertNotIn('applied_regions',wire)
        self.assertNotIn('PRIVATE',json.dumps(wire));self.assertNotIn('before_count',json.dumps(wire))

    def test_entire_rejection_returns_exact_source_and_no_accepted_mask(self):
        self.returned=self.rgb.copy();self.report['regions'][0]['status']='rejected'
        self.report.update(status='rejected',fingerprints_transformed=0,fingerprints_rejected=2);self.rehash()
        result=self.validate();self.assertEqual(result.accepted['pixels'],0);self.assertEqual(result.refused['pixels'],32)
        np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(result.returned_png))),self.rgb)

    def test_empty_permission_is_rejected_without_fabricated_region(self):
        self.labels.fill(0);self.permission=self.labels>0;self.returned=self.rgb.copy()
        self.report.update(status='rejected',regions=[],fingerprints_detected=0,fingerprints_transformed=0,fingerprints_rejected=0,
            prediction_pixel_sha256=sha(self.permission));self.rehash()
        result=self.validate();self.assertEqual(result.detected,0);self.assertEqual(result.changed_pixels,0)

    def test_changed_pixel_in_bounding_box_hole_fails_exact_permission(self):
        self.returned[3,3]=121;self.rehash()
        with self.assertRaisesRegex(ValueError,'outside_accepted'):self.validate()

    def test_rejected_region_change_fails_even_when_inside_prediction(self):
        self.returned[8,10]=121;self.rehash()
        with self.assertRaisesRegex(ValueError,'rejected_region'):self.validate()

    def test_working_pass_without_actual_native_evidence_is_not_accepted(self):
        self.report['regions'][0]['renderer_details']['structure_checked_on_actual_native_return']=False
        with self.assertRaisesRegex(ValueError,'actual_native_gate'):self.validate()

    def test_missing_candidate_or_fabricated_accepted_region_fails(self):
        self.report['regions']=self.report['regions'][:1]
        with self.assertRaisesRegex(ValueError,'partition_identity'):self.validate()

    def test_wrong_region_mask_hash_fails(self):
        self.report['regions'][0]['mask_pixel_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'region_permission'):self.validate()

    def test_false_success_or_success_with_no_changed_RGB_fails(self):
        self.report['status']='success'
        with self.assertRaisesRegex(ValueError,'counts_mismatch'):self.validate()
        self.report['status']='partial_success';self.returned=self.rgb.copy();self.rehash()
        with self.assertRaisesRegex(ValueError,'without_actual_RGB'):self.validate()

    def test_wrong_source_or_returned_hash_fails(self):
        with self.assertRaisesRegex(ValueError,'source_binding'):self.validate(source_sha256='b'*64)
        self.report['returned_RGB_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'returned_RGB_hash'):self.validate()

    def test_coordinate_and_partition_shape_mismatch_fails(self):
        self.report['coordinate_system']='upright_pixels'
        with self.assertRaisesRegex(ValueError,'source_binding'):self.validate()
        self.report['coordinate_system']='encoded_original_pixels';self.labels=self.labels.T
        with self.assertRaisesRegex(ValueError,'partition'):self.validate()

    def test_boolean_count_and_approval_flags_not_silently_coerced(self):
        self.report['fingerprints_transformed']=True
        with self.assertRaisesRegex(ValueError,'invalid_transformed'):self.validate()
        self.report['fingerprints_transformed']=1;self.report['privacy_validated']=True
        with self.assertRaisesRegex(ValueError,'approval_flags'):self.validate()

    def test_geometry_method_is_explicit_and_warning_preserves_regression(self):
        self.report['single_photo_entrypoint']=ENTRYPOINTS['distal_v13'];result=self.validate(engine='distal_v13')
        response=result.response('synthetic-geometry',1)
        self.assertEqual(response['method'],'photo_distal_v13_geometry_experimental')
        self.assertIn('GEOMETRY_BOUNDARIES_REQUIRE_REVIEW_ACCURACY_REGRESSION_OBSERVED',response['warnings'])
        self.assertNotEqual(response['method'],'gaussian_blur')

    def test_selected_engine_mismatch_never_relabels_native_as_geometry(self):
        with self.assertRaisesRegex(ValueError,'engine_binding'):self.validate(engine='distal_v13')

    def test_encoded_EXIF_preserved_but_android_endpoint_requires_normalized_input(self):
        for orientation in range(1,9):
            self.report['input_identity']['source_exif_orientation']=orientation
            result=self.validate(orientation=orientation)
            with Image.open(io.BytesIO(result.returned_png)) as im:self.assertEqual(im.getexif()[274],orientation)
            self.assertEqual((result.width,result.height),(16,12))
        require_android_request_orientation(1)
        for orientation in (True,0,2,6,9,'1'):
            with self.subTest(orientation=orientation),self.assertRaises(ValueError):require_android_request_orientation(orientation)

    def test_oversize_lossless_result_is_rejected_without_downscale_or_JPEG(self):
        with patch('photo_experimental_transport_v1.MAX_RETURNED_PNG_BYTES',10),self.assertRaisesRegex(ValueError,'lossless_limit'):
            self.validate()

    def test_pose_empty_is_explicit_verified_rejection_without_report_mutation(self):
        self.labels.fill(0);self.permission=self.labels>0;self.returned=self.rgb.copy()
        self.report.update(single_photo_entrypoint=ENTRYPOINTS['pose_v14'],status='rejected',regions=[],
            fingerprints_detected=0,fingerprints_transformed=0,fingerprints_rejected=0,
            reject_reason='pose_exactly_one_observed_hand_required')
        del self.report['prediction_pixel_sha256'];self.rehash();before=copy.deepcopy(self.report)
        with self.assertRaisesRegex(ValueError,'permission_hash'):self.validate(engine='pose_v14')
        result=self.validate(engine='pose_v14',verified_empty_permission_reason=self.report['reject_reason'])
        self.assertEqual(self.report,before);wire=result.response('pose-nohand',0)
        self.assertEqual(wire['candidate_components'],0);self.assertEqual(wire['status'],'rejected')
        self.assertEqual(wire['method'],'photo_pose_v14_geometry_experimental')
        self.assertIn('POSE_GEOMETRY_BOUNDARIES_REQUIRE_REVIEW',wire['warnings'])
        with self.assertRaisesRegex(ValueError,'empty_permission_proof'):self.validate(engine='pose_v14',verified_empty_permission_reason='different')
        self.report['prediction_pixel_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'permission_hash'):self.validate(engine='pose_v14',verified_empty_permission_reason=self.report['reject_reason'])

    def test_native_gate_must_be_authoritative_and_same_actual_return_evidence(self):
        details=self.report['regions'][0]['renderer_details'];details['final_native_gate_authoritative']=False
        with self.assertRaisesRegex(ValueError,'actual_native_gate'):self.validate()
        details['final_native_gate_authoritative']=True;details['regions'][0]['returned_RGB_structure_check']={'structure_change_passed':False}
        with self.assertRaisesRegex(ValueError,'actual_native_gate'):self.validate()

    def test_request_RGB_roundtrip_and_rejects_conversion_or_EXIF(self):
        np.testing.assert_array_equal(decode_request_png(png(self.rgb)),self.rgb)
        for pixels in [np.dstack([self.rgb,np.full(self.rgb.shape[:2],255,np.uint8)]),self.rgb[:,:,0]]:
            with self.assertRaisesRegex(ValueError,'RGB8'):decode_request_png(png(pixels))
        with self.assertRaisesRegex(ValueError,'EXIF_1'):decode_request_png(png(self.rgb,6))

    def test_request_crc_trailing_bytes_and_resource_bounds_fail(self):
        content=bytearray(png(self.rgb));content[29]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):decode_request_png(bytes(content))
        with self.assertRaisesRegex(ValueError,'IEND'):decode_request_png(png(self.rgb)+b'junk')
        with patch('photo_experimental_transport_v1.MAX_REQUEST_PNG_BYTES',10),self.assertRaisesRegex(ValueError,'byte_limit'):decode_request_png(png(self.rgb))
        with patch('photo_experimental_transport_v1.MAX_PIXELS',10),self.assertRaisesRegex(ValueError,'size_or_encoding'):decode_request_png(png(self.rgb))

    def test_request_truecolor16_tRNS_APNG_and_interlace_are_rejected(self):
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        def tiny(depth=8,interlace=0,extras=b''):
            return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,depth,2,0,0,interlace))+
                extras+chunk(b'IDAT',zlib.compress(b'\0'+b'\0'*(3*(depth//8))))+chunk(b'IEND',b''))
        with Image.open(io.BytesIO(tiny(16))) as im:self.assertEqual(im.mode,'RGB') # Inferred RGB hides 16-bit source.
        with self.assertRaisesRegex(ValueError,'RGB8'):decode_request_png(tiny(16))
        with self.assertRaisesRegex(ValueError,'opaque_single_frame'):decode_request_png(tiny(extras=chunk(b'tRNS',b'\0'*6)))
        with self.assertRaisesRegex(ValueError,'opaque_single_frame'):decode_request_png(tiny(extras=chunk(b'acTL',struct.pack('>II',1,0))))
        with self.assertRaisesRegex(ValueError,'size_or_encoding'):decode_request_png(tiny(interlace=1))
        output=io.BytesIO();first=Image.fromarray(self.rgb);second=Image.fromarray(self.returned)
        first.save(output,format='PNG',save_all=True,append_images=[second],duration=100,loop=0)
        with self.assertRaisesRegex(ValueError,'opaque_single_frame'):decode_request_png(output.getvalue())

    @staticmethod
    def png_chunks(content):
        rows=[];at=8
        while at<len(content):
            size=struct.unpack('>I',content[at:at+4])[0]
            rows.append((content[at+4:at+8],content[at+8:at+8+size]));at+=size+12
        return rows

    @staticmethod
    def from_chunks(rows):
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        return b'\x89PNG\r\n\x1a\n'+b''.join(chunk(kind,data) for kind,data in rows)

    def test_duplicate_late_EXIF_and_single_duplicate_orientation_tag_are_rejected(self):
        rows=self.png_chunks(png(self.rgb));late=[row for row in self.png_chunks(png(self.rgb,6)) if row[0]==b'eXIf']
        with self.assertRaisesRegex(ValueError,'duplicate_or_late_EXIF'):decode_request_png(self.from_chunks(rows[:-1]+late+rows[-1:]))
        little=b'II'+struct.pack('<HIH',42,8,2)+struct.pack('<HHIHH',274,3,1,1,0)*2+struct.pack('<I',0)
        rows=[(kind,little if kind==b'eXIf' else data) for kind,data in rows]
        with self.assertRaisesRegex(ValueError,'EXIF_1'):decode_request_png(self.from_chunks(rows))

    def test_unknown_critical_reserved_or_nonletter_chunk_is_rejected(self):
        rows=self.png_chunks(png(self.rgb))
        for kind in (b'ABCD',b'PLTE',b'abcd',b'a1Cd'):
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'unknown_critical|chunk_type'):
                decode_request_png(self.from_chunks(rows[:1]+[(kind,b'')]+rows[1:]))

    def test_nonconsecutive_IDAT_rejected_but_consecutive_split_is_valid(self):
        rows=self.png_chunks(png(self.rgb));split=[]
        for kind,data in rows:
            if kind==b'IDAT':split.extend([(kind,data[:len(data)//2]),(kind,data[len(data)//2:])])
            else:split.append((kind,data))
        np.testing.assert_array_equal(decode_request_png(self.from_chunks(split)),self.rgb)
        split=rows[:-1]+[(b'tEXt',b'name\0value'),(b'IDAT',b'')]+rows[-1:]
        with self.assertRaisesRegex(ValueError,'nonconsecutive_IDAT'):decode_request_png(self.from_chunks(split))

    def test_exact_zlib_eof_and_filtered_scanline_size_are_required(self):
        rows=self.png_chunks(png(self.rgb));compressed=b''.join(data for kind,data in rows if kind==b'IDAT')
        def encoded(payload):return self.from_chunks([(kind,payload if kind==b'IDAT' else data) for kind,data in rows])
        for payload in (compressed+b'extra',compressed+zlib.compress(b'other')):
            with self.assertRaisesRegex(ValueError,'trailing_zlib'):decode_request_png(encoded(payload))
        for payload in (compressed[:-1],zlib.compress(b'\0'),zlib.compress(b'\0'*(self.rgb.shape[0]*(self.rgb.shape[1]*3+1)+1))):
            with self.assertRaisesRegex(ValueError,'scanline_size'):decode_request_png(encoded(payload))

    def test_deflate_bomb_check_uses_bounded_output_without_flush(self):
        import photo_experimental_transport_v1 as contract
        rows=self.png_chunks(png(self.rgb));bomb=zlib.compress(b'\0'*(2*1024*1024))
        data=self.from_chunks([(kind,bomb if kind==b'IDAT' else payload) for kind,payload in rows])
        real=zlib.decompressobj;limits=[]
        class Bounded:
            def __init__(self):self.real=real()
            def __getattr__(self,name):return getattr(self.real,name)
            def decompress(self,value,max_length):
                limits.append((len(value),max_length));return self.real.decompress(value,max_length)
            def flush(self,*args):raise AssertionError('unbounded flush forbidden')
        with patch.object(contract.zlib,'decompressobj',side_effect=Bounded),self.assertRaisesRegex(ValueError,'scanline_size'):
            decode_request_png(data)
        self.assertTrue(limits);self.assertTrue(all(a<=65536 and b==65536 for a,b in limits))

    def test_filter_byte_0_to_4_required_at_each_streamed_scanline(self):
        rows=self.png_chunks(png(self.rgb));stride=self.rgb.shape[1]*3+1
        raw=bytearray(self.rgb.shape[0]*stride);raw[stride]=5
        invalid=self.from_chunks([(kind,zlib.compress(raw) if kind==b'IDAT' else payload) for kind,payload in rows])
        with self.assertRaisesRegex(ValueError,'scanline_filter'):decode_request_png(invalid)
        for filter_value in range(5):
            raw=bytearray(self.rgb.shape[0]*stride)
            for y in range(self.rgb.shape[0]):raw[y*stride]=filter_value
            content=self.from_chunks([(kind,zlib.compress(raw) if kind==b'IDAT' else payload) for kind,payload in rows])
            self.assertEqual(decode_request_png(content).shape,self.rgb.shape)

    def test_response_request_id_matches_HTTP_ASCII_contract(self):
        result=self.validate()
        for value in ['550e8400-e29b-41d4-a716-446655440000','photo:case_1.v2','A'*200,'0']:
            with self.subTest(valid=value):self.assertEqual(result.response(value,1)['request_id'],value)
        for value in ['',None,True,123,'A'*201,'photo test',' test','test ','test\n','test\r','test\t','test\0','test/path','test\\path','한글','é','Ａ','_start',':start']:
            with self.subTest(invalid=value),self.assertRaisesRegex(ValueError,'invalid_request_id'):result.response(value,1)

    def test_canonical_source_rejects_all_color_and_HDR_metadata_chunks(self):
        rows=self.png_chunks(png(self.rgb))
        values={b'iCCP':b'synthetic\0\0'+zlib.compress(b'not-a-biometric-asset'),b'cICP':bytes([1,13,0,1]),
            b'gAMA':struct.pack('>I',45455),b'cHRM':struct.pack('>8I',31270,32900,64000,33000,30000,60000,15000,6000),
            b'mDCV':b'\0'*24,b'cLLI':b'\0'*8,b'sRGB':b'\0',b'sBIT':bytes([8,8,8])}
        for kind,data in values.items():
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'noncanonical_metadata'):
                decode_request_png(self.from_chunks(rows[:1]+[(kind,data)]+rows[1:]))

    def test_canonical_source_rejects_noncolor_ancillary_chunks_too(self):
        rows=self.png_chunks(png(self.rgb))
        for kind,data in [(b'tEXt',b'title\0synthetic'),(b'zTXt',b'title\0\0'+zlib.compress(b'synthetic')),
                          (b'iTXt',b'title\0\0\0\0\0synthetic'),(b'pHYs',struct.pack('>IIB',100,100,1)),
                          (b'tIME',struct.pack('>HBBBBB',2026,1,1,0,0,0)),(b'bKGD',b'\0'*6)]:
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'noncanonical_metadata'):
                decode_request_png(self.from_chunks(rows[:1]+[(kind,data)]+rows[1:]))

    def test_canonical_EXIF_is_optional_minimal_orientation_only(self):
        rows=self.png_chunks(png(self.rgb));plain=[row for row in rows if row[0]!=b'eXIf']
        np.testing.assert_array_equal(decode_request_png(self.from_chunks(plain)),self.rgb)
        minimal=b'II'+struct.pack('<HIHHHIHHI',42,8,1,274,3,1,1,0,0)
        np.testing.assert_array_equal(decode_request_png(self.from_chunks(plain[:1]+[(b'eXIf',minimal)]+plain[1:])),self.rgb)
        changed=[]
        extra=minimal[:8]+struct.pack('<H',2)+minimal[10:22]+struct.pack('<HHIHH',40961,3,1,1,0)+struct.pack('<I',0)
        changed.append(extra)
        pointer=bytearray(minimal);pointer[22:26]=struct.pack('<I',8);changed.append(bytes(pointer))
        color_tag=bytearray(minimal);color_tag[10:12]=struct.pack('<H',40961);changed.append(bytes(color_tag))
        changed.append(minimal+b'extra')
        for metadata in changed:
            with self.subTest(metadata=metadata.hex()),self.assertRaisesRegex(ValueError,'EXIF_1'):
                decode_request_png(self.from_chunks(plain[:1]+[(b'eXIf',metadata)]+plain[1:]))

    def test_wire_RGB_and_L_masks_use_the_same_metadata_free_subset(self):
        import photo_experimental_transport_v1 as contract
        for array,mode,color in [(self.rgb,'RGB',2),(self.permission.astype(np.uint8)*255,'L',0)]:
            rows=self.png_chunks(png(array))
            for kind,data in [(b'gAMA',struct.pack('>I',45455)),(b'iCCP',b'synthetic\0\0'+zlib.compress(b'profile')),
                              (b'sRGB',b'\0'),(b'tEXt',b'title\0synthetic')]:
                with self.subTest(mode=mode,kind=kind),self.assertRaisesRegex(ValueError,'noncanonical_metadata'):
                    contract.verify_wire_png(self.from_chunks(rows[:1]+[(kind,data)]+rows[1:]),array,mode,color,1)

    def test_masks_are_opaque_L_binary_and_hash_exact_decoded_bool(self):
        wire=self.validate().response('test',1)
        for key in ['accepted_permission_mask','rejected_permission_mask']:
            record=wire[key];raw=base64.b64decode(record['image_base64'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),record['png_sha256'])
            self.assertEqual(raw[25],0)
            with Image.open(io.BytesIO(raw)) as mask:
                self.assertEqual(mask.mode,'L');self.assertEqual(mask.getexif()[274],1)
                pixels=np.asarray(mask);self.assertTrue(set(np.unique(pixels)).issubset({0,255}))
            self.assertEqual(sha(pixels>0),record['boolean_pixel_sha256'])


if __name__=='__main__':unittest.main()
