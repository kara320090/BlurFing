"""Passive profiling of frozen seed/estimator calls, private arrays by default.

No function rebinding, replacement ROI or gate changes. This thread's profiler
is restored on exit. Internal measurement ROI is not anatomical/GT support.
"""
import copy,hashlib,sys
from pathlib import Path
import cv2,numpy as np
import protect_visible_pad_checked_v2 as seed_module
import contactless_ridge_pitch as estimator_module
from photo_resize_safety_v1 import validate_resize

VERSION='photo_seed_pitch_support_trace_v1'


def pixel_sha(array):return hashlib.sha256(array.tobytes()).hexdigest()


def seed_inside_working_pad(image,box,mask):
    """Unknown for invalid/unsupported geometry; empty slices cannot prove support."""
    if (not isinstance(image,np.ndarray) or image.ndim!=3 or len(box)!=4 or
            any(not isinstance(v,(int,np.integer)) or isinstance(v,(bool,np.bool_)) for v in box)):
        return None
    a,b,c,d=box;h,w=image.shape[:2]
    if not (0<=a<c<=w and 0<=b<d<=h):return None
    if not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=(h,w):return None
    return bool(mask[b:d,a:c].all())


def profile_roi_weights(roi,mx,my):
    if (not isinstance(roi,np.ndarray) or roi.dtype!=np.bool_ or roi.ndim!=2 or min(roi.shape)<1 or
            not isinstance(mx,np.ndarray) or not isinstance(my,np.ndarray) or mx.dtype!=np.float32 or
            my.dtype!=np.float32 or mx.ndim!=2 or mx.shape!=my.shape or min(mx.shape)<1):
        raise ValueError('profile_roi_map_contract_mismatch')
    validate_resize(*roi.shape,1.);validate_resize(*mx.shape,1.,channels=1,itemsize=4)
    if not np.isfinite(mx).all() or not np.isfinite(my).all():raise ValueError('profile_roi_map_nonfinite')
    weights=cv2.remap(roi.astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    nearest=cv2.remap(roi.astype(np.uint8),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_REFLECT_101)
    return dict(nearest_coverage=float(nearest.mean()),mean_supported_bilinear_weight=float(weights.mean()),
        samples_with_unsupported_neighbors=int((weights<1.).sum()),sample_count=int(weights.size),
        minimum_supported_bilinear_weight=float(weights.min()),
        maximum_unsupported_bilinear_weight=float((1.-weights).max()),
        reference_mask='internal prepare_fingerprint ROI, not original pad/body or anatomical GT',
        interpolation='actual captured cv2.remap maps; INTER_LINEAR + BORDER_REFLECT_101')


def frozen_profile(gray,mx,my):
    sampled=cv2.remap(gray.astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).mean(0)
    axis=np.arange(len(sampled));sampled-=np.polyval(np.polyfit(axis,sampled,1),axis)
    return sampled


def fixed_map_controls(gray,roi,mx,my):
    """Direct profile dependency only; frozen orientation/maps/ROI stay fixed."""
    baseline=frozen_profile(gray,mx,my);rows=[]
    for value in [0,128,255]:
        derived=gray.copy();derived[~roi]=value
        assert np.array_equal(derived[roi],gray[roi])
        change=frozen_profile(derived,mx,my)-baseline
        rows.append(dict(outside_internal_ROI_fill=value,max_profile_change=float(np.max(np.abs(change))),
            RMS_profile_change=float(np.sqrt(np.mean(change.astype(float)**2))),inside_ROI_pixels_identical=True))
    return rows


class SeedPitchTrace:
    def __init__(self):
        self.seeds=[];self.estimates=[];self.errors=[];self._seeds={};self._estimates={}
        self._seed_code=seed_module.observed_seed_pitch.__code__
        self._estimator_code=estimator_module.estimate_ridge_pitch.__code__

    def __enter__(self):
        if sys.getprofile() is not None:raise RuntimeError('existing_profiler_active')
        self._previous=sys.getprofile();sys.setprofile(self._profile);return self

    def __exit__(self,*exception):
        sys.setprofile(self._previous)
        return False

    def _profile(self,frame,event,arg):
        try:self._event(frame,event,arg)
        except Exception as error:
            # A diagnostic error must not alter the running frozen algorithm.
            self.errors.append(dict(event=event,function=frame.f_code.co_name,error=type(error).__name__))

    def _event(self,frame,event,arg):
        key=id(frame);code=frame.f_code
        if code is self._seed_code:
            if event=='call':
                image=frame.f_locals['original'];box=list(frame.f_locals['box']);a,b,c,d=box
                validate_resize(d-b,c-a,1.)
                caller=frame.f_back
                caller_mask=caller.f_locals.get('working_mask')
                inside_pad=seed_inside_working_pad(image,box,caller_mask)
                record=dict(seed_id=len(self.seeds)+1,box_working_xyxy=box,
                    caller=dict(file=Path(caller.f_code.co_filename).name,function=caller.f_code.co_name,line=caller.f_lineno),
                    input_working_image_shape=list(image.shape[:2]),seed_fully_inside_caller_working_pad=inside_pad,
                    caller_pad_is_anatomical_GT=False,
                    seed_RGB_pixel_sha256=pixel_sha(image[b:d,a:c]),estimator_ids=[],completed=False)
                self.seeds.append(record);self._seeds[key]=record
            elif event=='return':
                record=self._seeds.pop(key,None)
                if record is not None and isinstance(arg,tuple) and len(arg)==3:
                    pitch,measurement,raw=arg
                    record.update(completed=True,pitch_working=pitch,measurement=copy.deepcopy(measurement),
                        raw512=raw.copy(),raw512_pixel_sha256=pixel_sha(raw),
                        measurement_ROI512=frame.f_locals.get('mask',None))
                    if record['measurement_ROI512'] is not None:record['measurement_ROI512']=record['measurement_ROI512'].copy()
                    self._mark_selected(record)
            return
        if code is not self._estimator_code:return
        if event=='call':
            gray=frame.f_locals['gray'];roi=frame.f_locals['roi'];validate_resize(*gray.shape,1.)
            owner=None;ancestor=frame.f_back
            while ancestor is not None:
                if id(ancestor) in self._seeds:owner=self._seeds[id(ancestor)];break
                ancestor=ancestor.f_back
            caller=frame.f_back;label=caller.f_locals.get('label')
            if label is None and caller.f_code.co_name=='two_scale_measurement':label='Gaussian'+str(caller.f_locals['sigma'])
            row=dict(estimator_id=len(self.estimates)+1,seed_id=owner['seed_id'] if owner else None,
                preprocessing=label or 'isolated_estimator_call',frame=gray.copy(),ROI=roi.copy(),
                frame_pixel_sha256=pixel_sha(gray),ROI_pixel_sha256=pixel_sha(roi),profiles=[])
            self.estimates.append(row);self._estimates[key]=row
            if owner is not None:owner['estimator_ids'].append(row['estimator_id'])
        elif event=='c_call' and arg is cv2.remap:
            row=self._estimates.get(key)
            if row is not None:
                mx,my=frame.f_locals['mx'].copy(),frame.f_locals['my'].copy()
                row['profiles'].append(dict(x=int(frame.f_locals['cx']),y=int(frame.f_locals['cy']),
                    mx=mx,my=my,support=profile_roi_weights(row['ROI'],mx,my)))
        elif event=='return':
            row=self._estimates.pop(key,None)
            if row is not None and isinstance(arg,dict):
                row['measurement']=copy.deepcopy(arg)
                periodic={(m['x'],m['y']):m for m in arg.get('measurements',[])}
                for profile in row['profiles']:
                    profile['periodic_measurement']=periodic.get((profile['x'],profile['y']))
                    profile['participates_in_selected_estimation']=False

    def _mark_selected(self,seed):
        selected=seed['measurement'].get('selected')
        if seed['pitch_working'] is None:return
        for index in seed['estimator_ids']:
            estimate=self.estimates[index-1];label=estimate['preprocessing']
            chosen=(label==selected or selected=='TwoScaleGaussian1.2_1.8' and label.startswith('Gaussian'))
            if not chosen:continue
            result=estimate['measurement'];values=np.array([m['pitch'] for m in result.get('measurements',[])])
            median=float(np.median(values)) if len(values) else None
            for profile in estimate['profiles']:
                m=profile['periodic_measurement']
                if m is None:continue
                if selected!='TwoScaleGaussian1.2_1.8' and result.get('status')=='estimated':
                    contributes=abs(m['pitch']-median)<=max(2.,3*result['pitch_mad'])
                else:contributes=m['correlation']>=.6 and m['coherence']>=.65 and m['profile_contrast']>=2
                profile['participates_in_selected_estimation']=bool(contributes)

    def metadata(self):
        estimates=[]
        for row in self.estimates:
            profiles=[{k:v for k,v in p.items() if k not in ['mx','my']} for p in row['profiles']]
            estimates.append({k:v for k,v in row.items() if k not in ['frame','ROI','profiles']}|dict(profiles=profiles))
        seeds=[{k:v for k,v in s.items() if k not in ['raw512','measurement_ROI512']} for s in self.seeds]
        return dict(schema_version=VERSION,seeds=seeds,estimates=estimates,errors=self.errors,
            instrumentation='thread-local passive Python/C profile events; no function/global rebinding',
            original_algorithm_return_value_replaced=False,internal_ROI_is_anatomical_GT=False,
            protection_proven=False)
