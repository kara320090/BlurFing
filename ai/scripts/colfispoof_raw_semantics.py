"""Raw upstream DeepLab semantics; no segment() contour/crop postprocessing.

RGB inputs and outputs use encoded-original pixels (EXIF is not applied).
The four rotations and >=2 votes are fixed before GT evaluation. No cleanup.
External source and weights are supplied by callers, never vendored here.
"""
import hashlib
import importlib.util
import os
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

MODEL_SHA256 = 'f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f'
FINGERTIP_CLASS = 2
ROTATIONS_CW = (0, 90, 180, 270)


def resolve_preprocessing(external_source):
    """Accept the upstream checkout or its preprocessing directory.

    Both forms resolve to the same external loader; never search alternate
    implementations or change graph/preprocessing semantics.
    """
    source = Path(external_source)
    if (source / 'Segmentation' / 'DeepLabModel.py').is_file():
        return source
    preprocessing = source / 'pre-processing'
    if (preprocessing / 'Segmentation' / 'DeepLabModel.py').is_file():
        return preprocessing
    raise FileNotFoundError('COLFISPOOF Segmentation/DeepLabModel.py missing')


def prepare(rgb, size=1024):
    """Official crop_to_size resize/black-padding geometry, without rotation."""
    if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8 or min(rgb.shape[:2])<1:raise ValueError('uint8_RGB_required')
    if isinstance(size,(bool,np.bool_)) or not isinstance(size,(int,np.integer)) or size<1:raise ValueError('positive_integer_preprocessing_size_required')
    h,w=rgb.shape[:2]
    if w>=h:
        nw=size;nh=round(size/w*h);left=0;top=round((size-nh)/2)
    else:
        nh=size;nw=round(size/h*w);top=0;left=round((size-nw)/2)
    if min(nh,nw)<1:raise ValueError('unsupported_preprocessing_aspect_ratio')
    # Match upstream's positional call exactly: the third argument is dst,
    # not interpolation. OpenCV therefore actually uses default INTER_LINEAR.
    scaled=cv2.resize(rgb,(nw,nh),cv2.INTER_AREA)
    padded=cv2.copyMakeBorder(scaled,top,top,left,left,cv2.BORDER_CONSTANT,value=(0,0,0))
    return padded,dict(native_width=w,native_height=h,padded_width=padded.shape[1],padded_height=padded.shape[0],scaled_width=nw,scaled_height=nh,left=left,top=top)


def restore(labels, geometry, quarter_turns):
    """Undo model resize, exact recorded padding/resize, then CW rotation."""
    g=geometry
    mask=cv2.resize((labels==FINGERTIP_CLASS).astype(np.uint8),(g['padded_width'],g['padded_height']),interpolation=cv2.INTER_NEAREST)
    mask=mask[g['top']:g['top']+g['scaled_height'],g['left']:g['left']+g['scaled_width']]
    if mask.shape!=(g['scaled_height'],g['scaled_width']):raise ValueError('padding_inverse_shape_mismatch')
    mask=cv2.resize(mask,(g['native_width'],g['native_height']),interpolation=cv2.INTER_NEAREST)
    return np.rot90(mask,quarter_turns).copy().astype(bool)


def vote_masks(masks, minimum_votes=2):
    if len(masks)!=4 or any(m.shape!=masks[0].shape for m in masks):raise ValueError('four_equal_shape_masks_required')
    if minimum_votes not in (1,2,3,4):raise ValueError('invalid_vote_threshold')
    return np.sum(np.stack(masks).astype(np.uint8),axis=0)>=minimum_votes


class RawDeepLabRuntime:
    def __init__(self, external_preprocessing, model, threads=8, *, device='cpu', dll_directories=()):
        if device not in ('cpu','cuda') or type(threads) is not int or not 1<=threads<=32:
            raise ValueError('explicit_semantic_device_and_thread_contract')
        if (not isinstance(dll_directories,(tuple,list)) or
                any(not isinstance(p,str) or not Path(p).is_absolute() or not Path(p).is_dir() for p in dll_directories)):
            raise ValueError('semantic_DLL_directories_contract')
        if dll_directories and (device!='cuda' or os.name!='nt'):
            raise ValueError('semantic_DLL_directories_require_Windows_CUDA')
        self._dll_handles=[];self._previous_path=None;self.device=device
        model=Path(model)
        if hashlib.sha256(model.read_bytes()).hexdigest()!=MODEL_SHA256:raise ValueError('model_SHA256_mismatch')
        try:
            if dll_directories:
                self._previous_path=os.environ.get('PATH','')
                os.environ['PATH']=os.pathsep.join(list(dll_directories)+[self._previous_path])
                for directory in dll_directories:self._dll_handles.append(os.add_dll_directory(directory))
            import tensorflow as tf
            tf.config.threading.set_intra_op_parallelism_threads(threads)
            tf.config.threading.set_inter_op_parallelism_threads(1)
            if device=='cpu':
                tf.config.set_visible_devices([], 'GPU')
            else:
                tf.config.experimental.enable_tensor_float_32_execution(False)
                devices=tf.config.list_physical_devices('GPU')
                if not devices:raise ValueError('configured_CUDA_device_unavailable')
                tf.config.set_visible_devices(devices[:1],'GPU')
                tf.config.experimental.set_memory_growth(devices[0],True)
            path=resolve_preprocessing(external_preprocessing)/'Segmentation/DeepLabModel.py'
            spec=importlib.util.spec_from_file_location('blurfing_external_deeplab',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.model=module.DeepLabModel(str(model));self.framework_version=tf.__version__;self.source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        except BaseException:
            self._release_dlls();raise

    def predict(self, rgb):
        if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8:raise ValueError('uint8_RGB_required')
        start=time.perf_counter();masks=[];records=[];prep_time=0.;infer_time=0.;inverse_time=0.
        for k,angle in enumerate(ROTATIONS_CW):
            tick=time.perf_counter();rot=np.rot90(rgb,-k).copy();padded,g=prepare(rot);prep_time+=time.perf_counter()-tick
            tick=time.perf_counter();resized,labels=self.model.run(Image.fromarray(padded));duration=time.perf_counter()-tick;infer_time+=duration
            if labels.shape!=(resized.height,resized.width):raise ValueError('model_label_shape_mismatch')
            tick=time.perf_counter();mask=restore(labels,g,k);inverse_time+=time.perf_counter()-tick
            if mask.shape!=rgb.shape[:2]:raise ValueError('native_mask_shape_mismatch')
            ids,counts=np.unique(labels,return_counts=True)
            records.append(dict(rotation_cw=angle,geometry=g,model_width=resized.width,model_height=resized.height,label_counts={str(int(i)):int(c) for i,c in zip(ids,counts)},inference_seconds=duration))
            masks.append(mask)
        tick=time.perf_counter();consensus=vote_masks(masks);vote_time=time.perf_counter()-tick
        return dict(mask=consensus,rotation_masks=masks,rotations=records,timing=dict(preprocessing=prep_time,one_rotation_inference=infer_time/4,four_rotation_inference=infer_time,inverse_mapping=inverse_time,consensus=vote_time,total=time.perf_counter()-start),fingertip_class=FINGERTIP_CLASS,minimum_votes=2,cleanup='none',coordinate_system='encoded_original_pixels')

    def close(self):
        try:self.model.sess.close()
        finally:self._release_dlls()

    def _release_dlls(self):
        for handle in self._dll_handles:handle.close()
        self._dll_handles=[]
        if self._previous_path is not None:
            os.environ['PATH']=self._previous_path;self._previous_path=None
