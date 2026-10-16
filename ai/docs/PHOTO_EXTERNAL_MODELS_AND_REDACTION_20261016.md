# External models and explicit pitch-free redaction — 2026-10-16

The existing model, GUI/API defaults, renderer mathematics and numeric gates
are unchanged. A separate experimental command can visibly black out predicted
pad pixels without measuring ridge spacing. Its mask coverage is unverified;
it does not make the current PHOTO system production-ready.

Follow-up: [isolated finger completion](PHOTO_ISOLATED_PAD_COMPLETION_20261016.md)
records a second SAM prompt comparison and an optional COLFISPOOF-derived
completion policy for fragmented single-finger masks.

## Actual external-model comparison

No fine-tuning was performed. Source RGB, checkpoints, semantic masks and
human GT were preserved. The seven additional photos are related development
images from an existing capture. Their human boundary review remains deferred.
All comparison prompts were made without GT; existing GT was used only for
metrics after inference. The 13 annotated comparison photos were already part
of V6 training, so these are training-fit diagnostics, not independent results.

### SAM 2.1

The official [SAM 2 repository](https://github.com/facebookresearch/sam2) was
pinned at `2b90b9f5ceec907a1c18123530e92e794ad901a4`. Hiera tiny checkpoint
SHA256: `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`.
The official code/checkpoints use Apache 2.0; neither is redistributed here.
Inference ran on CPU in an isolated environment using an existing read-only
Torch installation. Model hashing was streamed separately from the image
asset-size contract; no image safety limit was relaxed for the larger model.

All 20 photos received one image embedding and automatic coarse-pad prompts:
one deepest interior positive point, one proximal-owner negative if available,
and the pad box expanded by 25% in each direction. A single output mask was
intersected with the same observed owner, retaining all resulting components.
No hole filling, sprinkle removal, GT prompt or per-photo adjustment was used.

| Same 13 training-fit photos | Micro IoU | Macro image IoU |
|---|---:|---:|
| Existing V6 | 0.8804017103 | 0.8976219455 |
| SAM 2.1, this fixed prompt protocol | 0.5909366565 | 0.7056460964 |

This SAM configuration is rejected as a default replacement. The comparison
does not establish that other SAM checkpoints/prompts cannot work, or that V6
generalizes better to independent photographs. SAM still needs semantic
guidance to distinguish the pad from the rest of a finger.

### FingerNet orientation and raw-profile spacing

The third-party [PyTorch port](https://github.com/JF235/FingerNet) was pinned
at `3e394d220e09652be944ed3e46e855256c6e6e53`. Its provided state dictionary
loaded strictly: 209 tensors, SHA256
`47474fae8a74aa720b159f6c6c182dae0b6dc629834b7e7b3858e3149ab63682`.
Code and weights stay private to the isolated research runtime. The port
refers licensing to the original project; redistribution rights and original
TensorFlow/PyTorch numeric equivalence were not established here.

Twelve synthetic orientation controls used periods 8/16 and six known angles.
The published angle convention was checked without selecting a sign from real
photos. Error reached 45 degrees in one period-16 control, demonstrating that
network orientation is not automatically trustworthy outside its training
conditions. No Gabor-enhanced/generated image was used to measure spacing.

`photo_raw_profile_pitch_v2.py` is a diagnostic observer that samples the
supplied raw image at seven rates, records sampling-unit conversion, checks
ACF against FFT bins, requires six distinct centers per usable rate, and
requires at least two rates to agree. Downsampling uses explicit anti-aliasing;
its finite sampling/filter support must be inside permission. Orientation can
use surrounding context and is not claimed context-independent. Shared-profile
FFT/ACF and multiple sampling rates are not independent biometric evidence.
There is no default pitch and no connection to the frozen renderer gate.

All valid coarse candidates across the seven photos plus one previously
investigated development case were examined: 19 candidates across eight
images. One candidate produced additional raw-profile periodicity using the
FingerNet reference. The two existing unchanged photos remained unobserved.
Real pitch GT is unavailable, so that candidate is not certified ridge spacing.
The legacy observer returned no period in these broad coarse-square ROIs;
this does not describe its success on the different, smaller observation seeds
used by the complete existing pipeline.

Synthetic tests cover short and long periods (including 3.2 and 26.4 image
pixels), oblique/rotated coordinates, flat/noise rejection, support and input
preservation. Such controls do not substitute for real-photo pitch validation.

## Explicit alternative when spacing is unavailable

`photo_pitch_free_redaction_v1.py` writes constant black RGB inside a hash-bound
boolean mask and preserves every exterior RGB pixel. For a fixed mask, changing
the original masked RGB cannot change the returned image. This is a local
pixel-removal property; it does not prove complete anatomical mask coverage.

`protect_photo_pitch_free_v1.py` connects source decoding, configured
COLFISPOOF semantics and the unchanged V6 checkpoint to that separate method:

```sh
python ai/scripts/protect_photo_pitch_free_v1.py --input photo.jpg --model private/model --consumed-registry private/registry.json --output fresh-result
```

Runtime configuration follows the existing native PHOTO entrypoint. Strict
consumed-input checks remain the default; `--development-replay` explicitly
allows retests and never creates independent evaluation data. Source RGB/L and
RGBA-over-white decoding, encoded EXIF coordinates, source ICC/orientation in
the final opaque RGB PNG, fresh output, source hashing and runtime-source
snapshot checks are reused. The original file is preserved. `redacted_mask.png`
is saved beside the image and private report.

The default detector for this new command is V6 only. The explicit
`--include-observed-pose` option unions an existing observed TIP-connected BODY
proposal when exactly one valid hand is observed. No-hand results retain V6;
invalid worker contracts fail instead of inventing landmarks. This option may
cover extra skin/background and remains unreviewed. It is not enabled in the
existing appearance-preserving renderer, desktop engine or HTTP API.

The pose model found one hand in 3/20 comparison photos. On the 13 training-fit
photos, union changed pixel recall 0.9014531413 -> 0.9083715273 and micro IoU
0.8804017103 -> 0.8749107235. This is a coverage/precision tradeoff, not an
unconditional accuracy improvement or an approved default detector.

## Actual outputs and matching

All seven photos produced visibly redacted copies in both explicit mask
policies. These batch renders reused hash-bound existing V6 predictions; fresh
COLFISPOOF/V6 inference was separately exercised through the actual launcher
on a previously unchanged single-finger image and a full hand. The wider run
also executed the actual hand model. Returned RGB matched the corresponding
cached batch results exactly. Original bytes and all exterior pixels were
preserved; 627 protected original files and the old checkpoint/config were
rechecked unchanged. A Windows PowerShell CMD-launcher run was also exercised.

Seven nonempty redaction outputs do **not** mean seven fully protected photos.
Visual inspection still shows incomplete boundaries and false-positive pieces
in predicted masks. The new method handles spacing failure by changing the
protection method, while detection errors remain visible and unapproved.

Actual NBIS and SourceAFIS evaluation used all 26 pre-existing fixed ROIs:
the earlier 16 coarse ROIs and 10 digit ROIs from two full hands. Each engine
processed 78 images and 78 comparisons (original, V6-only redaction and wider
redaction), with no ROI selection based on new scores or output masks.
Residual positive NBIS comparisons remained in four ROIs, including 104 versus
original self 379; SourceAFIS retained a 0.7153 comparison in one ROI versus
original self 1177.954. No matcher acceptance threshold was introduced.
Failed extraction, insufficient original features and score zero are retained
as limitations, not counted as protection success.

The separate status is `redacted_unverified_scope`, or
`no_mask_original_returned`. Reports keep `whole_photo_protection_verified`
and `privacy_validated` false. The existing natural renderer's success flags
and feature gates are not reused to label black redaction.

## Verification and remaining evidence

Windows: **705 AI tests passed**, including 12 new observer/redaction/entrypoint
contracts. The isolated external-model environment passed `pip check`.
Ubuntu Python 3.10 and 3.11 each passed the **48 synthetic reference checks and
40 focused tests** at source commit `af5a49c2fb86769cac580f313e4888cf7059e97e`:
[verified actual Linux run](https://github.com/kara320090/BlurFing/actions/runs/38837891743).
The exact commit and both jobs' test-step conclusions were checked through the
public GitHub API. The hosted jobs use no private photographs or model weights.
Full model parity, independent accuracy and general privacy performance remain
unverified.

Next evidence is human-reviewed complete pad boundaries for the additional
photos, independent capture groups and real spacing reference data. A new
anatomical detector or automatic natural-renderer pitch fallback should not be
approved from these related development observations alone.
