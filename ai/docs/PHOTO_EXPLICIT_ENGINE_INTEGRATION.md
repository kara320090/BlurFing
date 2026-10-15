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
| `pose_v14` | Observed hand joints/TIPs with semantic BODY and TIP-connected permissions | Consumed registry and isolated hand runtime; no V6 pad model |

`distal_v13` is a geometry experiment requiring boundary review. It showed
regression against existing human annotations and is not a generalized
detector improvement. COLFISPOOF still requires its separately configured
semantic segmentation model. These experiments are not approved for production
or independently validated privacy/protection.

`pose_v14` is a separate full-hand geometry experiment. It requires exactly
one observed hand and all five distal axes; missing/multiple hands or invalid
geometry return the original RGB as rejected. It does not try V6 or V13 after
rejection. See [pose configuration and limitations](PHOTO_POSE_NATIVE_V14.md).

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
The same registry-only argument rule applies to `pose_v14`.
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

Pose V14 additionally requires process-local `BLURFING_HAND_PYTHON` and
`BLURFING_HAND_MODEL`. The worker runtime and official model stay outside the
repository. The PowerShell launcher inherits these variables; it does not
install or mutate a global environment.

Changing engine, model, registry, or replay mode invalidates the old preview
and save action. The process job and benchmark capture the same selection;
a late result from a previous configuration cannot replace the new result.
The geometry experiment displays a boundary review warning.

Synthetic tests cover engine/flag/path validation, lazy legacy defaults,
PHOTO versus scanner/UNKNOWN routing, partial/rejected metadata,
RGBA/EXIF dispatch, no alternate-engine retry, fresh output, GUI job identity,
and actual Windows PowerShell argument transport. These tests do not measure
detector accuracy, matcher security, runtime latency, or Linux parity.

## Backend and Android integration boundary — 2026-10-16

The existing V1 bytes/rectangle `gaussian_blur` contract remains separate.
The opt-in [V2 server](../../backend/README-photo-v2.md) and
[Android experimental flow](../../android/docs/EXPERIMENTAL_PHOTO_V2.md) now
carry actual status, accepted/rejected masks and unapproved flags. They
validate source binding, output shape, mask hashes and changed pixels inside
accepted permissions. Display bounds do not replace masks. No native engine
is labeled `gaussian_blur`, and there is no engine or Mock fallback.

Desktop PHOTO output preserves valid source RGB ICC without changing RGB
samples; the GUI converts only its preview for display. HTTP instead requires
client-normalized sRGB/EXIF1 pixels in a canonical RGB8 PNG without color
chunks. Both paths preserve the original file.

Actual configured local HTTP and Android Repository-to-MediaStore readback
were verified on one development photo; see the
[dated checks](PHOTO_DESKTOP_VALIDATION_20261016.md). These checks do not
approve detector accuracy, general privacy protection, independent final
testing or Linux equivalence. Authentication, external deployment and broad
physical-device validation remain separate requirements.
