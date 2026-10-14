"""Body-owner groups + observed native width + same-body observation seeds."""
import photo_learned_pad_pipeline_v1 as base
from photo_learned_pad_pipeline_v3 import prepare_scoped_region as prepare_body_scale
from photo_owner_partition_v1 import partition
from photo_body_observation_seed_v1 import prepare_region
from photo_returned_rgb_structure_v1 import returned_structure_check
from photo_native_owner_context_v1 import restore_contexts

VERSION='photo_learned_pad_pipeline_v4_body_owner_observation_experimental'


def prepare_scoped_region(*args):return prepare_body_scale(*args,_preparer=prepare_region,_version=VERSION,_postprocess=returned_structure_check)


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    return base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=partition,_context_adapter=restore_contexts)


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)


if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detect-only',action='store_true');a=p.parse_args()
    protect_bundle(a.model,a.inputs,a.output,a.detect_only)
