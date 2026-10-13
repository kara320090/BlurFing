# Automatic detection artifact: experimental, not deployment-ready

## Status and baseline
The frozen renderer natural_auto_04, compositor boundaryblend_02, SourceAFIS rules and NBIS policy are unchanged. This work adds a separate detector prototype and an artifact consumer. It does **not** establish reliable automatic boundary protection.

The 20-image development baseline reproduced exactly: candidate photos 10, candidates 17, accepted boundaries 1. The sole legacy boundary mask remains pixel-identical. After periodicity validation it is not transformable. The 20-image prototype has no approved transformation regions. More proposals are not evidence of improvement.

## Eligibility
Four photos have historical human-reviewed ridge-positive ROIs; 11 remain ambiguous and 5 are provisionally non-target/object-occluded. Labels are developmental and not expert boundary ground truth. Existing identity/ridge labels do not identify every background pixel or the joint crease. No independent holdout is used.

## Prototype stages
- Existing legacy-approved geometry remains a separate protected path.
- Aspect-preserving internal 1024/1600 views and exact quadrant rotation generate candidates; native coordinates are restored.
- Cross-view center/width NMS removes duplicate proposals.
- Seeded local graph-cut separates candidate foreground before multi-row median width/IQR checks.
- Width outliers are compared with the measured median, rather than a potentially undersized cap estimate.
- A local dark-valley path creates a curved lower boundary. Original absolute crease-response, coverage and prior-distance requirements are retained.
- Search-window contact is checked before erosion so the forced graph-cut border cannot hide clipping.
- Original pitch measurement and spatial fallback consensus remain unchanged.
- **New graph-cut masks stay review-gated.** They are never automatically promoted from heuristics to safe protection masks.

The close-up positive case now has a candidate and foreground proposal, but its full proposed pad extent cannot fit the frozen renderer's square scope within the image. We reject it, rather than truncate the mask silently or change renderer mathematics.

Arbitrary oblique finger normalization, reliable small-finger detection and palmar-vs-nail classification are not validated. New approvals require human boundary references and explicit background/neighbor leakage validation; current source alone is not a substitute.

## Portable artifact contract
Run from repository root, with private input/output paths:
```sh
python ai/scripts/detection_artifact.py detect --input /path/to/input.jpg --output /path/to/private/detection_result
python ai/scripts/detection_artifact.py consume --input /path/to/input.jpg --detection /path/to/private/detection_result/detection.json --output /path/to/private/returned_result
```
Output folders must be new. Actual artifacts are private and must not be committed.

Artifacts contain detection.json, full-image fingerprint_mask.png, per-region binary masks and detection_timing.json. JSON paths are relative basenames. Mask coordinates are the EXIF-transposed input RGB coordinates; pixels are 8-bit 0=forbidden, 255=allowed. Multiple regions use per-region ROI/pitch fields. Empty rejected masks return unchanged RGB.

The consumer checks schema, source file SHA-256, decoded RGB SHA-256, EXIF state, dimensions, PNG mode, mask SHA-256, binary values, ROI/seed bounds, seed inclusion, connected components, region overlap, union equality and finite pitch. It re-observes pitch on the input. Wrong source/shape/mask fails before rendering. Decoder differences across operating systems fail closed via decoded RGB hash.

Canonical detection JSON and masks exclude timing; timing is stored separately for deterministic transfer. Source/mask hash matching validates integrity, not detector accuracy or artifact authenticity. Only artifacts from a trusted producer should be consumed.

The consumer imports the one frozen compositor, temporarily binds the validated geometry and restores bindings/renderer on exceptions. Existing structure inspection remains mandatory. Changed pixels outside the authorized full-frame mask cause an error.

## Installation, smoke tests and runtime
Install ai/requirements.txt in a venv. No new model/package is required.
```sh
python ai/scripts/test_detection_artifact.py
python ai/scripts/reproduce_frozen_pipeline.py --check
```
These public-source tests use synthetic data, not private photographs. They do not claim real detector accuracy.

Actual transform structure inspection requires JDK >=11 and the hash-pinned SourceAFIS artifacts; see LINUX_SETUP.md. Set BLURFING_SOURCEAFIS_HOME and optionally BLURFING_SOURCEAFIS_CONFIG for private runtime locations. Optional NBIS evaluation uses BLURFING_NBIS_CONFIG and the existing native bridge contract. Never copy private runtime into Git.

## Benchmark
```sh
python ai/scripts/benchmark_detection_artifact.py --input /path/to/input.jpg --output /path/to/private/benchmark --repeats 10 --matchers
```
One warmup is excluded. Candidate generation, boundary/pitch, transform, NBIS, SourceAFIS and total time are separate. Transform time includes mandatory SourceAFIS structure extraction; the separately reported SourceAFIS time is pair matching evaluation. Applied and unchanged runs are separated. Reports include mean/median/min/max/std/p95.

A separate existing developer control passed artifact→transform, outside preservation and both matchers over ten measured runs. This validates the artifact integration, **not** the new masks or detection success on the 20-image set.

## Required human evidence before promotion
Provide reviewed whole-pad masks (or explicit foreground/background/crease annotations) for the ridge-positive examples and negative controls. Historical square texture ROIs cannot establish background leakage or lower crease accuracy. No threshold loosening or matcher-score-based ROI selection is used to bypass this requirement.

FINAL_INDEPENDENT_VALIDATION_COMPLETE=false; PROJECT_COMPLETE=false. General fingerprint protection is not established.

## Human mask evaluation follow-up
Four human pad references are now available. [Quantitative evaluation](../results/linux_detection_gt_evaluation.md) still rejects promotion: all approved artifacts are empty, despite a close-up raw proposal with high GT overlap. The remaining blocker is unusable masks and frozen square-scope mismatch, rather than missing positive annotations. Negative/control segmentation evidence remains necessary. The evaluator validates source/mask hashes, EXIF and encoded dimensions; it never authorizes a region.
