# Experimental crease-optional distal pad estimation

`distal_pad_estimator_experimental.py` is a separate wrapper over the existing SAM review extractor. It does not alter original detector policy or frozen transform code. RGB tip/cap and major axis anchor longitudinal width, distance-transform and ridge energy/coherence signals. Observed crease is optional high-confidence evidence. Geometry fallback is never accepted by this wrapper. Weak cue agreement produces an empty rejected prediction and a separate diagnostic mask.

The fixed engineering constants are available in `POLICY`. Confidence is a cue-group fraction, not a probability, and has not been optimized on the four GT images. Returned region metadata includes `proximal_boundary_source`, `confidence`, `contributing_cues`, `reject_reason` and mask. All results remain private review candidates with `approved_for_use=false`, including confidence >=0.75.

```sh
python ai/scripts/evaluate_distal_pad_experimental.py --roster /path/to/private/SAM-roster.json --output /path/to/private/distal_results
python ai/scripts/evaluate_distal_pad_experimental.py --roster /path/to/private/GT-roster.json --ground-truth-root /path/to/private/ground_truth --output /path/to/private/distal_GT_results
```

Roster entries are `{sample_id, source, manifest}`. GT is read only after inference. Source/mask hash and native encoded coordinate checks reuse the existing loader. `experimental_pad_mask.png` represents actual review proposals; `diagnostic_only_mask.png` must not be treated as approved output. Do not publish either or the associated details/previews.

RGB and SAM-mask generation use the existing documented producer. Keep its model environment isolated. Do not tune the confidence threshold to maximize the four-image GT metric. Further confidence/semantic safety assessment is blocked on three additional human annotations; see [experimental results](../results/distal_pad_experimental_summary.md).

## Seven-annotation evaluation

The estimator remains unmodified and unapproved. See [GT7 results](../results/distal_pad_GT7_summary.md): macro positive IoU 0.4913, component coverage 70%, anatomically wrong high-confidence candidates. The additional annotations are sufficient to reject this development candidate; more annotation is not requested now.

```sh
python ai/scripts/evaluate_distal_pad_gt7.py --roster /path/to/private/GT7-roster.json --output /path/to/private/GT7-evaluation --benchmark-sample CAP-042
```

Roster entries contain `sample_id`, `source`, `manifest`, `GT_folder`. Annotation metadata is validated first but never passed into the estimator. Explicit ambiguous samples are not converted to positives/negatives, and verified empty non-target masks are supported. Missing status on existing human-reviewed nonempty masks is recorded as a legacy positive interpretation, without editing source.json. Public output must be sanitized separately; raw output includes private artifacts.
