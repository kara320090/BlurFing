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
