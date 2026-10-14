# Coarse PHOTO experimental integration

This opt-in development path preserves the unapproved COLFISPOOF class 1+2 →
finger-body distal estimator. It does not use the rejected refinement model,
GT for inference, detector tuning, or matcher scores to select a renderer.
The default public PHOTO API is unchanged.

`PHOTO_DETECTOR_APPROVED=false` and
`PHOTO_PROTECTION_PRODUCTION_READY=false` remain mandatory.

## Coordinate and renderer contract

Semantic caches bind the input file SHA-256, encoded image dimensions and binary
PNG hashes. Coarse masks remain in encoded original coordinates and are subsets
of the finger-body mask. Each eligible component becomes a CanonicalFingerprintROI.
Native pitch metadata and observed working-image pitch are kept distinct.

EXIF orientation is an exact permutation. The experimental working canvas uses
one common isotropic scale derived from the median pad distance-transform
inscribed diameter, targeting 400 pixels, the existing structure check's width
normalization. Actual rounded working dimensions and scale are recorded.
This is an explicit input adaptation, not a change to the frozen renderer.
It is not proven equivalent to direct native-resolution rendering.

A deterministic interior seed supplies the unchanged observed-pitch routine.
The complete pad bbox is enclosed by a square scope; necessary right/bottom
padding uses edge pixels. No pad is cropped away and pitch is never clamped.
Unobserved pitch and working pitch outside 2..50 reject the component.

Unmodified natural_auto_04 + boundaryblend_02 produce the candidate, and the
existing width/minutiae/skeleton structure gate decides whether it is applied.
Scoped bindings are restored even on exceptions. Use this integration serially;
concurrent use of other globally bound historical renderer APIs is not supported.

After inverse resize and EXIF mapping, only successfully applied original pad
masks are composited into a copy of the original RGB. Failed pads and every pixel
outside the applied masks remain identical. This hard mask containment prevents
resampling from altering the background. It does not prove visual naturalness
at the mask boundary. Original JPG files are never written.

## Usage

Prepare SourceAFIS Java classes/JARs and the hash-verified NBIS runtime as described
in LINUX_SETUP.md. Keep all runtime files, semantic caches and images private.

Generate source-bound semantics with the isolated TensorFlow 2.10 environment:

```bash
/path/to/tensorflow-python ai/scripts/colfispoof_body_semantics.py \
  --input /path/to/input.jpg --output /path/to/private/semantics \
  --external-source /path/to/COLFISPOOF/pre-processing \
  --model /path/to/deeplab_model.tar.gz
```

Run the experimental consumer with the scientific Python environment:

```bash
export BLURFING_SOURCEAFIS_HOME=/path/to/sourceafis
export BLURFING_NBIS_LINUX_CONFIG=/path/to/nbis_runtime_linux.json
python ai/scripts/protect_photo_coarse_experimental.py \
  --input /path/to/input.jpg --semantics /path/to/private/semantics \
  --output /path/to/private/fresh-result
```

Output includes `returned.png`, binary native-coordinate pad PNGs and
`result.private.json` (source SHA, shape, mask SHA, exact working scope/scale,
pitch, rejection reasons, applied counts and native changed-pixel counts).
These outputs are private, including masks and JSON. This is a separate
experimental schema, not an automatic replacement of the legacy artifact API.
A semantic cache from another source/hash/dimension is rejected.

Run one warm-up and ten complete sequential runs with a persistent isolated
TensorFlow worker:

```bash
python ai/scripts/benchmark_photo_coarse_experimental.py \
  --input /path/to/input.jpg --output /path/to/private/fresh-benchmark \
  --tensorflow-python /path/to/tensorflow-python \
  --external-source /path/to/COLFISPOOF/pre-processing \
  --model /path/to/deeplab_model.tar.gz --repeats 10
```

The worker keeps model/runtime output off its JSON-line protocol. Benchmark
records genuine wall-clock end-to-end time, inference, IPC, combined coarse /
Canonical adapter, combined renderer / compositing / frozen structure gate,
matcher preparation and both matcher times. Internal renderer, compositing and
structure-gate timing are not separately instrumented; their combined time is
reported rather than invented. First runtime startup belongs to excluded warm-up.
Determinism compares coarse mask, native returned RGB and actual matcher inputs.

Matcher comparisons use identical existing Canonical 512px grayscale/letterbox
normalization on original and actual returned RGB, with the original native mask.
DPI remains the adapter's existing 500 default. This is a disclosed development
input contract, not an assumed physical scanner resolution. It differs from
historical seed-width-normalized structure-gate frames. Insufficient features or
zero scores do not establish privacy or matching resistance.

## Reproducible public-source tests

```bash
python -m unittest discover -s ai/scripts -p 'test_*.py'
```

The new synthetic tests cover EXIF permutation round trips, long-pad containment,
seed determinism, source RGB mismatch, exception restoration and strength zero.
Private development samples are not required for these tests.

The detector's GT7 macro IoU stays 0.7529, coverage 10/10. Neither these seven
already-used images nor this integration are independent holdout validation.
Remaining rejection cases and matcher limitations are preserved in the results.
