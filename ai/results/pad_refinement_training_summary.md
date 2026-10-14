# PHOTO pad refinement: prepared, training blocked

The specified ten human annotations all passed source/mask hashes, original shape, binary 0/255, nonempty mask and preview readability checks. TRN-008 and every other unlisted source were excluded. The six binary components in TRN-001 versus five polygons are reported unchanged; no annotation was repaired or converted into a negative.

The unchanged COLFISPOOF class 1+2 / finger-body distal v2 frontend generated proposals from source RGB only. Crops use proposal bbox plus fixed 35% context padding, aspect-preserving 256x256 letterbox, RGB+coarse channel and nearest-neighbor labels. GT enters only as supervised labels after boxes are fixed. There are 27 crops across all ten sources; none requires a GT-guided fallback. GT7 source SHA overlap is zero.

| Source | Annotation components | Coarse-guided crops |
|---|---:|---:|
| TRN-001 | 6 | 5 |
| TRN-002 | 5 | 2 |
| TRN-003 | 2 | 2 |
| TRN-004 | 1 | 1 |
| TRN-006 | 4 | 2 |
| TRN-010 | 5 | 5 |
| TRN-014 | 5 | 1 |
| TRN-016 | 3 | 3 |
| TRN-020 | 4 | 3 |
| TRN-022 | 3 | 3 |

## Mandatory pretrained blocker

The installed isolated PyTorch runtime is usable on CPU but CUDA is unavailable. The official MobileNetV3-small ImageNet checkpoint is not in local cache, and the attempted official download failed with `Could not resolve host: download.pytorch.org`. Actual training failed at the mandatory pretrained checkpoint check **before any optimizer step or fold training**. No random-initialized private-data training was substituted.

Architecture code: 4-channel MobileNetV3-small encoder and lightweight U-Net-style skip decoder, 1,203,441 total parameters / 276,865 trainable. RGB input weights are copied, coarse-channel weights initialized to zero. Other encoder weights and BatchNorm statistics are frozen; only input convolution and decoder train. Architecture/loss smoke tests use synthetic tensors and random weights solely to verify shapes, not to produce model-performance results.

## Fixed protocol, not executed

Seed 20261014; five source-disjoint folds with 8 train / 2 validation sources; BCE+Dice; 40 maximum epochs; patience 6; fixed threshold 0.5; final epoch count is median of five best epochs. Training-only augmentation includes rotations/flips, mild affine scale, brightness/contrast/saturation and mild blur/noise. Masks use nearest-neighbor interpolation. Validation reconstructs full original-coordinate predictions and clips to finger body, including GT areas missed by proposals in the denominator.

There are no CV scores, best epochs or final checkpoint SHA-256. GT7 refinement inference, overlays, benchmark and PHOTO downstream protection/matcher checks were not run. GT7 remains untouched as a one-shot final evaluation: it is not training, validation or early-stopping data. The planned split CSV has blank metrics rather than fabricated zero values.

## Regression

The main scientific-Python suite passed 110 tests, with three Torch-specific tests skipped there; all six refinement tests passed in the separate PyTorch environment. Python syntax passed. Scanner smoke matches previous returned pixels, changes 95,930 pixels and preserves exterior pixels. Frozen, scanner, legacy, COLFISPOOF runtime and matcher components were not modified. Checkpoint 303/303 and 55 capture hashes were checked separately.

Next required step: acquire the official pretrained encoder checkpoint, verify provenance/hash, then run the fixed five-fold protocol and one final training run. Only after that may the single GT7 refinement test be consumed. Do not change the protocol or re-train after observing GT7 results. No independent protection, Windows equivalence or project-completion claim follows from this preparation.
