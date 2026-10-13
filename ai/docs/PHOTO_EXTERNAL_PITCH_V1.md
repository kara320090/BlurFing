# External observed pitch v1 — opt-in experiment

This version adds an explicit evidence contract without changing frozen v4,
natural_auto_04, boundaryblend_02, the coarse detector or either matcher.
It never patches v4's observed_seed_pitch. Production/default inference remains
unchanged and unapproved. No GT is used in inference or threshold selection.

## Renderer identity

The experimental entrypoint calls the existing **whole_pad_skin_relief**
low-level renderer. Its original function code object and numerical helpers are
reused with a private globals dictionary containing only a source-checked scope
provider. No global renderer binding is modified. The existing width and
SourceAFIS/skeleton structure gates remain mandatory.

This is NOT natural_auto_04/boundaryblend_02 output equivalence. Those variants
remain frozen and their nested render implementations are not exposed as a
public external-pitch API. This experiment must not replace either baseline.

## ExternalPitchEvidence

Required information includes pitch_value, pitch_unit (`pixels`),
coordinate_space (`native_source_pixels` or `normalized_working_pixels`),
image_scale, orientation_deg, observer_name/version, patch counts, cue results,
agreement_result, evidence_hash and source_image_sha256. Additional bindings are
schema_version (`external-pitch-v1`), observed grayscale pixel SHA, mask pixel SHA
and image_shape. Native source coordinates use scale 1. Working scale is the
existing deterministic coarse adapter's geometric scale; actual image dimensions
are recorded in the consumer audit. This is pixel spacing, not known physical DPI.

The consumer recomputes source/mask/shape/pixel/hash and cue-consistency checks.
Accepted patch counts, median cue values and relative IQR must agree with the
actual stored patch records. SHA provides integrity, not authentication or proof
that an arbitrary malicious producer measured a real fingerprint. Use the
included local observer as the trusted producer. Evidence and masks are private.

For example, an accepted evidence payload has this structure (hash placeholders
and omitted patch records mean this illustration is not a runnable payload):

```json
{
  "schema_version": "external-pitch-v1",
  "pitch_value": 10.0809390231205,
  "pitch_unit": "pixels",
  "coordinate_space": "normalized_working_pixels",
  "image_scale": 0.2043982042300348,
  "orientation_deg": "measured local-normal axial mean",
  "observer_name": "acf_fft_ridge_patches",
  "observer_version": "1.0",
  "patch_count": "tested mask-supported locations",
  "accepted_patch_count": 10,
  "cue_results": {
    "autocorrelation": {"valid": true, "pitch": 10.054616270179395},
    "fft": {"valid": true, "pitch": 10.107261776061605},
    "patches": "actual numeric patch records required"
  },
  "agreement_result": {
    "passed": true,
    "orientation_consistent": true,
    "relative_IQR": 0.05947573502607471
  },
  "evidence_status": "accepted",
  "source_image_sha256": "<source-file SHA256>",
  "observed_image_pixel_sha256": "<observed grayscale SHA256>",
  "mask_pixel_sha256": "<mask pixel SHA256>",
  "image_shape": ["working height", "working width"],
  "evidence_hash": "<canonical payload SHA256>"
}
```

Statuses: accepted, insufficient_patches, cue_disagreement, no_periodicity,
unstable_orientation. Confidence is not represented as an invented probability.

## Rules fixed before photo diagnostics

Local 128px ridge-normal profiles are sampled on a deterministic 64px grid.
Structure-tensor orientation normalizes each patch; at least 95% mask support,
coherence >=0.65 and contrast >=2 are required. These support/coherence/contrast
criteria and six-patch minimum follow the existing frozen ridge estimator.

Autocorrelation uses the first credible periodic peak: correlation >=0.6,
prominence >=0.15. FFT uses a Hann-windowed spectral peak with quadratic log
interpolation; the peak and its adjacent bins must contain >=50% in-band energy.
The majority-energy FFT rule is a new, predeclared experimental rule, not a
literature-proven classifier or a threshold fitted on GT7. Synthetic periodic,
flat and contract rejection tests precede photo diagnostics.

At least six patches must satisfy both cues, <=15% relative cue disagreement,
and <=15% cross-patch relative IQR. The IQR rule follows existing frozen partial
pitch agreement. Orientation consistency is local tensor coherence for every
accepted patch; curved ridges need not share one global direction.

ACF and FFT are distinct estimators of the same image-derived profile. They are
not statistically independent evidence; agreement does not establish biological
fingerprint identity, particularly on textured backgrounds. No GT7 threshold,
loss, epoch, detector or renderer tuning was performed.

## Coordinate conversion and gates

`source pitch = measured working pitch / image_scale`.
The renderer operates on the explicitly recorded working image and receives the
measured working pitch. Both measured and converted source pitch must be finite
and within the existing 2..50 pixel range. This conservative rule rejects rather
than clamps. Audit records measured space/scale, pitch_native, pitch_renderer and
`silent_clamp=false`. Unknown pitch remains unknown.

A coarse pad stays inside the source-bound finger-body mask. Complete square
scope must fit the working canvas; unsupported padding rejects explicitly.
Width unavailable rejects before rendering. Existing structure failure returns
unchanged pixels. The native consumer composites only applied original masks;
every pixel outside the coarse mask remains identical. These constraints do not
prove naturalness or privacy.

The frozen_seed_pitch diagnostic backend records its original measurement in
the same schema but cannot authorize external v1: it lacks the required FFT cue.
When both backends observe pitch, relative difference is diagnostic only.

## Linux usage

Prepare source-bound semantic caches with the existing isolated COLFISPOOF setup.
Install public requirements and configure the unchanged SourceAFIS/NBIS runtimes.

```bash
export BLURFING_SOURCEAFIS_HOME=/path/to/sourceafis
export BLURFING_NBIS_LINUX_CONFIG=/path/to/nbis_runtime_linux.json
python ai/scripts/protect_photo_external_pitch_v1.py \
  --input /path/to/input.jpg --semantics /path/to/private/semantics \
  --output /path/to/private/fresh-v1-output
```

Output is native encoded-coordinate returned.png plus audit.private.json with all
accepted/rejected evidence, frozen diagnostics, conversions and gate outcomes.
All outputs, including evidence JSON, must remain private. The function API is
`photo_external_pitch_v1.render(image, mask, seed_roi, scope, evidence, source_sha,
image_scale, coordinate_space)`; supply the exact observed working image/mask.

```bash
python ai/scripts/benchmark_photo_external_pitch_v1.py \
  --input /path/to/input.jpg --semantics /path/to/private/semantics \
  --output /path/to/private/fresh-benchmark --repeats 10
python -m unittest discover -s ai/scripts -p 'test_*.py'
```

Benchmark excludes one warm-up. The complete consumer benchmark includes cache
loading, coarse adaptation, observers, rendering, compositing, unchanged structure
validation and both matchers. It excludes COLFISPOOF inference and therefore is
not directly comparable to a full RGB-to-model benchmark. Separate observer /
renderer-structure timings are recorded in results. No Windows equivalence or
independent holdout validation is claimed.
