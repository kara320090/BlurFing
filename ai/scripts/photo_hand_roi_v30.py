"""Native-resolution whole-hand ROI optimization, with explicit changed context.

The learned semantic/V6/pose/boundary/renderer pipeline still runs inside the
crop. No landmark rectangle alone authorizes synthesis. Masks and RGB are
translated back to the original frame and validated by the usual transport.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import numpy as np
from PIL import Image


def hand_box(hands,width,height):
    if not isinstance(hands,list) or not 1<=len(hands)<=2:return None
    points=[]
    for hand in hands:
        values=np.asarray(hand.get('normalized_xy'))
        if values.shape!=(21,2) or values.dtype.kind not in 'iuf' or not np.isfinite(values).all():
            raise ValueError('ROI_hand_observation_contract')
        points.append(values*np.array([width,height]))
    points=np.concatenate(points)
    left,top=points.min(0);right,bottom=points.max(0)
    margin=max(32.,.12*max(right-left,bottom-top))
    x0=max(0,math.floor(left-margin));y0=max(0,math.floor(top-margin))
    x1=min(width,math.ceil(right+margin));y1=min(height,math.ceil(bottom+margin))
    if x1-x0<32 or y1-y0<32 or (x1-x0)*(y1-y0)>=width*height*.65:return None
    return x0,y0,x1,y1


def candidate_labels(folder):
    from photo_partial_pose_v25 import partition_candidates
    from scipy import ndimage
    if not (folder/'candidate_mask.png').exists():
        report=json.loads((folder/'result.private.json').read_text('utf-8'))
        if report.get('regions')!=[]:raise ValueError('ROI_missing_candidate_artifact')
        with Image.open(folder/'returned.png') as image:return np.zeros((image.height,image.width),np.uint16)
    with Image.open(folder/'candidate_mask.png') as image:mask=np.asarray(image)>0
    binding=json.loads((folder/'proposal/proposal.private.json').read_text('utf-8'))
    if binding.get('partial_pose') is not None:
        with Image.open(folder/'proposal/pose_owners.png') as image:owners=np.array(image)
        labels,_=partition_candidates(mask,owners,binding['partial_pose']['selected_labels'])
    else:labels,_=ndimage.label(mask,np.ones((3,3),np.uint8))
    return labels.astype(np.uint16)


def run(source,output,*,photo_model,consumed_registry,request_id,development_replay=False,execution_context=None):
    from export_photo_permissions_v1 import _request
    import photo_automatic_v23 as automatic
    from protection_runtime_sources_v1 import capture_runtime_sources,assert_runtime_sources_unchanged
    from fingerprint_input_router import route_input
    import pad_refinement_tiles_v3 as tiles
    from photo_consumed_replay_v1 import development_replay as replay_scope
    import mediapipe_hand_worker_v1 as hand
    from photo_pose_native_pipeline_v1 import verify_worker
    source,output=Path(source),Path(output)
    rgb,source_sha=_request(source)
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_ROI_output_required')
    if route_input(rgb)['input_type']!='PHOTO':
        return automatic.run(source,output,photo_model=photo_model,consumed_registry=consumed_registry,
            request_id=request_id,development_replay=development_replay,execution_context=execution_context)
    registry,_=tiles.json_snapshot(consumed_registry);tiles.validate_registry(registry)
    identity=tiles.image_identity(source)
    with replay_scope(registry,[identity],enabled=development_replay):tiles.exclude_consumed(identity,registry)
    snapshot=capture_runtime_sources();started=time.perf_counter()
    output.mkdir(parents=True);(output/'INCOMPLETE.txt').write_text('ROI photo not completed.',encoding='utf-8')
    observation=output/'whole-hand.private.json'
    if execution_context is not None:
        with execution_context.hand_job(source.resolve(),observation.resolve()) as job:job.finish()
    else:
        subprocess.run([os.environ['BLURFING_HAND_PYTHON'],str(Path(hand.__file__)),'--input',str(source),
            '--model',os.environ['BLURFING_HAND_MODEL'],'--output',str(observation)],check=True,timeout=60,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    record=json.loads(observation.read_text('utf-8'))
    binding=dict(source_path=str(source),source_sha256=source_sha,source_RGB_sha256=automatic.pixels(rgb),source_exif_orientation=1)
    verify_worker(binding,rgb,record)
    box=hand_box(record['hands'],rgb.shape[1],rgb.shape[0])
    if box is None:
        # Explicit full-frame path when a bounded whole-hand crop is unavailable.
        target=automatic.run(source,output/'full-frame',photo_model=photo_model,consumed_registry=consumed_registry,
            request_id=request_id,development_replay=development_replay,execution_context=execution_context)
        for name in ('result.transport.json','result.private.json','returned.png','applied_mask.png','candidate_mask.png'):
            path=target.parent/name
            if path.exists():(output/name).write_bytes(path.read_bytes())
        (output/'roi.private.json').write_text(json.dumps(dict(used=False,reason='no_bounded_whole_hand_ROI')))
        assert_runtime_sources_unchanged(snapshot);(output/'INCOMPLETE.txt').unlink()
        return output/'result.transport.json'
    x0,y0,x1,y1=box
    crop=output/'hand-input.png';Image.fromarray(rgb[y0:y1,x0:x1]).save(crop)
    local=output/'hand-result'
    result=automatic.run(crop,local,photo_model=photo_model,consumed_registry=consumed_registry,request_id=request_id,
        development_replay=development_replay,execution_context=execution_context,array_result=True)
    if not isinstance(result,automatic.AutomaticArrays) or result.source_sha256!=hashlib.sha256(crop.read_bytes()).hexdigest():
        raise ValueError('ROI_array_result_binding')
    generated,small_applied,small_labels=result.returned,result.applied,result.labels
    labels=np.zeros(rgb.shape[:2],np.uint16);labels[y0:y1,x0:x1]=small_labels
    applied=np.zeros(rgb.shape[:2],bool);applied[y0:y1,x0:x1]=small_applied
    returned=rgb.copy();view=returned[y0:y1,x0:x1];view[small_applied]=generated[small_applied]
    report=result.report
    for evidence in report.get('evidence',[]):
        if 'source_bbox_xyxy' in evidence:
            a,b,c,d=evidence['source_bbox_xyxy'];evidence['source_bbox_xyxy']=[a+x0,b+y0,c+x0,d+y0]
    report.update(version='native_whole_hand_ROI_v30',ROI_optimization=dict(used=True,bbox_xyxy=list(box),
        original_shape=list(rgb.shape[:2]),processing_shape=[y1-y0,x1-x0],resized=False,
        learned_detection_context_changed=True,whole_photo_coverage_verified=False),
        original_RGB_sha256=automatic.pixels(rgb),output_RGB_sha256=automatic.pixels(returned),
        original_labels_sha256=automatic.pixels(labels),
        outside_applied_RGB_preserved=True)
    value=automatic.transport(rgb,returned,labels,applied,report,source_sha,request_id,int((time.perf_counter()-started)*1000))
    Image.fromarray(returned).save(output/'returned.png');Image.fromarray(applied.astype(np.uint8)*255).save(output/'applied_mask.png')
    Image.fromarray((labels>0).astype(np.uint8)*255).save(output/'candidate_mask.png')
    report['runtime_sources']=assert_runtime_sources_unchanged(snapshot)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=source_sha:raise ValueError('ROI_source_changed')
    (output/'result.private.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (output/'result.transport.json').write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')
    (output/'INCOMPLETE.txt').unlink()
    return output/'result.transport.json'
