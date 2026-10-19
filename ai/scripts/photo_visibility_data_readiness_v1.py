"""Audit metadata for visibility learning; never train or create human labels.

Checks necessary capture-group/class coverage for train/calibration/test roles.
Passing these checks alone does not establish adequate sample size, person
independence, representative negatives, or independent model performance.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


DEVELOPMENT = 'consumed_training_development'
HISTORICAL = 'consumed_historical_GT7_forbid_training'
LABELS = ('visible','not_observed','uncertain')


def audit(export, roster):
    sources = roster.get('sources',[]); records = export.get('records',[])
    by_id = {r['source_id']:r for r in sources}
    if len(by_id)!=len(sources) or not sources:
        raise ValueError('unique_nonempty_roster_required')
    for key in ('source_sha256','upright_RGB_sha256'):
        identities = [r[key] for r in sources]
        if len(set(identities)) != len(identities):
            raise ValueError('duplicate_source_or_decoded_pixels')
    if len(records)!=len(sources) or {r['source_id'] for r in records}!=set(by_id):
        raise ValueError('one_reviewed_record_per_source_required')
    classes = {label:dict(regions=0,photos=set(),capture_groups=set()) for label in LABELS}
    group_counts = {}; unknown_groups = []; excluded = 0
    for record in records:
        source = by_id[record['source_id']]
        if record.get('human_GT') is not True or record.get('status')!='reviewed':
            raise ValueError('reviewed_human_labels_required')
        for key in ('source_sha256','mask_sha256','upright_RGB_sha256','split_role','acquisition_group'):
            if record.get(key)!=source.get(key):
                raise ValueError('label_source_binding_changed')
        if source['split_role'] not in (DEVELOPMENT,HISTORICAL):
            raise ValueError('explicit_known_split_role_required')
        if any(r.get('label') not in LABELS for r in record['groups']):
            raise ValueError('missing_or_unknown_label')
        members = [i for r in record['groups'] for i in r['component_ids']]
        if not members or len(set(members))!=len(members):
            raise ValueError('nonempty_nonduplicated_groups_required')
        if source['split_role']==HISTORICAL:
            excluded += 1
            continue
        group = source.get('acquisition_group')
        if not isinstance(group,str) or not group.strip():
            unknown_groups.append(source['source_id']); group=None
        for region in record['groups']:
            label = region['label']; c = classes[label]
            c['regions'] += 1; c['photos'].add(source['source_id'])
            if group is not None:
                c['capture_groups'].add(group)
                group_counts.setdefault(group,Counter())[label] += 1
    summary = {label:dict(regions=v['regions'],photos=len(v['photos']),
               capture_groups=len(v['capture_groups'])) for label,v in classes.items()}
    blockers = []
    if unknown_groups: blockers.append('capture_group_unknown')
    for label in ('visible','not_observed'):
        if summary[label]['capture_groups'] < 3:
            blockers.append(label+'_in_fewer_than_three_capture_groups')
    folds=[]
    for group,counts in sorted(group_counts.items()):
        train = {label:summary[label]['regions']-counts[label] for label in ('visible','not_observed')}
        test = {label:counts[label] for label in ('visible','not_observed')}
        folds.append(dict(held_out_capture_group=group,train=train,test=test,
                          both_classes_in_train=all(train.values()),both_classes_in_test=all(test.values())))
    return dict(version='photo_visibility_data_readiness_v1',metadata_only=True,
                source_pixels_revalidated_by_this_function=False,development=summary,
                historical_photos_excluded_from_training=excluded,leave_one_capture_group_out=folds,
                necessary_three_role_class_group_coverage_met=not blockers,blockers=blockers,
                independent_validation_established=False,person_independence_established=False,
                automatic_training_performed=False,uncertain_used_as_negative=False,
                additional_negative_capture_groups_needed_for_necessary_condition=max(0,3-summary['not_observed']['capture_groups']),
                requirement_is_not_a_statistical_sample_size_guarantee=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roster',required=True,type=Path);p.add_argument('--labels',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    rb=a.roster.read_bytes();lb=a.labels.read_bytes();roster=json.loads(rb.decode('utf-8-sig'));labels=json.loads(lb.decode('utf-8-sig'))
    if labels.get('roster_sha256')!=hashlib.sha256(rb).hexdigest():raise ValueError('roster_hash_mismatch')
    result=audit(labels,roster)
    result['input_sha256']={'roster':hashlib.sha256(rb).hexdigest(),'labels':hashlib.sha256(lb).hexdigest()}
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
