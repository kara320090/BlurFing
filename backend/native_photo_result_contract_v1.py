"""Optional experimental result validation, independent of the v1 blur API.

Arrays
are encoded-original coordinates; any public v2 endpoint must require EXIF 1.
No matcher score, detector accuracy or privacy protection claim is produced.

The HTTP client must normalize source colors into sRGB before encoding. An
untagged RGB raster cannot prove its own color provenance. This verifier only
accepts the canonical metadata-free chunk subset; removing an ICC profile
without converting its samples does not perform color normalization.
"""
from dataclasses import dataclass
import base64
import hashlib
import io
import re
import struct
import zlib
import numpy as np
from PIL import Image

ENGINES={'native_v12':'photo_native_v12_experimental','distal_v13':'photo_distal_v13_geometry_experimental',
         'pose_v14':'photo_pose_v14_geometry_experimental'}
ENTRYPOINTS={'native_v12':'single_photo_whole_pad_context_native_v1_experimental','distal_v13':'photo_distal_native_v13_experimental',
             'pose_v14':'single_photo_pose_native_v14_experimental'}
MAX_PIXELS=20_000_000
MAX_COMPONENTS=256
MAX_RETURNED_PNG_BYTES=15*1024*1024
MAX_REQUEST_PNG_BYTES=15*1024*1024
PNG_BLOCK_BYTES=64*1024
MAX_PNG_CHUNKS=4096
CANONICAL_PNG_CHUNKS=frozenset((b'IHDR',b'eXIf',b'IDAT',b'IEND'))
REQUEST_ID_PATTERN=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:\-]{0,199}\Z')


def require_request_id(value):
    if not isinstance(value,str) or REQUEST_ID_PATTERN.fullmatch(value) is None:raise ValueError('invalid_request_id')


def _exif_one(data):
    """Only a minimal TIFF carrying orientation 1; no other tags or pointers."""
    if len(data)!=26 or bytes(data[:2]) not in (b'II',b'MM'):raise ValueError('request_PNG_minimal_EXIF_1_required')
    order='little' if bytes(data[:2])==b'II' else 'big'
    def number(at,size):
        if at<0 or at+size>len(data):raise ValueError('request_PNG_EXIF_1_required')
        return int.from_bytes(data[at:at+size],order)
    if number(2,2)!=42:raise ValueError('request_PNG_EXIF_1_required')
    offset=number(4,4)
    if offset!=8:raise ValueError('request_PNG_minimal_EXIF_1_required')
    count=number(offset,2)
    if count!=1:raise ValueError('request_PNG_minimal_EXIF_1_required')
    orientations=0
    for index in range(count):
        at=offset+2+12*index
        if number(at,2)==274:
            orientations+=1
            if orientations!=1 or number(at+2,2)!=3 or number(at+4,4)!=1 or number(at+8,2)!=1:
                raise ValueError('request_PNG_EXIF_1_required')
    if orientations!=1 or number(20,2)!=0 or number(22,4)!=0:raise ValueError('request_PNG_minimal_EXIF_1_required')


def _exact_zlib_rows(content,idats,row_bytes,height):
    """Count filtered scanline bytes with constant-size input/output buffers.

    Never use unbounded decompress/flush: an advertised tiny raster may carry a
    much larger deflate stream. All input slices and output allocations are at
    most PNG_BLOCK_BYTES, irrespective of the source dimensions or compression.
    """
    expected=row_bytes*height;decoder=zlib.decompressobj();total=0;view=memoryview(content)
    def counted(out):
        nonlocal total
        if total+len(out)>expected:raise ValueError('request_PNG_scanline_size')
        first=(-total)%row_bytes
        if any(out[index]>4 for index in range(first,len(out),row_bytes)):raise ValueError('request_PNG_scanline_filter')
        total+=len(out)
    def consume(pending):
        nonlocal total
        while pending:
            if decoder.eof:raise ValueError('request_PNG_trailing_zlib_data')
            out=decoder.decompress(pending,PNG_BLOCK_BYTES)
            counted(out)
            if decoder.unused_data:raise ValueError('request_PNG_trailing_zlib_data')
            tail=decoder.unconsumed_tail
            if len(tail)==len(pending) and not out:raise ValueError('request_PNG_zlib_no_progress')
            pending=tail
    try:
        for start,end in idats:
            for offset in range(start,end,PNG_BLOCK_BYTES):consume(view[offset:min(end,offset+PNG_BLOCK_BYTES)])
        # Drain only bounded output; flush(length) does not impose an output cap.
        while not decoder.eof:
            out=decoder.decompress(b'',PNG_BLOCK_BYTES);counted(out)
            if decoder.unused_data or decoder.unconsumed_tail:raise ValueError('request_PNG_trailing_zlib_data')
            if not out:break
    except zlib.error as error:raise ValueError('request_PNG_invalid_zlib') from error
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or total!=expected:
        raise ValueError('request_PNG_scanline_size_or_incomplete_zlib')


