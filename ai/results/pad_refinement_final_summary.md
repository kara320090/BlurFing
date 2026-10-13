# Refinement final training and one-shot GT7 test

The official MobileNetV3-small checkpoint full SHA-256 was verified: `047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f`. RGB encoder weights exactly matched pretrained values, the fourth channel was zero, and all other encoder tensors matched before training. The existing protocol was resumed unchanged on CPU. No GT7 label/image was used for training, validation, early stopping or final epoch choice.

## Source-level five-fold validation

| Fold | Best epoch | IoU | Dice | Precision | Recall | Leakage |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 0.5153 | 0.6790 | 0.7936 | 0.5977 | 0.2064 |
| 2 | 13 | 0.7035 | 0.8148 | 0.8894 | 0.7770 | 0.1106 |
| 3 | 3 | 0.6489 | 0.7633 | 0.7519 | 0.7836 | 0.2481 |
| 4 | 16 | 0.5368 | 0.6911 | 0.6180 | 0.8480 | 0.3820 |
| 5 | 30 | 0.6538 | 0.7834 | 0.8258 | 0.7459 | 0.1742 |

CV macro IoU 0.6116, Dice 0.7463. Best epochs 3/13/3/16/30 yield median **13**. One final model was trained on all ten sources for exactly 13 epochs; no extra model was trained after test. Final checkpoint SHA-256: `383ee3c4965305d14996368790d1384ba58bb768e5dc9bd1b26f3fe3cc0ed298`. Architecture, BCE+Dice, augmentation, threshold 0.5 and coarse frontend stayed fixed.

## One-shot final development test

The final checkpoint existed and was hash-verified before fresh COLFISPOOF inference on GT7. GT-free coarse/crop generation preceded refinement. GT labels were read only for scoring frozen predictions. A model-directory exclusive ledger records consumption of this version's final test; repeated forwards were only determinism and timing checks, with no selection/retraining.

| Sample | Coarse IoU | Refined IoU | Precision | Recall | Leakage | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.8989 | 0.6668 | 1.0000 | 0.6668 | 0.00% | 2/2 |
| DET-03 | 0.5946 | 0.1853 | 1.0000 | 0.1853 | 0.00% | 0/1 |
| DET-04 | 0.7938 | 0.3072 | 1.0000 | 0.3072 | 0.00% | 0/3 |
| DET-05 | 0.6586 | 0.2178 | 1.0000 | 0.2178 | 0.00% | 0/1 |
| CAP-016 | 0.6649 | 0.4725 | 0.7888 | 0.5410 | 21.12% | 0/1 |
| CAP-042 | 0.7804 | 0.4491 | 1.0000 | 0.4491 | 0.00% | 0/1 |
| CAP-054 | 0.8789 | 0.6055 | 0.9999 | 0.6056 | 0.01% | 1/1 |

**Model rejected.** Macro IoU falls from 0.7529 to 0.4149, component coverage from 10/10 to 3/10. Unmatched prediction components: 14; missed GT components: 7, under the unchanged IoU>=0.5 one-to-one matching rule. Private overlays show severe undercoverage and fragmentation inside true fingers, rather than a new large wrist/keyboard/background region. CAP-016 leakage decreases from 28.92% to 21.12%, but recall falls from 91.14% to 54.10%; this is not a successful refinement.

Every refined pixel remains inside the original semantic body. All seven repeated inference mask hashes match. These safety/determinism checks do not negate poor segmentation performance. The coarse detector remains preserved; no refinement adapter was adopted and no PHOTO transform, NBIS or SourceAFIS downstream run occurred.

## CPU detector-only benchmark

Warm-up one, measured ten, fixed representative DET-01. Each environment's runtime is loaded once. Timings below are a staged sum across isolated TensorFlow/scientific-Python/PyTorch runtimes; crop serialization is included. Graph/model loading, source decode and protection are excluded, so this is not a complete protection end-to-end benchmark.

| Stage | Mean s | Median s | p95 s |
|---|---:|---:|---:|
| COLFISPOOF | 2.1086 | 2.0732 | 2.3705 |
| coarse_and_crop | 0.1576 | 0.1562 | 0.1635 |
| refinement | 0.0439 | 0.0442 | 0.0475 |
| detector_staged_total | 2.3102 | 2.2734 | 2.5691 |

## Regression and next blocker

Core regression tests and isolated Torch tests pass; Python syntax passes. Scanner public-fixture smoke returns pixels identical to the prior result, changes 95,930 pixels and preserves exterior pixels. Checkpoint303/captures55/frozen/legacy/runtime/private GT and unrelated user changes were checked separately.

The blocker is refinement generalization/recall on this small ten-image training set, with low validation scores and fragmentary test masks. No architecture/epoch/threshold/loss adjustment is made from GT7. Any next model experiment needs an independently fixed training/validation plan and a fresh final test strategy; GT7 has now been consumed for this version and must not become training data or a tuning target. These development results do not establish fingerprint protection or independent final validation. Weights, sources, GT, crops and overlays remain private.
