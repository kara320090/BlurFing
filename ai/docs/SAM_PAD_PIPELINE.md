# Linux SAM finger masks → fingerprint pads

This is a review-gated development pipeline, not an approved protection detector. Shared frozen renderer natural_auto_04 and compositor boundaryblend_02 are unchanged.

## Coordinates and inputs

Input RGB and mask arrays use original encoded JPG coordinates. Source SHA-256, native dimensions, schema, relative mask path, PNG SHA, grayscale mode and 0/255 values are validated. EXIF orientation is handled during the optional SAM producer's working-image transformation and inverted back to native coordinates. Current samples are 4000×3000 encoded, 3000×4000 upright. Do not pass upright masks as native masks.

`sam-finger-input-v1` manifests contain source_sha256, image_width, image_height, coordinate_system and a masks list with mask_path/mask_sha256. The producer may attach tip_hint_native and RGB-only provenance. The loader uses source bytes to validate the manifest. No GT argument exists in the producer or extractor.

## Extraction

Clean each finger's connected components, require dominant-component consistency, estimate PCA axis, normalize a local analysis crop, compute robust multi-scanline width profiles and estimate cap direction. An optional RGB proposal tip resolves axis sign, subject to foreground proximity and endpoint checks. Estimate distal crease valleys from low-frequency grayscale residual and transverse coverage. Trace a smoothed local crease when observed; geometry fallback is explicitly flagged for review. Inverse-map and intersect with the input finger mask. A subset assertion prevents new exterior pixels. Unstable or mixed geometry rejects fail-closed.

Each region exposes native binary pad mask, bbox, axis, tip, width profile, crease/quality reasons and renderer compatibility metadata. Output schema `sam-pad-candidates-v1` deliberately uses review_required and approved_for_use=false; it is not an accepted protection artifact. The existing consumer must not be invoked until aggregate gate and individual structure/runtime checks pass.

## Private CLI usage

Use a separate optional SAM environment with PyTorch and Meta segment-anything (Apache-2.0); supply separately obtained weights. No weights or new dependency are added to the core environment. The experiment used ViT-B, torch 2.13.0+cu130 on CPU, four threads. Common pad evaluation requires the existing NumPy/OpenCV/Pillow/SciPy dependencies. The model producer uses independent RGB-only point/box proposals and highest-score SAM multimask selection, not manually provided GT prompts.

```sh
python ai/scripts/generate_sam_finger_inputs.py prompts --input /path/to/private/input.jpg --output /path/to/private/prompts.json
/path/to/sam-env/bin/python ai/scripts/generate_sam_finger_inputs.py infer --input /path/to/private/input.jpg --prompts /path/to/private/prompts.json --checkpoint /path/to/private/sam_vit_b_01ec64.pth --output /path/to/private/sam_result
python ai/scripts/sam_pad_detector.py --input /path/to/private/input.jpg --finger-manifest /path/to/private/sam_result/sam_fingers.json --output /path/to/private/pads
python ai/scripts/evaluate_sam_pad.py --roster /path/to/private/roster.json --ground-truth-root /path/to/private/ground_truth --output /path/to/private/evaluation
python ai/scripts/evaluate_sam_pad.py --benchmark-only --input /path/to/private/input.jpg --finger-manifest /path/to/private/sam_result/sam_fingers.json --output /path/to/private/benchmark
python -m unittest discover -s ai/scripts -p 'test_sam_pad_detector.py'
```

Roster is a JSON list of `{sample_id, source, manifest}`. GT source.json and binary ground_truth_mask.png are validated by the existing evaluation utility. The evaluator reads GT after inference. Private outputs include masks, overlays and detailed metadata; do not publish them. SAM producer outputs must also remain private.

## Acceptance and limitations

Gate values and outcomes are documented in ../results/sam_pad_evaluation_summary.md and sam_pad_status.json. A measured gate failure blocks all downstream execution. Macro improvements cannot override sample-specific leakage. Four development images cannot establish generalization, non-target robustness or independent protection efficacy. Current detector is not approved; DET-03 needs better foreground rejection, and DET-05 boundary excess needs investigation without GT-based threshold optimization. Square scope and pitch compatibility remain a separate frozen-renderer blocker.

## Foreground follow-up

The v2 review extractor detects near-full-frame SAM contamination using frame occupancy and image-edge proximity, then performs RGB-only Otsu red-minus-green chroma separation before axis estimation. Uncertain partitions stay unchanged. It remains review-gated; missing crease is explicitly reported. See [foreground follow-up](../results/sam_pad_foreground_refinement_summary.md) for four-sample results, residual proximal leakage and approval status. Existing CLI commands are unchanged.

## Proximal boundary evidence observer

`proximal_boundary_evidence.py` computes axial grayscale, crease, width, distance-transform, ridge energy/coherence and spectral diagnostics from the RGB/mask analysis frame. Its API accepts no GT. Slightly tilted transverse crease sampling is included. A crease plus independent appearance transition is required; width and distance alone are insufficient. Missing evidence returns `proximal_boundary_unobserved`. Diagnostic geometry fallback must never authorize protection. Existing accepted crease masks are retained without boundary recalculation, but are labeled legacy evidence rather than newly certified multi-cue boundaries.

Private signal rendering:

```sh
python ai/scripts/plot_proximal_diagnostics.py --details /path/to/private/evaluation/DET-03/pad_candidates.private.json --output /path/to/private/proximal_signals
```

Output CSV uses analysis rows and native longitudinal distances. Orange plot lines indicate geometry fallback, blue lines show diagnostic peaks; neither denotes accepted ground truth. See [proximal observation report](../results/sam_pad_proximal_summary.md). No detector approval or downstream execution was granted.
