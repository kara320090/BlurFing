# Development-only body tile refinement V3

This opt-in experiment expands model observation beyond the historical coarse-pad crop. It does not replace the default PHOTO detector, adopt the rejected V1 refinement, change frozen protection mathematics, or change detector/pitch/feature/matcher thresholds.

## Data and protocol

Geometry uses only source identity and observed semantic finger body: deterministic 512-native-pixel windows, 384 stride, endpoint anchoring, connectivity 4, and the existing 256-pixel letterbox. Small body components are retained. A whole source is rejected if its resource-bounded plan cannot cover all native body pixels; targets never select/filter windows. Native coverage does not prove that downsampling preserves every small detail. Predictions are clipped to observed body, so finger-body segmentation misses remain unrecoverable.

The V3 contract separates supervised crop NPZs from zero-label input NPZs. Published input manifests contain no target paths/hashes; validation prediction and standalone inference read only that input view. Source/mask hashes, canonical pixel identities, complete ordered boxes and RGB/coarse/label contents are checked. Consumed GT7 and eight prior holdout appearances are excluded using both file and decoded RGB identities; the exclusion registry must match the trained checkpoint. Raw original holdout file identities may be unavailable when only derived RGB copies were imported.

GT10 was already inspected during development. The V3 protocol is frozen before new V3 training/validation results, not a first blind evaluation of GT10. Two acquisition-folder/date groups are held out in turn (7 and 3 sources); they do not establish independent biometric subjects or sessions. Early stopping uses native-source macro IoU, at most 40 epochs and patience 6. The final fit uses the floored median of the two best epochs, with the earliest strictly better IoU checkpoint winning ties. Source-macro and group-macro scores are reported separately.

Official SHA-verified MobileNetV3-small ImageNet weights are mandatory. The historical network, aligned augmentation, optimizer and BCE/Dice math are retained. All tiles occur once per epoch with seeded shuffling and weight `T/(S*n_source)`; weighted per-example loss is divided by the configured batch size 4, including the last partial batch. This makes total source loss mass equal across an epoch without per-batch normalization. CPU deterministic training is used. Parameters, buffers and gradients must remain finite.

Overlapping tile probabilities are restored with explicit bilinear interpolation, summed and divided by actual native overlap counts. Threshold 0.5 is applied after averaging. Endpoint anchoring can create more than four overlaps; the implementation counts actual windows. Manifest snapshots, code hashes, runtime versions, official weights and model checkpoint SHA are recorded. Changed inputs/code prevent publication of a completed training or inference report. A failed run leaves diagnostic artifacts without a success report.

The standalone checkpoint loader applies the same eight-thread deterministic CPU settings before prediction. A synthetic audit found that fresh process defaults (16 threads on the audited machine) could change logits by about `3.6e-6` and flip a deliberately boundary-centered synthetic pixel. The incomplete initial training record was retained; a new run completed under the corrected code hashes. This is a runtime reproducibility fix, with no threshold or protection-math change.

## Commands

Run using the isolated CPU PyTorch environment. All private inputs, masks, manifests and weights must remain outside Git. Output folders must be fresh.

```text
python ai/scripts/pad_refinement_tiles_v3.py --inputs PRIVATE_INPUTS.json --consumed-registry PRIVATE_REGISTRY.json --output PRIVATE_DATASET
python ai/scripts/train_pad_refinement_tiles_v3.py --dataset PRIVATE_DATASET --encoder-weights OFFICIAL_WEIGHTS.pth --output PRIVATE_TRAINING
python ai/scripts/infer_pad_refinement_tiles_v3.py --model PRIVATE_TRAINING --inputs PRIVATE_DATASET --output PRIVATE_PREDICTIONS
```

Standalone inputs use `--purpose inference` and omit GT fields. Group-heldout OOF predictions are developmental results; final-fit predictions on training sources verify operation only. A fresh independent acquisition set and human pad masks remain required before any adoption. Consumed GT7/holdout and user examples must not be reused to tune this experiment. Lower matcher scores/extraction failures are not general privacy or security proof.

## Experimental protection connection

`photo_learned_pad_pipeline_v1.py` explicitly connects V3 predictions to the existing per-component scale plan, pitch observer and frozen renderer. Each full learned component must belong to exactly one validated observed finger-body owner with an observed estimator axis. Invalid owners still participate in ambiguity checks. Crossing owners, unavailable axes and more than 256 predicted components are rejected; masks are never filtered, split or assigned by largest overlap. Rounded estimator resize ratios, EXIF direction and actual renderer ratios are preserved. A learned pad may extend beyond the old coarse pad while remaining wholly inside its unique body owner.

