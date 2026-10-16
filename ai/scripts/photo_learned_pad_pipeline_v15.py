"""Explicit boundary association experiment with unchanged V12 final-RGB gate."""
import photo_learned_pad_pipeline_v1 as base
from photo_learned_pad_pipeline_v12 import prepare_scoped_region
from photo_native_owner_context_v1 import restore_contexts
from photo_owner_boundary_repair_v2 import repair_contexts
from photo_component_local_evidence_v1 import connected_partition

VERSION='photo_learned_pad_pipeline_v15_boundary_association_experimental'


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    audits=[]
    def contexts(original,body):
        repaired,audit=repair_contexts(restore_contexts(original,body),body,mask)
        audits.append(audit);return repaired
    returned,report=base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,
        _candidate_builder=connected_partition,_context_adapter=contexts)
    report.update(boundary_association_audit=audits,evidence_permission_component_local=True,
        anatomical_pad_verified=False,prediction_false_positives_possible=True,
        final_native_gate_authoritative=True,working_structure_is_diagnostic=True,
        proposal_seed_scale_or_renderer_retries=0,default_pipeline_enabled=False,
        approved_for_protection=False,privacy_validated=False,complete_photo_protection_verified=False,
        count_semantics='connected permissions after unique-adjacent-owner association; not fingers',
        partition_policy='experimental_unique_adjacent_owner_no_permission_pixel_changes')
    return returned,report
