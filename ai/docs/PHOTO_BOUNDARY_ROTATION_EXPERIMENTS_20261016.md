# Boundary association and rotation experiments — 2026-10-16

These are opt-in development tools, not a replacement for the current model,
desktop/API engine, quality gates or frozen protection math. No detection,
pitch, feature, matcher or probability threshold was changed. Private photos,
predictions, probabilities, ground truth and model weights remain outside Git.

## Unique adjacent owner experiment

`photo_owner_boundary_repair_v2.py` considers connected predicted permission
pieces that have no observed owner. A piece is associated only when its
four-neighbor rim touches exactly one valid original observed owner and also
touches that owner's already-owned permission. All decisions use the original
ownership plane simultaneously. Multiple/overlapping/invalid owners, isolated
pieces and resource-limit cases remain unassigned. No predicted pixel is added
or deleted, and the original observed axis is retained. This is an inferred
association, not verified anatomical ownership.

`photo_learned_pad_pipeline_v15.py` connects that experiment to the unchanged
V12 final-returned-RGB gate. Each connected permission still needs its own
evidence; rejected and exterior pixels remain exactly original. The adapter
does not enable a new GUI/API/default engine.

All seven related development photos were checked for partition coverage. Two
fragmented cases changed from 64 candidates each to 8 and 17. Actual protection
was rerun on those two cases with their existing hash-bound V6 predictions:

| Development case | V12 applied components | V15 applied components | V15 changed RGB pixels |
|---|---:|---:|---:|
| A | 2 | 2 | 128,031 |
| B | 3 | 4 | 234,381 |

These are component counts, not finger counts. The other five cases retained
their partition geometry; their protection was not needlessly rerun. Prediction
pixels, original files and checkpoint were preserved. No new human GT was
created. The two unchanged pitch-rejected photos remain unresolved.

Actual NBIS and SourceAFIS evaluation used all ten pre-existing fixed pose
ROIs across the two photos, including unchanged and low-feature originals:
30 images and 30 comparisons per engine. ROI definitions were not selected by
the new outputs, scores or GT. Matching did **not** consistently improve:
one newly changed ROI retained an NBIS score of 64 before and after; another
changed from V12 385 to V15 393 (original self 1028), whereas one improved
37 to 17. Some originals did not have enough features for useful comparison.
Failed extraction, zero scores and changed pixels are not protection proof.
Accordingly V15 remains an unapproved association experiment, not a solution
to whole-pad coverage or privacy. Missing V6 pad predictions, including a
missed thumb, cannot be repaired by owner association alone.

## Rotation and resize

`photo_pixel_cell_support_v1.py` uses positive-area overlap of integer pixel
cells to produce a boolean support envelope. Synthetic rectangular rotations,
reflections and round trips preserve their stated contracts. An envelope is
not transform permission; it may expand support. Existing V6 preprocessing
is unchanged because applying a new resize policy to an old checkpoint would
change its input contract.

`photo_rotation_orbit_v1.py` restores four full view probabilities, sorts them
per pixel, averages in float64 and returns float32. This stabilizes cyclic
reduction order. Quarter-turn consistency assumes deterministic identical-input
view inference; shared-view reduction checks do not replace independent
four-view inference in a second frame.

The existing 13 human-reviewed **training** cases each received four fresh V6
views. GT was loaded only after inference for metrics, not model inputs:

| Metric | Original view V6 | Four-view mean |
|---|---:|---:|
| Micro IoU | 0.8804017103 | 0.7828752648 |
| Macro image IoU | 0.8976219455 | 0.8159180691 |
| False-negative pixels | 376,232 | 720,691 |

Only 1/13 image IoUs improved. The original-view baseline reproduced the
existing fit metric. The ensemble is **rejected for default adoption**; no
post-result threshold tuning or retraining was performed. These training-fit
results are not an independent accuracy estimate. Rotation consistency alone
does not establish correct detection.

## Pitch reliability diagnostics

`photo_pitch_spectrum_diagnostic_v1.py` detrends and scales a supplied 1-D
profile, applies a Hann window and reports a discrete FFT peak alongside an
optional existing candidate period. It exposes possible harmonic disagreement
without producing a replacement pitch or changing a gate. A dominant peak
can itself be a harmonic; FFT/ACF from one profile are not independent
biometric evidence. Synthetic tests include known periods, short-period
aliasing, brightness/polarity/trend changes, flat inputs, strong harmonics and
extreme finite amplitudes. These diagnostics do not solve the real photos'
unobserved-pitch failures.

## Portable reference and validation scope

From the repository root, with NumPy and SciPy available:

```sh
python ai/scripts/verify_photo_geometry_portable_v1.py --compare ai/config/portable_photo_geometry_reference_v1.json --output /tmp/blurfing-geometry-fresh.json
```

The output must be fresh; choose another name if it exists. The reference
contains synthetic geometry/reduction hashes and spectral bins only. All 48
invariant checks matched in two Windows environments (Python 3.11 and 3.10,
with different NumPy versions). This is not a Linux, CNN, renderer, scanner or
privacy equivalence claim. No usable Linux runtime/verified remote endpoint
was available in this Windows session, so actual Linux execution remains
pending.

New focused tests: 28 passed, covering owner ambiguity, mutation, partition
pixel conservation, V15 rollback/detect-only/input contracts, rotation and
spectral diagnostics. The final Windows AI suite passed **693 tests**. A first
run correctly caught a concurrent edit to the new portable tool; the full run
passed after all source edits ended. The 627 protected original files were
rechecked unchanged, including seven originals at their relocated paths.

The `PHOTO synthetic geometry contracts` workflow uses public synthetic data
only on Ubuntu with Python 3.10 and 3.11. It repeats the 48 reference checks
and 28 focused tests without model weights, human GT, private pictures or
matcher runtimes. Adding the workflow alone is not evidence of Linux success;
the actual run conclusion and commit must be verified separately.

Further algorithm adoption requires verified complete pad boundaries, suitable
development data and an independent capture-group evaluation. The seven new
photos are additional images from an existing capture; their human boundary
review remains deferred. No machine prediction is promoted to human GT, and
no general PHOTO protection approval is claimed.
