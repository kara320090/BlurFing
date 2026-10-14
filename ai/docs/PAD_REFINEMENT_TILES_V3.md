# Development-only body tile refinement V3

This opt-in experiment expands model observation beyond the historical coarse-pad crop. It does not replace the default PHOTO detector, adopt the rejected V1 refinement, change frozen protection mathematics, or change detector/pitch/feature/matcher thresholds.

## Data and protocol

Geometry uses only source identity and observed semantic finger body: deterministic 512-native-pixel windows, 384 stride, endpoint anchoring, connectivity 4, and the existing 256-pixel letterbox. Small body components are retained. A whole source is rejected if its resource-bounded plan cannot cover all native body pixels; targets never select/filter windows. Native coverage does not prove that downsampling preserves every small detail. Predictions are clipped to observed body, so finger-body segmentation misses remain unrecoverable.

The V3 contract separates supervised crop NPZs from zero-label input NPZs. Published input manifests contain no target paths/hashes; validation prediction and standalone inference read only that input view. Source/mask hashes, canonical pixel identities, complete ordered boxes and RGB/coarse/label contents are checked. Consumed GT7 and eight prior holdout appearances are excluded using both file and decoded RGB identities; the exclusion registry must match the trained checkpoint. Raw original holdout file identities may be unavailable when only derived RGB copies were imported.

GT10 was already inspected during development. The V3 protocol is frozen before new V3 training/validation results, not a first blind evaluation of GT10. Two acquisition-folder/date groups are held out in turn (7 and 3 sources); they do not establish independent biometric subjects or sessions. Early stopping uses native-source macro IoU, at most 40 epochs and patience 6. The final fit uses the floored median of the two best epochs, with the earliest strictly better IoU checkpoint winning ties. Source-macro and group-macro scores are reported separately.

Official SHA-verified MobileNetV3-small ImageNet weights are mandatory. The historical network, aligned augmentation, optimizer and BCE/Dice math are retained. All tiles occur once per epoch with seeded shuffling and weight `T/(S*n_source)`; weighted per-example loss is divided by the configured batch size 4, including the last partial batch. This makes total source loss mass equal across an epoch without per-batch normalization. CPU deterministic training is used. Parameters, buffers and gradients must remain finite.

Overlapping tile probabilities are restored with explicit bilinear interpolation, summed and divided by actual native overlap counts. Threshold 0.5 is applied after averaging. Endpoint anchoring can create more than four overlaps; the implementation counts actual windows. Manifest snapshots, code hashes, runtime versions, official weights and model checkpoint SHA are recorded. Changed inputs/code prevent publication of a completed training or inference report. A failed run leaves diagnostic artifacts without a success report.

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