def _png_preflight(content,color_type,*,require_exif_one=True):
    if not isinstance(content,bytes) or not 0<len(content)<=MAX_REQUEST_PNG_BYTES:raise ValueError('request_PNG_byte_limit')
    if content[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('request_PNG_required')
    cursor=8;first=True;idat=False;idat_ended=False;exif=False;ended=False;count=0;idats=[];view=memoryview(content);noncanonical=False
    while cursor<len(content):
        count+=1
        if count>MAX_PNG_CHUNKS:raise ValueError('request_PNG_chunk_limit')
        if len(content)-cursor<12:raise ValueError('request_PNG_structure')
        length=struct.unpack('>I',content[cursor:cursor+4])[0];kind=content[cursor+4:cursor+8]
        end=cursor+12+length
        if end>len(content):raise ValueError('request_PNG_structure')
        if any(not (65<=byte<=90 or 97<=byte<=122) for byte in kind) or not 65<=kind[2]<=90:
            raise ValueError('request_PNG_chunk_type')
        data=view[cursor+8:cursor+8+length]
        crc=struct.unpack('>I',content[cursor+8+length:end])[0]
        if zlib.crc32(data,zlib.crc32(kind))&0xffffffff!=crc:raise ValueError('request_PNG_CRC')
        if first:
            if kind!=b'IHDR' or length!=13:raise ValueError('request_PNG_IHDR')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if depth!=8 or color!=color_type:raise ValueError('request_opaque_RGB8_PNG_required')
            if not 0<width*height<=MAX_PIXELS or compression or filtering or interlace!=0:raise ValueError('request_PNG_size_or_encoding')
            first=False
        elif kind==b'IHDR':raise ValueError('request_PNG_duplicate_IHDR')
        if kind in (b'tRNS',b'acTL',b'fcTL',b'fdAT'):raise ValueError('request_opaque_single_frame_PNG_required')
        if kind==b'IDAT':
            if idat_ended:raise ValueError('request_PNG_nonconsecutive_IDAT')
            idat=True;idats.append((cursor+8,cursor+8+length))
        elif kind==b'eXIf':
            if idat or exif:raise ValueError('request_PNG_duplicate_or_late_EXIF')
            exif=True
            if require_exif_one:_exif_one(data)
        elif kind not in (b'IHDR',b'IEND'):
            if 65<=kind[0]<=90:raise ValueError('request_PNG_unknown_critical_chunk')
            if kind not in CANONICAL_PNG_CHUNKS:noncanonical=True
            if idat:idat_ended=True
        if kind==b'IEND':
            if length or end!=len(content):raise ValueError('request_PNG_IEND')
            ended=True;break
        cursor=end
    if not ended or not idat:raise ValueError('request_PNG_structure')
    if noncanonical:raise ValueError('request_PNG_noncanonical_metadata_forbidden')
    _exact_zlib_rows(content,idats,width*(3 if color_type==2 else 1)+1,height)
    return width,height


def decode_request_png(content):
    """Opaque 8-bit RGB, single PNG, normalized EXIF 1; no implicit conversion."""
    width,height=_png_preflight(content,2)
    with Image.open(io.BytesIO(content)) as image:
        if image.format!='PNG' or image.mode!='RGB' or image.size!=(width,height) or getattr(image,'n_frames',1)!=1:
            raise ValueError('request_opaque_RGB8_PNG_required')
        require_android_request_orientation(image.getexif().get(274,1))
        image.load();rgb=np.asarray(image).copy()
    return rgb


def sha(array):return hashlib.sha256(array.tobytes()).hexdigest()


def require_android_request_orientation(orientation):
    if type(orientation) is not int or orientation!=1:
        raise ValueError('v2_request_requires_pixels_already_normalized_to_EXIF_1')


def integer(value,name,maximum):
    if type(value) is not int or not 0<=value<=maximum:raise ValueError('invalid_'+name)
    return value


def png(array,orientation=1):
    output=io.BytesIO();exif=Image.Exif();exif[274]=orientation
    Image.fromarray(array).save(output,format='PNG',exif=exif)
    return output.getvalue()


def verify_wire_png(content,array,mode,color_type,orientation):
    """Check our lossless encoder's actual bytes, not Pillow's inferred mode alone."""
    if (content[:8]!=b'\x89PNG\r\n\x1a\n' or len(content)<33 or content[12:16]!=b'IHDR' or
            struct.unpack('>I',content[8:12])[0]!=13 or
            struct.unpack('>IIBBBBB',content[16:29])!=(array.shape[1],array.shape[0],8,color_type,0,0,0)):
        raise ValueError('wire_PNG_encoding_contract')
    _png_preflight(content,color_type,require_exif_one=(orientation==1))
    with Image.open(io.BytesIO(content)) as image:
        if (image.mode!=mode or getattr(image,'n_frames',1)!=1 or image.getexif().get(274,1)!=orientation or
                not np.array_equal(np.asarray(image),array)):
            raise ValueError('wire_lossless_PNG_roundtrip_contract')


def encoded_mask(mask,orientation):
    raster=mask.astype(np.uint8)*255;content=png(raster,orientation)
    verify_wire_png(content,raster,'L',0,orientation)
    if len(content)>MAX_RETURNED_PNG_BYTES:raise ValueError('mask_PNG_exceeds_Android_lossless_limit')
    return dict(encoding='png_uint8_0_255',image_base64=base64.b64encode(content).decode('ascii'),
                png_sha256=hashlib.sha256(content).hexdigest(),boolean_pixel_sha256=sha(mask),pixels=int(mask.sum()))


@dataclass(frozen=True)
class ValidatedExperimentalPhotoResult:
    engine:str
    status:str
    source_sha256:str
    source_RGB_sha256:str
    returned_RGB_sha256:str
    width:int
    height:int
    source_orientation:int
    detected:int
    transformed:int
    rejected:int
    changed_pixels:int
    accepted:dict
    refused:dict
    region_display_bounds:tuple
    returned_png:bytes

    def response(self,request_id,processing_ms):
        require_request_id(request_id)
        integer(processing_ms,'processing_ms',2**63-1)
        warnings=['EXPERIMENTAL_UNAPPROVED','UNDETECTED_FINGERPRINTS_POSSIBLE','COUNTS_ARE_PERMISSION_COMPONENTS_NOT_FINGERS']
        if self.rejected:warnings.append('REJECTED_REGIONS_RETAIN_ORIGINAL_PIXELS')
        if self.engine=='distal_v13':warnings.append('GEOMETRY_BOUNDARIES_REQUIRE_REVIEW_ACCURACY_REGRESSION_OBSERVED')
        if self.engine=='pose_v14':warnings.append('POSE_GEOMETRY_BOUNDARIES_REQUIRE_REVIEW')
        return dict(contract_version='photo-experimental-v2',request_id=request_id,result_kind='experimental',
            method=ENGINES[self.engine],photo_engine=self.engine,status=self.status,
            image_base64=base64.b64encode(self.returned_png).decode('ascii'),mime_type='image/png',
            image_width=self.width,image_height=self.height,source_exif_orientation=self.source_orientation,
            coordinate_system='encoded_original_pixels',source_sha256=self.source_sha256,
            source_RGB_sha256=self.source_RGB_sha256,returned_RGB_sha256=self.returned_RGB_sha256,
            candidate_components=self.detected,transformed_components=self.transformed,rejected_components=self.rejected,
            changed_RGB_pixels=self.changed_pixels,accepted_permission_mask=self.accepted,rejected_permission_mask=self.refused,
            region_display_bounds=list(self.region_display_bounds),bounds_are_not_filled_permission=True,
            processing_ms=processing_ms,warnings=warnings,privacy_validated=False,production_approved=False,
            complete_photo_protection_verified=False,independent_final_test=False,evaluation=None)


def validate_native_result(source_rgb,returned_rgb,permission,labels,report,*,source_sha256,engine,orientation,verified_empty_permission_reason=None):
    """Validate the actual returned arrays against exact hash-bound partitions.

    Caller must read original request bytes and bind source_sha256 to them;
    reconstruct labels with the exact engine partition and source artifacts;
    and verify those artifact hashes before calling. Bounding boxes cannot
    replace labels. This function never re-renders or relaxes a quality gate.
    """
    if engine not in ENGINES:raise ValueError('unsupported_experimental_engine')
    if not isinstance(report,dict):raise ValueError('region_report_contract')
    if report.get('single_photo_entrypoint')!=ENTRYPOINTS[engine]:raise ValueError('selected_engine_binding_mismatch')
    if (type(orientation) is not int or orientation not in range(1,9) or
        not isinstance(source_sha256,str) or re.fullmatch('[0-9a-f]{64}',source_sha256) is None):
        raise ValueError('invalid_source_identity')
    for image in (source_rgb,returned_rgb):
        if not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
            raise ValueError('RGB_uint8_required')
    height,width=source_rgb.shape[:2]
    if not 0<height*width<=MAX_PIXELS or returned_rgb.shape!=source_rgb.shape:raise ValueError('RGB_size_contract')
    if not isinstance(permission,np.ndarray) or permission.dtype!=np.bool_ or permission.shape!=(height,width):
        raise ValueError('native_boolean_permission_required')
    if (not isinstance(labels,np.ndarray) or labels.dtype!=np.uint16 or labels.shape!=permission.shape or
            not np.array_equal(labels>0,permission)):
        raise ValueError('exact_native_partition_required')
    identity=report.get('input_identity',{})
    if not isinstance(identity,dict):raise ValueError('request_source_binding_mismatch')
    if (identity.get('original_source_sha256')!=source_sha256 or identity.get('canonical_RGB_sha256')!=sha(source_rgb) or
            identity.get('source_exif_orientation')!=orientation or report.get('coordinate_system')!='encoded_original_pixels'):
        raise ValueError('request_source_binding_mismatch')
    if report.get('returned_RGB_sha256')!=sha(returned_rgb):raise ValueError('returned_RGB_hash_mismatch')
    empty_verified=(engine=='pose_v14' and not permission.any() and
        isinstance(verified_empty_permission_reason,str) and bool(verified_empty_permission_reason) and
        report.get('reject_reason')==verified_empty_permission_reason and report.get('regions')==[])
    if verified_empty_permission_reason is not None and not empty_verified:raise ValueError('empty_permission_proof_contract')
    if report.get('prediction_pixel_sha256')!=sha(permission):
        if not (empty_verified and 'prediction_pixel_sha256' not in report):raise ValueError('permission_hash_mismatch')
    rows=report.get('regions')
    if not isinstance(rows,list) or len(rows)>MAX_COMPONENTS or any(not isinstance(row,dict) for row in rows):raise ValueError('region_report_contract')
    ids=set(int(x) for x in np.unique(labels) if x)
    if len(ids)!=len(rows) or ids!={r.get('region_id') for r in rows}:raise ValueError('region_partition_identity_mismatch')
    if len({r['region_id'] for r in rows})!=len(rows):raise ValueError('duplicate_region_report')
    changed=np.any(source_rgb!=returned_rgb,axis=2);accepted=np.zeros_like(permission)
    display=[];transformed=0
    for row in rows:
        region_id=integer(row.get('region_id'),'region_id',65535)
        if region_id==0:raise ValueError('zero_region_id')
        native=labels==region_id;pixels=int(native.sum())
        if row.get('mask_pixel_sha256')!=sha(native) or integer(row.get('mask_pixels'),'mask_pixels',MAX_PIXELS)!=pixels:raise ValueError('region_permission_hash_mismatch')
        if row.get('status')=='transformed':
            details=row.get('renderer_details',{})
            if not isinstance(details,dict):raise ValueError('actual_native_gate_evidence_required')
            gates=details.get('regions',[])
            if (not isinstance(gates,list) or len(gates)!=1 or
                    not isinstance(gates[0],dict) or not isinstance(gates[0].get('structure_check'),dict)):
                raise ValueError('actual_native_gate_evidence_required')
            if (details.get('structure_checked_on_actual_native_return') is not True or details.get('final_native_gate_authoritative') is not True or
                    len(gates)!=1 or gates[0].get('structure_check',{}).get('structure_change_passed') is not True or
                    gates[0].get('returned_RGB_structure_check')!=gates[0].get('structure_check')):
                raise ValueError('actual_native_gate_evidence_required')
            if not np.any(changed & native):raise ValueError('transformed_region_without_actual_RGB_change')
            accepted|=native;transformed+=1;reason='TRANSFORMED'
        elif row.get('status')=='rejected':
            if np.any(changed & native):raise ValueError('rejected_region_RGB_changed')
            reason=row.get('quality_status','REJECT_OTHER')
            if not isinstance(reason,str) or re.fullmatch('REJECT_[A-Z0-9_]+',reason) is None:reason='REJECT_OTHER'
        else:raise ValueError('unknown_region_state')
        yy,xx=np.where(native);x0,y0,x1,y1=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1
        display.append(dict(region_id=region_id,status=row['status'],reason_code=reason,mask_pixels=pixels,
            changed_RGB_pixels=int((changed & native).sum()),permission_boolean_sha256=sha(native),
            x=x0/width,y=y0/height,width=(x1-x0)/width,height=(y1-y0)/height,
            bounds_are_not_filled_permission=True))
    if np.any(changed & ~accepted):raise ValueError('RGB_changed_outside_accepted_permission')
    rejected=len(rows)-transformed
    status='success' if transformed and transformed==len(rows) else 'partial_success' if transformed else 'rejected'
    if (report.get('status')!=status or
        integer(report.get('fingerprints_detected'),'detected',MAX_COMPONENTS)!=len(rows) or
        integer(report.get('fingerprints_transformed'),'transformed',MAX_COMPONENTS)!=transformed or
        integer(report.get('fingerprints_rejected'),'rejected',MAX_COMPONENTS)!=rejected or
        integer(report.get('changed_pixels'),'changed_pixels',MAX_PIXELS)!=int(changed.sum())):
        raise ValueError('status_or_counts_mismatch')
    if report.get('approved_for_protection') is not False or report.get('privacy_validated') is not False:
        raise ValueError('experimental_approval_flags_must_be_false')
    for flag in ['production_approved','complete_photo_protection_verified','independent_final_test','independent_validation_complete',
                 'default_pipeline_enabled','PHOTO_DETECTOR_APPROVED','PHOTO_PROTECTION_PRODUCTION_READY']:
        if flag in report and report[flag] is not False:raise ValueError('experimental_approval_flags_must_be_false')
    returned_png=png(returned_rgb,orientation)
    verify_wire_png(returned_png,returned_rgb,'RGB',2,orientation)
    if len(returned_png)>MAX_RETURNED_PNG_BYTES:raise ValueError('returned_PNG_exceeds_Android_lossless_limit')
    return ValidatedExperimentalPhotoResult(engine,status,source_sha256,sha(source_rgb),sha(returned_rgb),width,height,
        orientation,len(rows),transformed,rejected,int(changed.sum()),encoded_mask(accepted,orientation),
        encoded_mask(permission & ~accepted,orientation),tuple(display),returned_png)
