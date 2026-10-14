"""Frozen holdout runner. Eligibility declarations are not inferred from filenames."""
import argparse,json,hashlib,datetime,os
from pathlib import Path
from PIL import Image
import numpy as np
from protect_fingerprint import protect_image

def validate_manifest(manifest,development_hashes):
    data=json.loads(Path(manifest).read_text());known=json.loads(Path(development_hashes).read_text());denied=set(known['source_sha256']);records=data['samples'];seen=set()
    if data.get('schema_version')!='independent-photo-v1' or not records:raise ValueError('invalid_or_empty_manifest')
    for record in records:
        source=Path(record['source']);sha=hashlib.sha256(source.read_bytes()).hexdigest()
        if sha!=record['source_sha256'] or sha in denied or sha in seen:raise ValueError('hash_mismatch_or_development_overlap')
        if record.get('not_used_for_training_or_tuning') is not True or record.get('independence_confirmed_by_provider') is not True:raise ValueError('independence_not_confirmed')
        datetime.date.fromisoformat(record['capture_date'])
        if not record.get('participant_alias'):raise ValueError('participant_alias_required')
        seen.add(sha)
    if not denied:raise ValueError('nonempty_development_hash_index_required')
    return data

def configuration_snapshot():
    root=Path(__file__).parent
    files=list(root.glob('*.py'))+list((root/'java').glob('*.java'))+list((root.parent/'docs').glob('*runtime*.json'))
    keys=['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL','BLURFING_SOURCEAFIS_HOME','BLURFING_SOURCEAFIS_CONFIG','BLURFING_NBIS_CONFIG','BLURFING_NBIS_LINUX_CONFIG','BLURFING_NBIS_WINDOWS_CONFIG']
    environment={k:os.environ.get(k) for k in keys}
    for value in environment.values():
        if value and Path(value).is_file():files.append(Path(value))
    external=environment['BLURFING_COLFISPOOF_SOURCE']
    if external and Path(external).is_dir():files+=list(Path(external).rglob('*.py'))
    return dict(environment=environment,files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})

def evaluate(manifest,development_hashes,output):
    data=validate_manifest(manifest,development_hashes);output=Path(output)
    if output.exists():raise FileExistsError('fresh_private_output_required')
    output.mkdir(parents=True);rows=[]
    frozen=configuration_snapshot()
    (output/'frozen_code_manifest.json').write_text(json.dumps(frozen,indent=2))
    for i,record in enumerate(data['samples']):
        image,result=protect_image(record['source'],output/f'{i}_first');repeat,other=protect_image(record['source'],output/f'{i}_repeat')
        deterministic=np.array_equal(image,repeat) and [(r.get('quality_status'),r.get('reason'),r.get('mask_pixel_sha256')) for r in result['regions']]==[(r.get('quality_status'),r.get('reason'),r.get('mask_pixel_sha256')) for r in other['regions']]
        metrics=None
        if record.get('ground_truth_folder'):
            folder=Path(record['ground_truth_folder']);identity=json.loads((folder/'source.json').read_text())
            if identity['source_sha256']!=record['source_sha256']:raise ValueError('GT_source_mismatch')
            if identity.get('annotation_status')!='ambiguous_unusable':
                gt=np.asarray(Image.open(folder/'ground_truth_mask.png'));pred=np.asarray(Image.open(output/f'{i}_first'/'fingerprint_mask.png')) if result['input_type']=='photo' else np.zeros(image.shape[:2],np.uint8)
                if gt.dtype!=np.uint8 or gt.shape!=image.shape[:2] or not np.isin(gt,[0,255]).all():raise ValueError('GT_contract_mismatch')
                from evaluate_detector_ground_truth import metrics as pixel_metrics,component_matching
                if gt.any():
                    values=pixel_metrics(pred>0,gt>0);values['dice']=2*values['true_positive_pixels']/max(1,int((pred>0).sum())+int((gt>0).sum()))
                else:
                    if identity.get('annotation_status') not in ['non_target','non-target']:raise ValueError('empty_GT_requires_explicit_non_target_status')
                    values=dict(iou=None,dice=None,precision=None,recall=None,false_positive_pixels=int((pred>0).sum()))
                metrics=dict(pixel_metrics=values,component_matching=component_matching(pred>0,gt>0))
        rows.append(dict(sample_id=record['sample_id'],route=result['input_type'],routing_correct=result['input_type']=='photo',GT_metrics=metrics,status=result['status'],detected=result['fingerprints_detected'],transformed=result['fingerprints_transformed'],rejected=result['fingerprints_rejected'],exterior_preserved=result['exterior_preserved'],deterministic=deterministic,regions=result['regions'],visual_review='pending'))
    if frozen!=configuration_snapshot():raise RuntimeError('configuration_changed_during_evaluation')
    # No GT means no accuracy; catastrophic-FP review remains a separate human requirement.
    report=dict(samples=rows,configuration_frozen=True,accuracy_computed=any(r['GT_metrics'] is not None for r in rows),FINAL_INDEPENDENT_VALIDATION_COMPLETE=False,PROJECT_COMPLETE=False,reason='human_visual_review_of_background_wrist_keyboard_required')
    (output/'holdout_audit.private.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--development-hashes',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from protect_fingerprint import cli_progress_to_stderr
    with cli_progress_to_stderr():r=evaluate(a.manifest,a.development_hashes,a.output)
    print(json.dumps(r))
