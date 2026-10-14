# Semantic finger body to distal pad: GT7 development evaluation

External COLFISPOOF DeepLab classes 1+2 form finger body; class 2 supplies optional distal-direction evidence. Four rotations, encoded-original inverse mapping and fixed >=2/4 consensus remain unchanged. Fresh class-2 masks were byte-identical to the previous class-2-only run. No GT, filename or person enters estimation, and there was no parameter search on GT7.

Each component has a PCA major axis, skeleton, skeleton endpoints and robust longitudinal scanline centerline. Multiple class-2 markers split connected body regions by distance-transform watershed. Without class 2, an actual foreground/image-frame intersection identifies the truncated proximal side; a uniquely opposite in-frame endpoint is the distal candidate. Ambiguous interior bodies fail closed.

The candidate distal extent is 1.35 times the reference scanline width measured in the initial 10–25% of the component's major-axis span. Class-2 evidence is retained; sustained proximal widening above 1.45 times that width can shorten the region. Distance-transform widths and skeleton endpoints are reported as diagnostics. The confidence is an uncalibrated engineering score, not a model posterior or observed anatomical crease. Every native pad is intersected with native body and has zero exterior expansion.

## Results

| Sample | Class-2 IoU | Body distal IoU | Precision | Recall | Leakage | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.8631 | 0.8989 | 0.9629 | 0.9311 | 3.71% | 2/2 |
| DET-03 | 0.0000 | 0.5946 | 0.9971 | 0.5957 | 0.29% | 1/1 |
| DET-04 | 0.7495 | 0.7938 | 0.9914 | 0.7993 | 0.86% | 3/3 |
| DET-05 | 0.2873 | 0.6586 | 0.9880 | 0.6639 | 1.20% | 1/1 |
| CAP-016 | 0.0490 | 0.6649 | 0.7108 | 0.9114 | 28.92% | 1/1 |
| CAP-042 | 0.7129 | 0.7804 | 0.9981 | 0.7816 | 0.19% | 1/1 |
| CAP-054 | 0.8197 | 0.8789 | 0.9820 | 0.8933 | 1.80% | 1/1 |

Macro IoU increases from **0.4973 to 0.7529**, coverage from **7/10 to 10/10**. There are zero unmatched predicted components and zero missed GT components at the unchanged one-to-one component IoU>=0.5 threshold. This does not mean zero pixel leakage.

DET-03 recovers a partial pad from class 1 alone; recall remains 59.57%. DET-05 recall improves from 28.73% to 66.39%. CAP-016 recall improves from 4.90% to 91.14%, but precision drops to 71.08% and GT-outside ratio rises to 28.92%. Private overlays show proximal finger overextension rather than renewed wrist selection. Keyboard/background component selection remains absent in CAP-042/054.

**PHOTO_DETECTOR_APPROVED=false**: macro IoU misses 0.85; geometric cutoff is not sufficiently precise. No frozen renderer, scanner branch or legacy detector was changed. No PHOTO transform, NBIS or SourceAFIS evaluation ran. The unchanged ridge validator is diagnostic only: macro IoU 0.0992, coverage 0/10. It neither gates nor modifies the primary candidates.

## Development correction and regression

The initial skeleton-path implementation gave macro IoU 0.6936 / coverage 9/10, but failed synthetic rotation and frame-truncation tests. Medial skeleton endpoints can stop before a real frame cut or terminate at boundary spurs. The correction uses the robust major-axis scanline centerline for longitudinal coordinates and actual component/frame intersection for truncation; skeleton endpoints remain available for inspection. Fixed extent/widening constants were not changed. Initial overlays and metrics remain private, separate from corrected results.

107 unit tests pass, including class-1-only truncated input, class-2 retention, rotation consistency, empty masks, tip/body subset and deterministic output. GT7 masks were identical on repeat estimation, and every predicted pixel remains within the semantic body. GT7 is development-only; these results do not establish general detection, anatomical boundary accuracy, fingerprint protection or independent final validation.

See [usage and policy](../docs/FINGER_BODY_DISTAL.md). Model source and weight remain external, as described in the COLFISPOOF raw evaluation guide. No private image, mask, GT or overlay is included here.
