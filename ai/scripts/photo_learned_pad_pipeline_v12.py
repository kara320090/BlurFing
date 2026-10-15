"""V11 observations, one unchanged proposal, authoritative actual-native gate."""
import photo_learned_pad_pipeline_v11 as legacy
import photo_learned_pad_pipeline_v10 as v10
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
from photo_native_return_decision_v1 import render
from photo_native_owner_context_v1 import restore_contexts
from photo_component_local_evidence_v1 import connected_partition

VERSION='photo_learned_pad_pipeline_v12_native_return_decision_experimental'


def prepare_scoped_region(*args,**kwargs):
    artifact,geometry,plan,scoped_render=legacy.prepare_scoped_region(*args,**kwargs)
    if artifact is None:return artifact,geometry,plan,scoped_render
    def native_render(axis):
        # Existing V10/V11 closures retain exact source, pitch and scope binding.
        with shared.renderer_binding._LOCK:
            previous=v10.render,legacy.render
            try:
                v10.render=legacy.render=render
                candidate,report=scoped_render(axis)
            finally:v10.render,legacy.render=previous
        report.update(experimental_gate_version=VERSION,final_native_gate_authoritative=True,
            working_structure_is_diagnostic=True,frozen_gate_equivalence=False)
        return candidate,report
    geometry.update(final_native_gate_authoritative=True,working_structure_is_diagnostic=True)
    return artifact,geometry,plan,native_render


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    returned,report=base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=connected_partition,_context_adapter=restore_contexts)
    report.update(evidence_permission_component_local=True,anatomical_pad_verified=False,
        prediction_false_positives_possible=True,feature_scope_changed_from_frozen_seed=True,frozen_gate_equivalence=False,
        orientation_filtered_fallback_enabled=True,final_native_gate_authoritative=True,
        working_structure_is_diagnostic=True,proposal_seed_scale_or_renderer_retries=0,
        default_pipeline_enabled=False,approved_for_protection=False,
        count_semantics='connected permission components within observed owners; not anatomical fingers',
        partition_policy='connected_permission_components_no_pixel_dropping')
    return returned,report
