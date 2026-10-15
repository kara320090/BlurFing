# Whole-body context plus local detail: V6 development ablation

The V4 label update and V5 class-balanced objective do not establish improved
whole-pad detection. The independent local tile model lacks an explicit view
of the whole finger and its first crease. V6 adds a separate context stream;
V3/V4/V5 checkpoints, default PHOTO/GUI paths and protection math are preserved.

## Input and feature geometry

Local inputs retain the existing GT-free native512-to-256 RGB/coarse tiles.
Global context uses only the nonempty observed body union bbox in encoded
original coordinates. Human masks never determine its crop. The existing
INTER_AREA 256 letterbox supplies actual rounded x/y dimensions and padding.
Only normalized RGB enters a separate official MobileNetV3-small encoder,
which stays fully frozen with BatchNorm in evaluation mode.

Stages 3/8/12 provide 24/48/576 channels at strides 8/16/32. Each is explicitly
border-resampled onto the stage-3 convolution lattice, input-edge anchor
`0.5 + 8*i`. Ordinary size-only interpolation would shift these different
feature lattices. These anchors do not imply point-local receptive fields:
deep convolution and SE intentionally carry context from the whole image.

A trainable 648-to-16 projection is sampled into the local tile and fused with
the local decoder's 16 channels and coarse channel before the new head.
Mapping uses native pixel centers, the rounded axis-specific letterbox scales,
and the declared context lattice. Feature boundaries use explicit border
extension. Local source validity remains separate from feature-center bounds.

Global context remains an identity reference. Local RGB/coarse/label and the
coordinate/validity fields receive the same historical rot90, flips and affine
geometry in the same random draw order. Only local RGB receives historical
photometric/noise augmentation. Partially supported affine/padding coordinates
reject; a float32 roundoff bound is fixed from synthetic arithmetic, not GT.
Validity is applied after projection and sampling so learned affine terms cannot
revive invalid locations. Context is a detector input, not independent biometric
evidence. Downstream V10 component-local pitch/renderer checks are preserved.

## Frozen experiment and verification

V6 returns to V4's unweighted BCE+Dice objective. Local input-convolution and
decoder learning rates, source weighting, augmentation, seed, batch size, group
splits, patience/max epochs, threshold 0.5 and median final-epoch rule stay fixed.
Every fold starts from fresh official weights. Context and model capacity both
change; this comparison does not isolate context as the sole causal factor.
Probability calibration and unchanged effective decision boundaries are not
claimed.

The local augmentation function is exact against the old implementation under
matching RNG states. Extra model initialization consumes random numbers, so
the actual noise realizations across different architectures need not match.

GT-free context features are cached from the same official encoder snapshot
before fold seeds are reset. Cache/checkpoint encoder identities, source/body,
RGB context, tile grids, protocol, code and original assets remain hash-bound,
including after final checkpoint save. Context features need 2,654,208 bytes
per source; separate feature and combined raw-cache bounds run before allocation.
Those planning bounds do not measure total process RSS.

Synthetic checks cover non-square rounded geometry, half-pixel mapping, all
rotations/flips and affine extremes, aligned stage coordinate ramps, exact
historical local augmentation/RNG, GT-view rejection, cache mutation, invalid
context zeros, actual projection gradients, frozen parameters/BN, optimizer
membership, finite state and save/load equality. The strict inference loader
rejects old/incomplete configs and mismatched context encoders.

```powershell
python ai/scripts/train_whole_pad_context_v6.py --dataset <private-V4-dataset> --encoder-weights <official-weights> --output <fresh-private-model>
python ai/scripts/infer_whole_pad_context_v6.py --model <private-V6-model> --inputs <GT-free-V3-input-folder> --output <fresh-private-predictions>
```

Adding `--protect` to the second command explicitly runs experimental V10
observation and unchanged frozen protection. It is not enabled in existing GUI
or unified defaults. All model weights, source images, annotations and per-image
outputs remain private.

`protect_photo_whole_pad_context_v4.py` is the separate single-photo entry:

```powershell
python ai/scripts/protect_photo_whole_pad_context_v4.py --input <photo> --model <private-V6-model> --consumed-registry <private-registry.json> --output <fresh-private-output>
```

