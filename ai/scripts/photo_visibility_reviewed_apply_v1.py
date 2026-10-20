"""Opt-in human-reviewed whole-pad synthetic replacement using unchanged V19.

Visibility probes are not classifiers and never authorize replacement here.
Every region needs an explicit source/mask-bound human decision. Uncertain and
not-observed regions retain their original RGB; this is not a privacy proof.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_synthetic_replacement_v19 import render
from photo_visibility_annotation_v1 import Project, component_map
from final_png_color_metadata_v1 import save_final_rgb_png
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged
from photo_synthetic_replacement_v10 import MAX_REGION_PIXELS, MAX_BOUNDING_PIXELS
from photo_reviewed_large_pad_v1 import render_large_pad


def pixels(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def complete_singletons(generated, render_labels, renderer, associations):
    """A one-pixel diagonal leaf cannot carry a ridge cycle of its own.

    Only borrow an immediately adjacent GENERATED pixel from a resolved part of
    the same reviewed pad. Never sample the original or another pad, never grow
    the mask, and never bridge larger unresolved fragments or propagate fills.
    Renderer resolution metadata remains unchanged and completion is explicit.
    """
    resolved={r['region_id'] for r in renderer['regions'] if r.get('fingerprint_texture_resolved') is True}
    out=generated.copy();completed={}
    for region in renderer['regions']:
        rid=region['region_id']
        if rid in resolved:continue
        yy,xx=np.where(render_labels==rid)
        if len(xx)!=1:continue
        y,x=int(yy[0]),int(xx[0]);neighbors=[]
        for dy in (-1,0,1):
            for dx in (-1,0,1):
                ny,nx=y+dy,x+dx
                if 0<=ny<render_labels.shape[0] and 0<=nx<render_labels.shape[1]:
                    other=int(render_labels[ny,nx])
                    if other in resolved and associations[other]==associations[rid]:
                        neighbors.append(generated[ny,nx].astype(np.uint32))
        if neighbors:
            values=np.stack(neighbors);count=len(values)
            out[y,x]=((2*values.sum(axis=0)+count)//(2*count)).astype(np.uint8)
            completed[rid]=dict(pixels=1,method='same_pad_adjacent_generated_RGB_mean',original_pixels_used=False)
    return out,completed


def apply_reviewed(rgb, labels, review, *, seed=None, appearance='v19'):
    if appearance not in ('v19', 'silhouette_v21'):
        raise ValueError('reviewed_appearance_not_supported')
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3
            or not isinstance(labels, np.ndarray) or labels.dtype != np.uint16 or labels.shape != rgb.shape[:2]):
        raise ValueError('reviewed_RGB_labels_contract')
    validate_resize(*labels.shape, 1.)
    if (not isinstance(review, dict) or review.get('version') != 'explicit_visibility_review_v1'
            or review.get('review_origin') != 'human_confirmed' or review.get('all_regions_reviewed') is not True
            or review.get('coordinate_system') != 'upright_native_pixels'
            or review.get('RGB_sha256') != pixels(rgb) or review.get('labels_sha256') != pixels(labels)):
        raise ValueError('explicit_source_bound_human_review_required')
    ids = set(int(i) for i in np.unique(labels) if i)
    decisions = review.get('regions')
    if not isinstance(decisions, list) or len(decisions) != len(ids):
        raise ValueError('every_region_review_required')
    selected = []; seen = set(); rows = []
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError('invalid_region_review')
        rid = item.get('region_id'); label = item.get('decision')
        if (type(rid) is not int or rid not in ids or rid in seen
                or label not in ('visible', 'not_observed', 'uncertain')):
            raise ValueError('invalid_region_review')
        seen.add(rid)
        if label == 'visible':
            selected.append(rid)
        rows.append(dict(region_id=rid, human_decision=label, status='pending_render' if label == 'visible' else
                         ('review_required' if label == 'uncertain' else 'not_applied_human_not_observed')))
    mask = np.isin(labels, selected)
    # A shared group may contain diagonally connected fragments. Give the
    # unchanged renderer separate four-connected components, with provenance.
    render_labels = np.zeros(labels.shape, np.uint16); associations = {}; next_id = 1
    for rid in sorted(selected):
        parts, count = ndimage.label(labels == rid)
        for part in range(1, count + 1):
            if next_id > 256:
                raise ValueError('reviewed_render_component_limit')
            render_labels[parts == part] = next_id; associations[next_id] = rid; next_id += 1
    before = (pixels(rgb), pixels(labels))
    large=[];regular_labels=render_labels.copy()
    for rid,sl in enumerate(ndimage.find_objects(render_labels),1):
        if sl is None:continue
        target=render_labels[sl]==rid
        if int(target.sum())>MAX_REGION_PIXELS or target.size>MAX_BOUNDING_PIXELS:
            large.append(rid);regular_labels[render_labels==rid]=0
    regular_mask=regular_labels>0
    generated, renderer = render(rgb, regular_mask, regular_labels, seed=seed)
    for rid in large:
        target=render_labels==rid
        (y0,y1,x0,x1),local,metadata=render_large_pad(rgb,target,rid,renderer['seed'],render)
        take=target[y0:y1,x0:x1];generated[y0:y1,x0:x1][take]=local[take]
        renderer['regions'].append(metadata)
    if large:
        renderer.update(version='reviewed_mixed_resolution_V19_v1',
            status='synthetic_replacement_applied',
            replacement_regions=len(renderer['regions']),replaced_pixels=int(mask.sum()),
            macro_crease_count=sum(len(r['color_field']['macro_creases']['curves']) for r in renderer['regions']),
            unresolved_texture_regions=sum(r.get('fingerprint_texture_resolved') is not True for r in renderer['regions']),
            actual_changed_pixels=int(np.any(generated!=rgb,axis=2).sum()),output_RGB_sha256=pixels(generated),
            mask_sha256=pixels(mask),working_resolution_region_ids=large,native_texture_resolution_verified=False)
    if generated.dtype != np.uint8 or generated.shape != rgb.shape:
        raise RuntimeError('reviewed_renderer_output_contract')
    if (pixels(rgb), pixels(labels)) != before or not np.array_equal(generated[~mask], rgb[~mask]):
        raise RuntimeError('reviewed_renderer_preservation_contract')
    unresolved = set()
    expected = set(associations)
    actual = [r['region_id'] for r in renderer['regions']]
    if set(actual) != expected or len(actual) != len(expected):
        raise RuntimeError('reviewed_renderer_region_contract')
    returned, completed = complete_singletons(generated, render_labels, renderer, associations)
    for r in renderer['regions']:
        if r.get('fingerprint_texture_resolved') is not True and r['region_id'] not in completed:
            unresolved.add(associations[r['region_id']])
    for row in rows:
        rid = row['region_id']; target = labels == rid
        if rid in unresolved:
            returned[target] = rgb[target]
            row['status'] = 'review_required_renderer_unresolved'
        elif rid in selected:
            if not np.any(returned[target] != rgb[target]):
                row['status'] = 'review_required_no_RGB_change'; unresolved.add(rid)
            else:
                row['status'] = 'synthetic_applied_unverified'
        row['changed_pixels'] = int(np.any(returned[target] != rgb[target], axis=1).sum())
        row['whole_pad_pixels'] = int(target.sum())
        row['generated_singleton_completion_pixels'] = sum(v['pixels'] for k,v in completed.items() if associations[k]==rid)
        row['working_resolution_render_used'] = any(associations[i]==rid for i in large)
    applied = mask & ~np.isin(labels, list(unresolved))
    appearance_report = None
    if appearance == 'silhouette_v21':
        from photo_silhouette_appearance_v21 import refine_regions
        returned, appearance_report = refine_regions(rgb, returned, applied, labels)
        for row in rows:
            target = labels == row['region_id']
            row['changed_pixels'] = int(np.any(returned[target] != rgb[target], axis=1).sum())
    if not np.array_equal(returned[~applied], rgb[~applied]):
        raise RuntimeError('reviewed_final_preservation_contract')
    return returned, applied, dict(version='human_reviewed_visibility_replacement_v1',
        status='synthetic_applied_review_required' if applied.any() else 'no_regions_applied_review_required',
        selection_basis='explicit_human_review_not_diagnostic_signal', regions=rows,
        selected_region_count=len(selected), applied_region_count=sum(r['status']=='synthetic_applied_unverified' for r in rows),
        review_required_count=sum(r['status'].startswith('review_required') for r in rows),
        candidate_pixels=int((labels>0).sum()), applied_mask_pixels=int(applied.sum()),
        changed_pixels=int(np.any(returned != rgb,axis=2).sum()),
        outside_applied_RGB_preserved=True, output_RGB_sha256=pixels(returned),
        original_RGB_sha256=before[0], original_labels_sha256=before[1],
        automatic_visibility_approved=False, privacy_validated=False, production_approved=False,
        independent_validation=False, renderer=renderer, appearance=appearance, appearance_report=appearance_report,
        generated_singleton_completions=completed,
        render_component_to_review_region=associations,working_resolution_render_region_count=len(large))


def run(roster, state, source_id, output, *, seed=None, project=None, appearance='v19'):
    output = Path(output); state = Path(state)
    if output.exists() or output.is_symlink():
        raise FileExistsError('fresh_reviewed_output_required')
    if not (state/'project.json').is_file():
        raise ValueError('existing_completed_review_required')
    snapshot = capture_runtime_sources()
    if project is None:
        project = Project(roster, state)
    elif (type(project) is not Project or project.roster_path != Path(roster).resolve()
            or project.state != state.resolve()):
        raise ValueError('reused_review_project_binding_mismatch')
    if hashlib.sha256(Path(roster).read_bytes()).hexdigest() != project.header['roster_sha256']:
        raise ValueError('review_roster_changed')
    record = project.current(source_id)
    if record.get('status') != 'reviewed' or record.get('human_GT') is not True or record.get('attestation') is not True:
        raise ValueError('completed_human_review_required')
    if record.get('source_id') != source_id or record.get('coordinates') != 'upright_native_pixels_xyxy_exclusive':
        raise ValueError('review_coordinate_contract')
    groups = project.validated_groups(source_id, record['groups'], True)
    rgb, mask = project.arrays(source_id); components, _ = component_map(mask)
    # A human-merged group is one atomic permission unit, even when disconnected.
    labels=np.zeros(mask.shape,np.uint16);group_components={}
    for group in groups:
        rid=group['component_ids'][0]
        labels[np.isin(components,group['component_ids'])]=rid
        group_components[rid]=group['component_ids']
    review = dict(version='explicit_visibility_review_v1', review_origin='human_confirmed', all_regions_reviewed=True,
                  coordinate_system='upright_native_pixels', RGB_sha256=pixels(rgb), labels_sha256=pixels(labels),
                  regions=[dict(region_id=g['component_ids'][0], decision=g['label']) for g in groups])
    returned, applied, report = apply_reviewed(rgb, labels, review, seed=seed, appearance=appearance)
    source = project.sources[source_id]; orientation = source['exif_orientation']
    # V19 ran in upright coordinates. Encode back in the original frame and
    # preserve the validated source ICC/EXIF through the existing PNG writer.
    inverse = {2:Image.Transpose.FLIP_LEFT_RIGHT, 3:Image.Transpose.ROTATE_180,
               4:Image.Transpose.FLIP_TOP_BOTTOM, 5:Image.Transpose.TRANSPOSE,
               6:Image.Transpose.ROTATE_90, 7:Image.Transpose.TRANSVERSE, 8:Image.Transpose.ROTATE_270}
    encoded = Image.fromarray(returned)
    if orientation in inverse:
        encoded = encoded.transpose(inverse[orientation])
    output.mkdir(parents=True, exist_ok=False)
    metadata = save_final_rgb_png(source['source_path'], source['source_sha256'], np.asarray(encoded),
                                  output/'returned.png', orientation)
    with Image.open(output/'returned.png') as im:
        if not np.array_equal(np.asarray(ImageOps.exif_transpose(im)), returned):
            raise RuntimeError('reviewed_saved_upright_RGB_mismatch')
    Image.fromarray(applied.astype(np.uint8)*255).save(output/'applied_mask_upright.png')
    Image.fromarray(mask.astype(np.uint8)*255).save(output/'candidate_mask_upright.png')
    if project.current(source_id) != record:
        raise ValueError('human_review_changed_during_render')
    project.arrays(source_id)  # Recheck original source and mask file hashes.
    report.update(source_id=source_id, input_source_sha256=source['source_sha256'], input_mask_sha256=source['mask_sha256'],
                  review_group_components=group_components,
                  annotation_revision=record['revision'], review=review, png_metadata=metadata,
                  output_frame='encoded_original_pixels_with_original_EXIF', mask_frame='upright_native_pixels',
                  runtime_source_snapshot=assert_runtime_sources_unchanged(snapshot))
    with (output/'result.private.json').open('x',encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    return report


if __name__ == '__main__':
    from protect_fingerprint import JSONArgumentParser, cli_progress_to_stderr
    parser=JSONArgumentParser(description=__doc__)
    for name in ('roster','state','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-id',required=True);parser.add_argument('--seed',type=int)
    parser.add_argument('--appearance',choices=('v19','silhouette_v21'),default='v19')
    args=parser.parse_args()
    try:
        with cli_progress_to_stderr():
            report=run(args.roster,args.state,args.source_id,args.output,seed=args.seed,appearance=args.appearance)
        print(json.dumps(dict(status=report['status'],output=str(args.output.resolve()),
                              applied_regions=report['applied_region_count'],review_required=report['review_required_count'])))
    except Exception as error:
        print(json.dumps(dict(status='error',reason=str(error),error=type(error).__name__)))
        raise SystemExit(1)
