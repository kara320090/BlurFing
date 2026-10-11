from visible_pad_scope_v3 import propose_visible_pad as raw_proposal

def propose_visible_pad(image,seed_roi):
    scope,mask,meta=raw_proposal(image,seed_roi)
    if scope is None:return scope,mask,meta|dict(automatic_boundary_accepted=False)
    disagreement=abs(meta['bottom_y']-meta['geometric_bottom_y'])/meta['width']
    observed=not meta['lower_boundary_geometric']
    accepted=observed and disagreement<=.2
    meta=meta|dict(automatic_boundary_accepted=accepted,crease_prior_disagreement_width_fraction=disagreement,
        boundary_gate='observed crease and distance from prior <=0.2 finger width',
        boundary_accuracy_validated=False,human_review_required=not accepted)
    if not accepted:
        return None,None,meta|dict(status='scope_boundary_requires_review',proposed_scope_roi=scope)
    return scope,mask,meta
