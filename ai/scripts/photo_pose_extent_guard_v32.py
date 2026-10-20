"""Conservative experimental cap/observed terminal-segment consistency guard."""
import numpy as np

MAX_WIDTH_TO_TERMINAL_SEGMENT=1.5


def bounded_caps(mask,report,pose):
    returned=mask.copy();rows=[]
    for item in report['candidates']:
        row=dict(item)
        if row['status']=='rounded_cap_applied':
            geometry=row['geometry'];width=float(geometry['reference_width'])
            length=float(np.linalg.norm(np.asarray(geometry['tip_xy'])-geometry['joint_xy']))
            if not np.isfinite([width,length]).all() or min(width,length)<=0:
                raise ValueError('pose_cap_extent_contract')
            ratio=width/length
            row['terminal_extent_guard']=dict(maximum_width_to_segment=MAX_WIDTH_TO_TERMINAL_SEGMENT,
                observed_width_to_segment=ratio,anatomical_validation=False)
            if ratio>MAX_WIDTH_TO_TERMINAL_SEGMENT:
                axis=next(a for a in pose['axes'] if 'pose-'+a['digit']==row['candidate_id'])
                returned[pose['owner_labels']==axis['label']]=False
                row.update(status='base_retained',reason='terminal_segment_width_inconsistent',
                    after_pixels=0,unanchored_candidate_excluded=True,review_required=True)
        rows.append(row)
    return returned,dict(report,candidates=rows,terminal_extent_guard_experimental=True,
        applied_caps=sum(row['status']=='rounded_cap_applied' for row in rows),
        unresolved_candidates=sum(row['status']=='base_retained' for row in rows))
