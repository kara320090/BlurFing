# Experimental semantic-body distal pad estimator

This route evaluates geometry on pretrained COLFISPOOF class 1+2 finger masks. It is not an approved PHOTO protection frontend. Class 2 is optional direction evidence; it is not the entire required pad. The scanner, frozen renderer and preserved legacy paths are unchanged.

## Semantic input

Using the isolated TensorFlow environment described in [raw evaluation](COLFISPOOF_RAW_EVALUATION.md):

```bash
/path/to/model-env/bin/python ai/scripts/colfispoof_body_semantics.py \
  --input /path/to/input.jpg \
  --output /path/to/private/semantics/DEV-01 \
  --external-source /path/to/COLFISPOOF/pre-processing \
  --model /path/to/COLFISPOOF/pre-processing/Segmentation/model/deeplab_model.tar.gz
```

The output must be a new private directory. It contains native binary `body.png`, `tip.png` and hash/coordinate-bound `semantics.json`. Source images are decoded in encoded-original coordinates, without EXIF transposition. All four rotations are inverted before fixed >=2/4 voting. External source and model are not vendored. Upstream COLFISPOOF acknowledgment and usage requirements continue to apply.

## Estimator API

In the common scientific-Python environment:

```python
from finger_body_distal_estimator import estimate
result = estimate(body_binary_boolean_array, tip_binary_boolean_array)
# result['mask']: native boolean distal candidate mask
# result['regions']: bbox, axis, endpoints, width profile, source/confidence/reject
# result['approved_for_use']: False (experimental candidates)
```

Inputs must have equal shape and every tip pixel must be inside body. GT, source filenames and person information are absent from this API. Computation uses a maximum-side 512 working image, deterministic watershed when multiple semantic tip markers share a body, PCA axis and scanline centerline. Skeleton endpoints and distance-transform widths are retained as diagnostics. Metadata endpoints/widths are in explicitly marked working-image coordinates; bbox and mask are native.

Class-1-only candidates require a uniquely truncated proximal side at the actual image frame and a sufficiently elongated major axis. If that direction is ambiguous, the component is rejected. Class-2 candidates use its position to select the distal axis endpoint. The fixed pad extent is 1.35 reference widths; sustained widening above 1.45 reference widths can shorten it. No parameter was selected by GT score. The confidence is an engineering score, not a probability or observed crease. No ridge threshold gates the candidate.

The 2026-10-14 audit corrected an off-by-one in this sustained-widening scan: the last complete window beginning at `N-K` is included. A synthetic terminal six-row widening now shortens the extent from 119 to 114.5, with identical masks after inverse quarter-turns; an incomplete five-row run still does not qualify. Native body/tip preservation and detector integration are tested. The existing 10-case Windows matrix and a/b default results remained exact when rerun with validated, source-bound semantic caches and the actual renderer/appropriate matcher. This rerun did not perform fresh TensorFlow inference or establish new independent protection performance. Parameters, model, frozen renderer and existing Linux references are preserved.

## Private quantitative evaluation

Use a private roster with `sample_id`, `source` and `GT_folder`, matching the existing human-annotation format. Semantic folders must be named by sample ID.

```bash
/path/to/evaluation-env/bin/python ai/scripts/evaluate_finger_body_distal.py \
  --roster /path/to/private/roster.json \
  --semantic-root /path/to/private/semantics \
  --output /path/to/private/new-evaluation
```

The evaluator validates source/semantic hashes, native shapes and binary masks, estimates twice for determinism, then uses GT only for metrics and overlays. It reports raw pad and separate ridge diagnostic metrics with the unchanged IoU>=0.5 one-to-one component matching rule. Ambiguous annotations are excluded from positive aggregate metrics.

All generated PNGs, input identities and overlays remain private. Publish only anonymous measurements. [GT7 results](../results/finger_body_distal_gt7_summary.md) show improved coverage but insufficient macro IoU and excessive CAP-016 proximal extension; therefore automatic protection integration is disabled.