The existing candidate-body width observer and unchanged pitch/feature/structure gates determine whether protection can run. Rejected pixels and every pixel outside the learned mask remain identical. Renderer `applied` must be a boolean and structure guard must be explicitly true. Saved PNG RGB is checked by decoding it again. This remains an opt-in developmental path without algorithm or privacy approval.

```text
python ai/scripts/photo_learned_pad_pipeline_v1.py --model PRIVATE_TRAINING --inputs PRIVATE_DATASET --output PRIVATE_PROTECTION
```

### Body-local allocation V2

`photo_learned_pad_pipeline_v2.py` retains the complete uniquely associated body owner and crops real source pixels around its bounding box. The context halo is an engineering geometry rule, `max(2 native pixels, ceil(2 working pixels / normalization scale))`: cubic interpolation neighbors and exterior body samples must come from the source. Original-frame clipping is recorded. No new body evidence is created outside the frame and no width/pitch/feature gate is relaxed. Tiny fragments can still exceed the allocation budget even with a local body crop.

Global estimator working-to-native axis conversion occurs before cropping. Integer translation preserves that native direction; EXIF and actual rounded local resize ratios are applied by the shared geometry helper. The virtual crop has a separate hash identity bound to parent source, native bbox, RGB/body/mask pixels and EXIF. ROI metadata explicitly distinguishes virtual-crop coordinates and maps the bbox back to original encoded coordinates. Local output is checked before compositing only learned native pixels into original RGB. Full-photo and cropped interpolation/seed inputs can differ; numerical or protection equivalence is not claimed. Frozen renderer/width functions themselves remain unchanged.

```text
python ai/scripts/photo_learned_pad_pipeline_v2.py --model PRIVATE_TRAINING --inputs PRIVATE_DATASET --output PRIVATE_PROTECTION
```

## Completed developmental experiment (2026-10-15)

Ten GT10 sources produced 295 body tiles (85 with positive labels, 210 without). Two acquisition groups were held out; best epochs were 20 and 6, so the final full-training fit used 13 epochs. The final checkpoint SHA-256 is `b168c8af175018d83ae796a97af7fad34ba16c28ec19332976057a373fbc143c`. Weights and every source/target/prediction remain private.

The comparison below uses the SAME native GT10 masks for coarse and saved group-heldout V3 predictions. It is developmental model selection, with no independent final-test claim.

| Native source metric | Existing coarse | V3 group-heldout |
|---|---:|---:|
| Source macro IoU | 0.351117 | 0.427477 |
| Source macro Dice | 0.478698 | 0.582013 |
| Precision | 0.384515 | 0.615640 |
| Recall | 0.815136 | 0.616467 |
| GT pixel miss fraction | 0.184864 | 0.383533 |
| Group macro IoU (equal two-group weight) | 0.370426 | 0.415707 |

IoU improved on eight sources and declined on two. Improved precision comes with more missed GT pixels. Predicted connected components increased from 21 to 145. One-to-one nonzero-IoU matching against 38 GT components matched 16 then 33, but unmatched components increased from 5 to 112. Of the V3 unmatched components, 85 have zero GT overlap and 27 are additional fragments overlapping GT. These counts do not identify anatomical fingers. Body clipping has a GT recall ceiling of about 0.946 source macro, but it does not explain the full V3 recall loss.

Protection was exercised on those saved group-heldout masks, preserving original/rejected/exterior pixels and every PNG RGB roundtrip. Both full-photo V1 and body-local V2 transformed **0/10 sources**. V1 rejected 142/145 components for memory, two for pitch and one for crossing an owner. V2 outcomes: 95 memory, 17 pitch, 24 crossing owners, seven ambiguous owners and two unavailable widths. Of the 142 original memory rejections, only 17 reached bounded local quality checks (15 pitch, two width); 30 were rejected earlier by ownership checks. No component was filtered and no gate was weakened.

Both heldout checkpoint replay probes matched saved OOF masks exactly with zero GT reader calls. The completed final checkpoint ran twice on all ten training-source input bundles, again with zero GT reader calls and exact mask/file hashes. That final-fit check verifies operation, not generalization. All 354 AI tests passed, including six local-scope tests for allocation, actual-source context, EXIF axes, coordinate mapping and exterior preservation. An independent code review found no mandatory unresolved implementation defect in the examined paths.

The experiment is **not adopted**. Remaining observed limitations include pad-pixel misses, excessive fragments, uncertain body association and pitch/width evidence. New development annotations from additional acquisition groups and a genuinely fresh final validation set are required before production decisions. Consumed GT7 and old holdout were not rerun or tuned.

The later [native body-owner protection audit](PHOTO_BODY_OWNER_PROTECTION.md) fixes fragment-driven normalization and connects same-owner observation support with an actual-return RGB structure guard. Historical V1/V2 results above remain unchanged; the newer opt-in V4 and single-photo entry point do not adopt the model or replace the default GUI.
