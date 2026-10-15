# Explicit observed-pose PHOTO experiment

`pose_v14` is an opt-in development experiment for a single full hand. It
addresses missed or merged learned permissions by using observed hand joints
and TIPs together with the existing COLFISPOOF semantic BODY. It is not a
production detector, an exact anatomical annotation or a privacy proof.
The default engine remains unchanged.

## Fixed observation and geometry

The isolated worker uses official MediaPipe Hand Landmarker in CPU IMAGE
mode, `num_hands=2` and the three existing 0.5 confidence defaults. The
consumer requires exactly one observed hand; two hands are rejected rather
than silently selecting the first. No confidence lowering or inference retry
is used. MediaPipe is pinned to 1.1.1 and the official task model SHA256 is
`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`.

Each thumb IP/TIP or finger DIP/TIP segment must have a finite positive
length and in-frame endpoints. Its midpoint and TIP must belong to semantic
BODY. BODY pixels are assigned to the nearest closed finite segment; exact
ties retain the fixed anatomical digit label. Each distal half-plane proposes
pixels within that owner. Only its 4-connected component containing its own
TIP is bound. All other proposed fragments remain explicit rejected
diagnostics; no largest-component or nearest-fragment substitution is used.

Normalized upright edge coordinates map to native pixel-center indices as
`normalized * upright_dimension - 0.5`, then through the inverse EXIF
transform. EXIF 1–8 are checked against actual PIL-transformed pixel-ID and
RGB rasters. Source shapes, decoded pixels, original bytes, model, worker
code, runtime and configuration are bound to the worker record.

Each digit's observed axis/owner and permission enter the existing V12
preparation and actual-native RGB decision gate. Pitch, feature, renderer and
compositor numeric criteria are unchanged. Existing base estimation still
runs, but its contexts have no role in the explicit pose candidate builder.
The report states this. Geometry failures return original RGB, while source
or semantic mutation cannot be hidden as a normal rejection.

## Configuration

Configure COLFISPOOF as before, plus an isolated hand worker Python and model:

```sh
export BLURFING_HAND_PYTHON=/private/hand-env/bin/python
export BLURFING_HAND_MODEL=/private/hand_landmarker.task
python ai/scripts/protect_fingerprint.py --input /private/full-hand.jpg \
  --output /private/fresh-pose-result --photo-engine pose_v14 \
  --consumed-registry /private/consumed_registry.private.json
```

Use the corresponding environment variables in Windows PowerShell. The
Windows GUI/launcher supports the same explicit engine. `--photo-model`
is invalid for pose V14: it uses no V6 pad model, but still needs the external
semantic and hand models. Strict consumed-source exclusion is the default;
explicit development replay never establishes independent validation.

The original-coordinate PNG/EXIF, actual partial/rejected outcome, unbound
fragments and private label/axis diagnostics are preserved. RGB outside
accepted permissions and rejected pixels must remain identical to source.
The public-source snapshot is checked before publishing a final result.

## Executed development diagnostics

The fixed geometry was generated without human GT before running the
existing gate on two related additional full-hand photos and one existing
training photo. New source/model inference was not repeated for this fixed
candidate diagnostic. The two additional photos changed from 2 and 3 applied
V6 permission components to 3 and 4 applied pose digits; the previously missed
thumb in the second photo was actually transformed. This is a change in
permission domains, not a claim of improved detector accuracy.

Actual NBIS and SourceAFIS evaluation used all fifteen fixed digit ROIs,
original self comparisons, saved V12 output and saved pose output. One newly
processed thumb's NBIS score changed from self 75 / V12 75 to pose 0; a newly
processed middle digit changed from self 42 / V12 42 to pose 3. Several
unprocessed usable originals retained the same positive score. Extraction
failure and insufficient original features were not counted as protection.

On the existing training annotation, fixed pose geometry had IoU 0.8495,
recall 0.9530 and precision 0.8867, compared with V6 IoU 0.8740, recall 0.9090
and precision 0.9577. The annotated sample was read only after geometry was
fixed; no fitting/tuning used these values. These are training diagnostics.

## Unresolved limits

- A connected wrong-neighbor bridge survives the TIP topology rule; a
  synthetic counterexample is retained in tests. Straight joint cuts also
  approximate a curved visible crease and semantic boundaries remain fallible.
- In a once-per-image development observation, the hand model detected three
  full hands among twenty photos and missed all seventeen single-finger/
  incomplete-hand views. It cannot replace the existing PHOTO detector.
- More complete permission geometry does not create missing pitch evidence.
  Some thumbs/little fingers and most digits of the existing training photo
  were still rejected. A no-hand result must not be reported as protection.
- Additional photos belong to an existing capture and have no new human
  whole-pad GT yet. Quantitative generalization, independent protection,
  Linux execution and deployed backend/Android behavior are not established
  by these Windows diagnostics.

## Final Windows integration verification

The completed source passed **606 AI-script tests** and **17 Windows GUI
tests**, with no failures, errors or skips. A fresh unified CLI invocation
on a related full-hand photo ran both COLFISPOOF and the hand worker, applied
four digit permissions and returned exactly the same full-resolution RGB
as the fixed-geometry diagnostic (maximum pixel difference zero). A second
fresh invocation on a single-finger photo observed no hand, rejected the
request and returned pixel-identical original RGB. Neither run selected
another engine after a rejection.

Both actual runs preserved original input, EXIF and the public-source
snapshot; their stdout parsed as a single JSON result. The existing V6
checkpoint also loaded successfully with its original sixteen training
source hashes and frozen protocol. These checks do not broaden the stated
accuracy, coverage or privacy claims. Existing actual Tk process/save
verification for native V12 is recorded in the
[desktop validation report](PHOTO_DESKTOP_VALIDATION_20261016.md).

Primary runtime references: [Hand Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python),
[Hand Landmarker overview](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker).
