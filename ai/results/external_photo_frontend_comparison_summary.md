# External PHOTO frontend comparison — acquisition blocked

No external candidate ran inference. No primary frontend was selected or integrated.
Missing predictions, scores, overlays and timing remain unavailable; they are not zero-score model failures.
MediaPipe is not a primary PHOTO detector. Existing algorithms and scanner behavior are preserved.

| Candidate | Official webpage | Local runtime | GT7 evaluation |
|---|---|---|---|
| MoBioFP object detector / U-Net / cascade | Supplied URL returned 404 | No official weight acquired | Not run |
| COLFISPOOF preprocessing | Visible | Source download blocked by DNS | Not run |
| RidgeFormer ISPFD preprocessing | Visible | Source and CLIP download blocked by DNS | Not run |

[COLFISPOOF](https://github.com/dasec/COLFISPOOF) documents own-fingerphoto preprocessing and requires publication acknowledgment. Its executable dependencies and redistribution permission were not verified.
[RidgeFormer](https://github.com/KNITPhoenix/Ridgeformer/tree/main/ISPFD_preprocessing) documents SAM + CLIP preprocessing. Its [license](https://github.com/KNITPhoenix/Ridgeformer/blob/main/LICENSE) is CC-BY-NC-4.0. Matcher checkpoints are not evidence of a dedicated pretrained fingertip detector.
The [supplied MoBioFP URL](https://github.com/rotiroti/mobiofp) was inaccessible through the web check. No mirror was substituted, and the claimed MIT license and weight filenames remain unverified.

## Existing GT7 comparison reference

The following numbers are previous legacy outputs, not newly executed external-model results.
All seven annotation files passed source hash, encoded-coordinate shape and binary mask checks; none declares ambiguous/non-target status.

| Sample | Legacy IoU | Coverage | FP | Miss | All external candidates |
|---|---:|---:|---:|---:|---|
| DET-01 | 0.9318 | 2/2 | 0 | 0 | Not evaluated |
| DET-03 | 0.0000 | 0/1 | 0 | 1 | Not evaluated |
| DET-04 | 0.9251 | 3/3 | 0 | 0 | Not evaluated |
| DET-05 | 0.9173 | 1/1 | 0 | 0 | Not evaluated |
| CAP-016 | 0.0000 | 0/1 | 1 | 1 | Not evaluated |
| CAP-042 | 0.0000 | 0/1 | 2 | 1 | Not evaluated |
| CAP-054 | 0.6645 | 1/1 | 1 | 0 | Not evaluated |

Legacy macro IoU: 0.4913; component coverage: 7/10; FP: 4; missed: 3.
There is no measured improvement or evidence for removal of wrist, keyboard or background false positives.
No domain-mismatch conclusion or training annotation minimum can be inferred without executing the models.

## Regression and preservation

93 existing unit tests passed. The unchanged scanner public API detected/transformed one public fixture, changed 95,930 pixels and preserved exterior pixels. Canonical captures and checkpoint were checked separately. The PHOTO protection path remains unapproved; no new PHOTO transform or matcher evaluation ran.

## Benchmark and next step

The requested warm-up plus ten-run comparison is not possible without acquired executable candidates. GPU driver access also failed. No inference timing is fabricated from DNS lookup time.
Restore access to official upstream sources and weights, then run upstream preprocessing on RGB inputs without GT, restore encoded original coordinates, evaluate raw and common-ridge-validated masks separately, and create private overlays. Use no sample-specific thresholds or fine-tuning on GT7. Model/source hashes and exact installed versions must be recorded after acquisition.

New detector adapters and heuristic substitutes were deliberately not introduced without a tested upstream implementation. No private images, masks, weights or external code were added to the repository.
