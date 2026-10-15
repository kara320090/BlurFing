# Explicit experimental PHOTO engine integration

The routed CLI/library and Windows development GUI can select one PHOTO
engine explicitly. The default remains `legacy`; scanner/UNKNOWN behavior and
existing renderer/quality thresholds are preserved. No per-image best-result
selection or fallback between experimental engines occurs.

| Engine | Permission source | Explicit private configuration |
| --- | --- | --- |
| `legacy` | Existing default pipeline | Existing runtime configuration |
| `native_v12` | V6 learned pad mask | Completed V6 model directory and consumed registry |
| `distal_v13` | Existing COLFISPOOF body/distal geometry | Consumed registry; no V6 pad model |

`distal_v13` is a geometry experiment requiring boundary review. It showed
regression against existing human annotations and is not a generalized
detector improvement. COLFISPOOF still requires its separately configured
semantic segmentation model. Neither experiment is approved for production
or independently validated privacy/protection.

## CLI and library

```sh
python ai/scripts/protect_fingerprint.py --input /private/photo.png \
  --output /private/fresh-result --photo-engine native_v12 \
  --photo-model /private/completed-V6 --consumed-registry /private/consumed.json

python ai/scripts/protect_fingerprint.py --input /private/photo.png \
  --output /private/fresh-geometry-result --photo-engine distal_v13 \
  --consumed-registry /private/consumed.json
```

The matching `protect_image` keyword arguments are `photo_engine`,
`photo_model`, `consumed_registry`, and `development_replay`. Boolean flags
must be real booleans. Experimental options require an explicit engine;
`distal_v13` rejects a V6 model argument instead of silently ignoring it.
Hand/SAM runtime injection cannot be combined with either experiment.

Strict consumed-source exclusion remains the default. Previously used photos
can be retested only with explicit `--development-replay`; those results
remain development reuse and never become independent evaluation data.
`--detect-only` and strength zero disable transformation. Strength retains
the existing supported values zero and 0.5.

Experimental PHOTO routing uses the selected entrypoint's RGB/RGBA/L
canonicalization before the legacy RGB/L restriction. Encoded original pixel
coordinates and EXIF orientation are preserved. The adapter adds common
unified fields in `result.json`, alongside the experiment's unchanged
`result.private.json` audit. Applied/rejected statuses and reasons are
preserved. Candidate component counts are not anatomical finger counts.

## Windows

`ai/platform/windows/run_unified.ps1` accepts `-PhotoEngine`, `-PhotoModel`,
`-ConsumedRegistry`, and explicit `-DevelopmentReplay`, for both CLI and
`-Gui`. The GUI also exposes the selection and private path fields. Native
V12 requires model plus registry; distal V13 requires only the registry.
The existing default CLI invocation is unchanged.

Changing engine, model, registry, or replay mode invalidates the old preview
and save action. The process job and benchmark capture the same selection;
a late result from a previous configuration cannot replace the new result.
The geometry experiment displays a boundary review warning.

Synthetic tests cover engine/flag/path validation, lazy legacy defaults,
PHOTO versus scanner/UNKNOWN routing, partial/rejected metadata,
RGBA/EXIF dispatch, no alternate-engine retry, fresh output, GUI job identity,
and actual Windows PowerShell argument transport. These tests do not measure
detector accuracy, matcher security, runtime latency, or Linux parity.

## Backend and Android integration boundary

The existing backend processor returns bytes only, supports `gaussian_blur`,
and reports every requested rectangle as applied. Android accepts only
`succeeded`. Connecting a partially rejecting PHOTO engine through that
contract would overstate which regions were processed. The current
experimental desktop integration does not activate that backend path.

A separate integration must introduce all of the following together:

- An explicit experimental method and automatic-detection versus manual
  permission contract. Do not label the native renderer `gaussian_blur` or
  silently ignore the user's selected regions.
- A structured processor result containing returned PNG, actual status,
  accepted permissions, rejected candidates/reasons, engine/model/runtime
  provenance and unapproved privacy flags. A bounding box alone does not
  guarantee that all its pixels were protected.
- Backend validation of returned size/format, actual accepted masks and
  source binding; no echoing requested regions as proof of application.
- Android presentation of partial/rejected output and exposed regions,
  preserving the source and clearly labeling unvalidated protection.
- New contract, timeout/concurrency and end-to-end tests using actual
  configured runtimes. Authentication, deployed servers and real devices
  remain external verification requirements.
