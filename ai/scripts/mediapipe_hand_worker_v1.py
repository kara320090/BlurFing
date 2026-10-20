"""Isolated official MediaPipe hand observations; no pad masks or renderer."""
import hashlib,json,platform,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from photo_resize_safety_v1 import validate_resize

VERSION='mediapipe_hand_worker_v1'
MODEL_SHA256='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
MEDIAPIPE_VERSION='1.1.1'
CONFIGURATION=dict(running_mode='IMAGE',delegate='CPU',num_hands=2,
    min_hand_detection_confidence=.5,min_hand_presence_confidence=.5,min_tracking_confidence=.5)


def digest(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>128*1024**2:raise ValueError('hand_asset_contract')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_hash(rgb):return hashlib.sha256(rgb.tobytes()).hexdigest()


def decode(source):
    with Image.open(source) as image:
        validate_resize(image.height,image.width,1.)
        orientation=image.getexif().get(274,1)
        if image.mode not in ['RGB','L'] or type(orientation) is not int or orientation not in range(1,9):
            raise ValueError('hand_RGB_L_EXIF_source_contract')
        encoded=np.asarray(image.convert('RGB')).copy()
        upright=encoded.copy() if orientation==1 else np.asarray(ImageOps.exif_transpose(image).convert('RGB')).copy()
    return encoded,upright,orientation


def create_detector(model):
    import importlib.metadata
    import mediapipe as mp
    version=importlib.metadata.version('mediapipe')
    if version!=MEDIAPIPE_VERSION:raise ValueError('hand_mediapipe_version_not_pinned')
    options=mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model),delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,num_hands=CONFIGURATION['num_hands'],
        min_hand_detection_confidence=.5,min_hand_presence_confidence=.5,min_tracking_confidence=.5)
    return mp.tasks.vision.HandLandmarker.create_from_options(options)


def _detect(upright,model,detector=None):
    import importlib.metadata
    import mediapipe as mp
    version=importlib.metadata.version('mediapipe')
    if version!=MEDIAPIPE_VERSION:raise ValueError('hand_mediapipe_version_not_pinned')
    if detector is None:
        with create_detector(model) as current:
            result=current.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=upright))
    else:
        result=detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=upright))
    hands=[]
    for index,landmarks in enumerate(result.hand_landmarks):
        points=np.asarray([[p.x,p.y,p.z] for p in landmarks],np.float64)
        if points.shape!=(21,3) or not np.isfinite(points).all():raise ValueError('hand_finite_21_landmarks_required')
        hands.append(dict(normalized_xy=points[:,:2].tolist(),normalized_xyz=points.tolist(),
            handedness=[dict(category_name=c.category_name,score=float(c.score),index=int(c.index)) for c in result.handedness[index]]))
    return hands,dict(mediapipe_version=version,python_version=platform.python_version(),machine=platform.machine(),
                      numpy_version=np.__version__,Pillow_version=importlib.metadata.version('Pillow'))


def run(source,model,output,*,detector=None):
    source,model,output=map(Path,(source,model,output))
    if output.exists():raise FileExistsError('fresh_hand_observation_JSON_required')
    source_sha=digest(source);model_sha=digest(model);code_sha=digest(__file__)
    if model_sha!=MODEL_SHA256:raise ValueError('official_hand_model_SHA256_mismatch')
    encoded,upright,orientation=decode(source)
    hands,runtime=(_detect(upright,model) if detector is None else _detect(upright,model,detector))
    if runtime.get('mediapipe_version')!=MEDIAPIPE_VERSION:raise ValueError('hand_mediapipe_version_not_pinned')
    if not isinstance(hands,list) or len(hands)>CONFIGURATION['num_hands']:raise ValueError('hand_result_count_contract')
    result=dict(version=VERSION,status='observed' if hands else 'no_hand_observed',source_sha256=source_sha,
        source_path=str(source.resolve()),encoded_RGB_sha256=pixel_hash(encoded),upright_RGB_sha256=pixel_hash(upright),
        encoded_shape=list(encoded.shape),upright_shape=list(upright.shape),source_exif_orientation=orientation,
        model_sha256=model_sha,worker_code_sha256=code_sha,runtime=runtime,configuration=dict(CONFIGURATION),
        hand_count=len(hands),hands=hands,GT_used=False,approved_for_protection=False)
    if digest(source)!=source_sha or digest(model)!=model_sha or digest(__file__)!=code_sha:
        raise ValueError('hand_source_model_or_worker_changed')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['input','model','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:result=run(args.input,args.model,args.output)
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__,reason=str(error))));raise SystemExit(1)
    print(json.dumps(result))
