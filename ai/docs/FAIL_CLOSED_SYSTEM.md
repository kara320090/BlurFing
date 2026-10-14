# Unified development system and completion limits

## Architecture

`protect_fingerprint.py` CLI / `protect_image()` API → unchanged content router →
PHOTO, FINGERPRINT_IMAGE or UNKNOWN. File names and identities are not routing
features. Processing can reject correctly; detected count is not accuracy.

PHOTO primary: configured isolated COLFISPOOF DeepLab (class 1+2, four rotations,
fixed consensus) → unchanged coarse distal estimator → source-bound Canonical
adapter → existing experimental input normalization → frozen natural_auto_04 +
boundaryblend_02 → unchanged width/pitch/feature/structure gates → native RGB.
Only admitted pads are composited. Failed pads and the exterior are identical.
The rejected neural refinement is never used. MediaPipe/SAM and legacy remain
optional historical/fallback tools, not primary. The external-pitch-v1 entrypoint
is a separate opt-in experiment using a different existing lower-level renderer;
it is not silently selected to maximize GT7 results.

SCANNER: unchanged foreground/ridge/canonical frontend → unchanged scanner
renderer → unchanged scanner structure guard → native result. UNKNOWN returns
unchanged image. Scanner and PHOTO do not share a skin compositor.

## PHOTO outcomes

Every proposed pad has a stable `quality_status`:

| Code | Meaning |
|---|---|
| TRANSFORMED | Existing gates passed and pixels applied |
| REJECT_WIDTH_UNAVAILABLE | Existing observed width unavailable |
| REJECT_PITCH_UNOBSERVED | Existing pitch observation unavailable |
| REJECT_PITCH_UNSTABLE | Optional evidence does not agree or orientation unstable |
| REJECT_INSUFFICIENT_FEATURES | Unchanged prototype feature requirement failed |
| REJECT_RENDERER_CONTRACT | Scope, size or observed pitch contract not met |
| REJECT_OTHER | Explicit other reason; never counted as applied |

Top-level status: success if all detected pads apply, partial_success if only some
apply, rejected if none apply (including no detected pads). Counts, region reasons,
source SHA, native dimensions, EXIF orientation and private mask hashes accompany
the returned image. Missing runtime/operational failure is explicitly reported;
it is not evidence that the photograph lacks fingerprints. Unsupported/corrupt
inputs produce structured CLI error JSON, with diagnostics on stderr.

PHOTO_DETECTOR_APPROVED=false and PHOTO_PROTECTION_PRODUCTION_READY=false.
PHOTO fail-closed readiness means tested containment/rejection/control flow,
not reliable detection of all true pads or absence of background false positives.
The coarse GT7 IoU remains 0.7529 and coverage 10/10; neither was retuned.

## Unified usage

```bash
python -m pip install -r ai/requirements.txt
export BLURFING_SOURCEAFIS_HOME=/path/to/sourceafis
export BLURFING_NBIS_LINUX_CONFIG=/path/to/nbis_runtime_linux.json
export BLURFING_COLFISPOOF_PYTHON=/path/to/isolated-tensorflow-python
export BLURFING_COLFISPOOF_SOURCE=/path/to/COLFISPOOF/pre-processing
export BLURFING_COLFISPOOF_MODEL=/path/to/deeplab_model.tar.gz
python ai/scripts/check_unified_runtime.py
python ai/scripts/protect_fingerprint.py --input /path/to/image --output /path/to/private/fresh-result
```

Core scientific dependencies and TensorFlow 2.10 model dependencies stay isolated;
no existing environment is downgraded. Model/runtime/JAR/source archives are not
bundled. Runtime check verifies prerequisites/files/hash, not execution equivalence.
The official model SHA check stays unchanged. No model download is performed by
image upload. Missing configuration rejects normally with its reason.

For an already source-bound private semantic cache, add
`--photo-semantics /path/to/private/semantics`. It is validated against the exact
source bytes and dimensions. `--detect-only` or strength 0 preserves pixels.
Full CLI processing defaults on; library users should use:

