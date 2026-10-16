# Isolated finger completion — 2026-10-16

The reported fragmented black output was caused by incomplete V6 permission,
not by the black renderer or a pitch rejection. In that exact decoded input,
V6 retained 146,751 pixels while the existing COLFISPOOF-derived coarse pad
contained 508,594 pixels. The external body detector had already found the
finger. A hand landmark model returned no single hand for this close-up.

## External model decision

The pinned official [SAM 2.1](https://github.com/facebookresearch/sam2) Hiera
tiny runtime from the prior experiment was tested on 21 images: 13 existing
training-fit GT photos, seven related development photos and the reported
consumed input. No retraining, GT prompts, per-image thresholds or retries
were used. The fixed prior point/box protocol was supplemented with a coarse
mask resized nearest to 256 by 256 and mapped to logits -6/+6. Each single
SAM proposal was intersected with its observed owner and unioned with V6.

On the same 13 training-fit photos:

| Mask policy | Micro IoU | Pixel recall |
|---|---:|---:|
| V6 | 0.880402 | 0.901453 |
| V6 + dense-prompt SAM | 0.725716 | 0.915851 |
| V6 + all coarse pads | 0.728649 | 0.907667 |

SAM did not justify replacement or automatic adoption. Unrestricted coarse
union also produced severe excess palm coverage on a multi-finger photograph.
Both policies were rejected for the launcher. This is a comparison of these
specific protocols on previously consumed data, not an independent ranking
of the models.

## Delivered optional completion

`protect_photo_pitch_free_v1.py --include-coarse-pad` now uses
`photo_isolated_coarse_completion_v1.py`. It requires all of the following:

- Exactly one valid estimator candidate and one native body component.
- That candidate owns the entire native observed body.
- The body intersects the image frame, while its coarse distal pad does not.
- The supplied coarse mask exactly matches the unchanged estimator result.

Eligible inputs keep the union of V6 and that coarse pad. Ineligible geometry
keeps the existing mask. Invalid mask contracts fail. The optional observed
pose union can then run as before. Existing learned pixels are never removed;
no morphological filling, synthetic landmarks or numeric gate tuning occurs.
The policy can still cover extra skin, miss other fingers, or choose an
incorrect proximal boundary. It does not establish the fingertip joint.

The default flag remains false. The local coverage launcher enables both
isolated completion and the existing observed-pose option. Appearance-preserving
renderers and GUI/API defaults are not changed. This remains visible solid
black redaction with `redacted_unverified_scope`, not natural ridge replacement.

The final policy was applied to the same complete 21-image roster. Relative
to the existing wider pose option, the 13-photo training-fit micro IoU changed
0.874911 → 0.869604 and recall 0.908372 → 0.909848. The modest recall increase
comes with lower precision, so the policy is an explicit option, not an
approved accuracy upgrade. No new human GT or independent capture was created.

For the reported input, the returned mask increased from 146,751 to 508,604
pixels and the fragmented coarse interior was covered. Remaining skin outside
the proposal is not certified fingerprint-free. On the multi-finger regression
case the new geometry check retains the previous wider mask instead of adding
the rejected palm expansion.

## Verification

Synthetic contracts cover an isolated fragmented pad, multiple fingers,
absence of a proximal frame cut, quarter turns, hash-bound coarse agreement,
invalid masks, and preservation of learned/input pixels. Actual returned PNGs
are checked for black RGB inside permission, exact exterior preservation and
EXIF/ICC round-trip. The same decoded reported input and a full hand are also
run through the real Windows CMD → PowerShell → COLFISPOOF/V6/hand entrypoint.
No matcher zero score or extraction failure is interpreted as protection proof.

Windows: **710 AI tests passed**. Both fresh CMD runs exactly matched their
cached comparison RGB and masks. The existing wider mode reproduced the
reported 146,751-pixel output exactly when the new flag was absent. All 627
protected originals and the V6 checkpoint/config remained unchanged.

Ubuntu Python 3.10 and 3.11 each passed **48 synthetic reference checks and
45 focused tests** at `093d23e3c1c57c66ad1be0eb6d3e23f0ebef05f3`:
[verified hosted run](https://github.com/kara320090/BlurFing/actions/runs/38852979931).
The exact commit, both jobs and their test steps were checked through the
public GitHub API. Full private-model Linux parity remains unverified.