It uses the configured COLFISPOOF worker, V6 GT-free context detection and V10
observation. Original encoded EXIF coordinates, explicit RGB/L/RGBA input
handling, source-bound semantics, fresh outputs and JSON stdout remain checked.

The 23 sources still form only three conservative development groups. The new
13-photo cohort is consumed development data with person/acquisition independence
unverified. Report OOF early-stopping scores separately from final training fit
and actual returned RGB. Body omissions and unobservable pitch/features remain
limitations. Production detection, complete-photo protection and new Linux
runtime validation remain unapproved.

All ten legacy GT previews were also inspected. They broadly mark visible pads;
no obvious rotation/overlay fault or confirmed policy contradiction was found.
Their exact crease/ambiguity policy remains undocumented. This is not evidence
that incorrect human labels caused the regression, and legacy GT is preserved.

## Completed learning checks

Fold best epochs are 4, 1 and 12, giving four final epochs. OOF source-macro IoU
is 0.483604 and equal-group IoU is 0.470537, versus V4's 0.552743 and 0.500480.
Legacy/new-policy OOF IoU is 0.455595/0.505149. These are developmental
early-stopping scores, including a new-cohort fold trained only on legacy ten.
The context experiment does not establish improved group generalization.

Final all-source training-fit IoU is 0.824281; legacy ten score 0.728937 and
new whole-pad thirteen score 0.897622. Improved fit must not be reported as
unseen-photo performance. Full-cohort cached forward equals isolated-source
forward and saved masks on two fixed sources. Final checkpoint audit confirms
all 38 trainable parameters changed, complete unique optimizer membership,
unchanged frozen encoder/BatchNorm states, finite tensors, the median epoch
rule and all code/model/manifest/context bindings. All 1,478 bound private assets
remain unchanged. Actual returned-RGB protection is evaluated separately.

## Actual returned RGB on the consumed thirteen

All thirteen complete the V10 evaluation. Eight have changed RGB; five return
the original unchanged. With the complete human GT as denominator, permission
covers 90.15%, accepted regions cover 52.43%, and changed RGB covers 49.53%.
The last quantity is a pixel-change diagnostic, not a security success rate.
There are 15,680 changed pixels outside human GT. All C-subset-A-subset-P,
rejected-pixel and permission-exterior preservation checks pass.

| Final training-cohort replay | Photos with changed RGB | Changed GT area | Changed outside GT |
| --- | ---: | ---: | ---: |
| V4 plus V10 | 6/13 | 18.35% | 646 pixels |
| V5 plus V10 | 9/13 | 56.57% | 798,901 pixels |
| V6 plus V10 | 8/13 | 49.53% | 15,680 pixels |

All three models trained on this cohort. V6 reduces V5's extensive overgrowth
and changes more GT area than V4, but it does not dominate V4 on exterior-to-GT
changes. The human GT boundary is not an independent certification of every
false-positive pixel. This comparison is consumed-development training fit,
and the weaker grouped score prevents an improved-default generalization claim.

Four unchanged photos have dominant component-local unobserved-pitch rejection;
the fifth has dominant insufficient-feature rejection. Small unowned/seedless
fragments and one adapter memory-limit rejection also remain. Region counts
include fragments and must not be presented as actual finger counts. Better
detector fit does not automatically satisfy the unchanged transform contracts.
No pitch, feature or detector threshold was relaxed to force acceptance.

The two-worker evaluation uses process-isolated renderer state and unique source
outputs, with parent-only aggregates in fixed acquisition order. It is not a
latency benchmark. An actual single-photo CLI and Windows PowerShell launcher,
including a fresh COLFISPOOF worker and a Unicode/space input path, exactly match
the cached batch mask and returned RGB on one fixed source. Original bytes,
EXIF and GT-free inputs are preserved. The full AI suite passes 481 tests, with
four additional context-entry tests; Android merge validation passes 136 tests
and builds application/test APKs. Device instrumentation and new Linux runtime
equivalence were not rerun here.

Complete anonymous metrics are in
[the V6 status](PHOTO_WHOLE_PAD_CONTEXT_V6_STATUS.json). V6 remains opt-in,
unapproved and outside existing defaults. Further independent validation needs
untouched acquisition groups, consistent human whole-pad labels and a frozen
model/preprocessing protocol before their first evaluation.