```python
from protect_fingerprint import protect_image
rgb, report = protect_image(input_path, output_path)
```

The older protect_fingerprint() low-level signature remains available for explicit
legacy compatibility, including caller-provided scanner guard semantics.
Actual PHOTO result masks and JSON are private biometric/provenance artifacts;
never publish them. PNG saves only orientation metadata, not identifying EXIF.

## Independent PHOTO evaluation

No eligible independent holdout is currently established. Existing 55 captures,
GT7 and TRN inputs are not promoted. The prepared inbox is reported by the current
completion audit; project originals are not changed to create it.

`config/independent_photo_manifest.example.json` is a template. Supply actual
source SHA, capture date, participant alias and explicit provider declarations of
independence/non-use for training or tuning. These declarations are not inferred
from file names, directory timestamps, or a new hash alone. A nonempty private
development hash index excludes known old captures/training/GT images. Near-frame
or identity/date independence additionally requires honest provenance from the
provider; content hashes cannot prove it.

```bash
python ai/scripts/evaluate_independent_photo.py \
  --manifest /path/to/private/holdout_manifest.json \
  --development-hashes /path/to/private/development_hashes.json \
  --output /path/to/private/fresh-evaluation
```

Before/after code hashes are pinned, configurations must remain fixed, source hashes
are checked, old/duplicate hashes rejected, and outputs repeated for determinism.
Optional `ground_truth_folder` records supply human masks solely for evaluation.
Ambiguous-unusable masks are excluded; explicit empty non-target GT measures false
positives. Without GT no accuracy is computed. Routing, counts/reasons, exterior
and deterministic signatures are recorded. Catastrophic wrist/keyboard/background
transform review is marked pending, not presumed successful. The evaluator never
sets final independence/project completion true from automation alone.

## Windows GUI

`ai/app/windows/unified_gui.py` is a new thin Tk interface to the same CLI. No
previous GUI source was available in the working clone, so existing external user
GUI files were not overwritten. Features: select/process, type and counts/reasons,
private preview/save, read-only runtime check and 1+10 CLI benchmark. It never
duplicates detector/renderer calculations and refuses saving over the source.
Actual Windows runtime/full-equivalence testing remains pending. Linux syntax or
platform dispatch tests are not Windows execution evidence.

See WINDOWS_SETUP.md. Python with Tcl/Tk, Java, external SourceAFIS/NBIS runtimes
and isolated COLFISPOOF runtime are required. Use configured Windows paths; no
private binaries/models are bundled. Background workers do not freeze Tk UI.

## Benchmark and validation scope

```bash
python ai/scripts/benchmark_unified_pipeline.py \
  --input /path/to/image --output /path/to/private/fresh-benchmark
python -m unittest discover -s ai/scripts -p 'test_*.py'
```

One excluded warm-up plus ten runs. Phase timing records routing, model subprocess
(including per-request runtime startup), coarse/observer, inclusive PHOTO quality
gate, renderer/compositor and structure validation, or scanner segmentation/ridge,
transform and guard. Instrumented timings are nested and NOT additive; profile
instrumentation overhead is included. The core guard's feature extraction belongs
to validation. Separate NBIS/SourceAFIS score-observation timings are provided by
prior dedicated benchmark results; they are not silently included as optional
identity comparisons in this core benchmark.

Stable signatures exclude elapsed time and fresh output paths. Machine outcomes,
mask/pixel signatures and rejection semantics are deterministic; entire audit JSON
with measured times is not expected to be byte-identical.

## Completion criteria

Linux development flow can be mechanically ready while PHOTO production approval
is false. Global functional completion still requires actual Windows integration
regression/equivalence, and project completion additionally requires independent
captures and sufficient reviewed evidence. Neither missing requirement is waived.
Score reduction is not universal privacy/security proof; feature extraction failure
is not success. Synthetic ridge regularity, seams, domain mismatch, router errors
and small reused development sets remain limitations.
