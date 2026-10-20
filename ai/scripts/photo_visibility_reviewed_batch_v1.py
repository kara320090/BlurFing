"""Reuse one validated human review project for an explicit reviewed batch."""
import json
from pathlib import Path
import sys
import hashlib
from pad_refinement_data_contract_v2 import checked_bytes
from photo_visibility_annotation_v1 import Project
from photo_visibility_reviewed_apply_v1 import run
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged


def run_batch(roster, state, output, *, source_ids=None, seed=None, appearance='v19'):
    if appearance not in ('v19','silhouette_v21','material_v22','junction_v23'):raise ValueError('reviewed_appearance_not_supported')
    output=Path(output)
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_reviewed_batch_required')
    if not (Path(state)/'project.json').is_file():raise ValueError('existing_completed_review_required')
    snapshot=capture_runtime_sources();project=Project(roster,state)
    ids=list(project.sources) if source_ids is None else source_ids
    if (not isinstance(ids,list) or not ids or any(not isinstance(s,str) or s not in project.sources for s in ids)
            or len(ids)!=len(set(ids))):
        raise ValueError('unique_known_source_ids_required')
    # Validate all requested review decisions before publishing any batch output.
    reviews={}
    for sid in ids:
        record=project.current(sid)
        if record.get('status')!='reviewed' or record.get('human_GT') is not True or record.get('attestation') is not True:
            raise ValueError('completed_human_review_required')
        project.validated_groups(sid,record['groups'],True)
        reviews[sid]=record
    output.mkdir(parents=True,exist_ok=False);marker=output/'INCOMPLETE.txt'
    marker.write_text('Batch incomplete: do not treat partial outputs as a complete run.\n',encoding='utf-8')
    rows=[]
    for index,sid in enumerate(ids,1):
        if project.current(sid)!=reviews[sid]:raise ValueError('human_review_changed_during_batch')
        report=run(roster,state,sid,output/sid,seed=seed,project=project,appearance=appearance)
        rows.append(dict(source_id=sid,status=report['status'],applied_regions=report['applied_region_count'],
                         selected_regions=report['selected_region_count'],review_required=report['review_required_count'],
                         output_RGB_sha256=report['output_RGB_sha256']))
        print(json.dumps(dict(completed=index,total=len(ids),source_id=sid,applied=report['applied_region_count'])),file=sys.stderr,flush=True)
    if hashlib.sha256(Path(roster).read_bytes()).hexdigest()!=project.header['roster_sha256']:
        raise ValueError('review_roster_changed_during_batch')
    for sid in ids:
        if project.current(sid)!=reviews[sid]:raise ValueError('human_review_changed_during_batch')
        for kind in ('source','mask'):
            checked_bytes(project.sources[sid][kind+'_path'],project.sources[sid][kind+'_sha256'])
    result=dict(version='human_reviewed_batch_v1',status='completed_reviewed_synthetic_batch',sources=len(rows),rows=rows,appearance=appearance,
                inputs_revalidated_at_completion=True,review_revisions={sid:r['revision'] for sid,r in reviews.items()},
                applied_regions=sum(r['applied_regions'] for r in rows),selected_regions=sum(r['selected_regions'] for r in rows),
                review_required=sum(r['review_required'] for r in rows),independent_validation=False,privacy_validated=False,
                automatic_visibility_approved=False,runtime_source_snapshot=assert_runtime_sources_unchanged(snapshot))
    with (output/'batch.private.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    marker.unlink()
    return result


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    p=JSONArgumentParser(description=__doc__)
    for name in ('roster','state','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-id',action='append');p.add_argument('--seed',type=int)
    p.add_argument('--appearance',choices=('v19','silhouette_v21','material_v22','junction_v23'),default='v19');a=p.parse_args()
    try:
        with cli_progress_to_stderr():result=run_batch(a.roster,a.state,a.output,source_ids=a.source_id,seed=a.seed,appearance=a.appearance)
        print(json.dumps(dict(status=result['status'],sources=result['sources'],applied_regions=result['applied_regions'],
                              review_required=result['review_required'],output=str(a.output.resolve()))))
    except Exception as e:
        print(json.dumps(dict(status='error',reason=str(e),error=type(e).__name__)))
        raise SystemExit(1)
