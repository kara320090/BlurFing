# Raw COLFISPOOF semantic evaluation

This is an evaluation route, not the primary PHOTO frontend or an approved protection detector. It loads an external pretrained DeepLab graph and never calls official `segment()` postprocessing. The scanner branch and frozen PHOTO renderer are unchanged.

## External runtime

Provide a separately installed COLFISPOOF preprocessing checkout and its official model archive. Do not copy them into this repository. The evaluated environment used TensorFlow 2.10.0, OpenCV 4.6.0, NumPy 1.21.6 and Pillow 9.3.0 on CPU. Use a separate virtual environment; do not modify the existing matcher or SAM environment.

The model archive must have SHA-256 `f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f`. The loader imports only external `Segmentation/DeepLabModel.py`, verifies the archive hash, disables GPU use and sets eight intra-op/one inter-op threads. No model, external repository, image, GT or preview is redistributed here. Respect upstream usage terms and acknowledge Kolberg et al., WACV 2023, [COLFISPOOF](https://github.com/dasec/COLFISPOOF).

## GT-free inference

Create a private input JSON containing only `sample_id`, `source` and `source_sha256` for every input. Obtain the SHA-256 directly from source bytes. Source paths must identify the exact encoded original JPG; when resolving annotation metadata with no explicit source path, match its source filename and SHA-256 to a unique capture file. Never pass GT paths or polygons to the inference worker.

```json
[
  {
    "sample_id": "DEV-01",
    "source": "/path/to/input.jpg",
    "source_sha256": "<source SHA-256>"
  }
]
```

From the repository root, using the separate TensorFlow environment:

```bash
/path/to/model-env/bin/python ai/scripts/run_colfispoof_raw.py \
  --inputs /path/to/private/inputs.json \
  --output /path/to/private/new-inference-output \
  --external-source /path/to/COLFISPOOF/pre-processing \
  --model /path/to/COLFISPOOF/pre-processing/Segmentation/model/deeplab_model.tar.gz \
  --benchmark-sample DEV-01
```

The output directory must be new. Each source is inferred three times, each with four rotations. It saves per-rotation binary masks, repeat consensus masks, source/model identities, transformation geometry, semantic label counts and timings. Benchmark uses one additional warm-up and ten measured four-rotation passes.

Primary policy is fixed: semantic class 2, >=2/4 pixel votes, no component cleanup. Classes 1 and 2 are the upstream finger-area classes; class 2 alone is fingertip. Black padding is removed; label maps use nearest-neighbor restoration. No EXIF transposition occurs: output masks use encoded-original pixels. Official preprocessing's positional OpenCV call actually uses default LINEAR resizing; the compatibility wrapper preserves that behavior. The model's own INPUT_SIZE=4608 PIL resize is unchanged.

## Separate GT evaluation

Create a private evaluation roster containing `sample_id`, `source` and `GT_folder`. Use the existing verified human annotation `source.json` / binary PNG format in encoded-original pixels. Ambiguous annotations are excluded from positive metrics; declared non-target annotations require a verified empty mask.

Run in the existing compatible BlurFing scientific-Python environment (this step does not import TensorFlow):

```bash
/path/to/evaluation-env/bin/python ai/scripts/evaluate_colfispoof_raw_gt.py \
  --roster /path/to/private/evaluation-roster.json \
  --inference /path/to/private/new-inference-output \
  --output /path/to/private/new-evaluation-output
```

Source/annotation hashes, binary masks, dimensions and saved prediction hashes are checked. Metrics use 4-connected components and Hungarian one-to-one matching with component IoU>=0.5. An unmatched true-fingertip subset is counted as an unmatched prediction; this statistic alone does not establish a background false positive.

Raw >=2/4 masks are the primary result. Union, 3/4 and intersection are diagnostic only. The unchanged shared ridge validator is evaluated separately per raw-component crop; its output must remain inside the raw mask. Neither secondary metrics nor GT scores can change inference policy.

All PNGs, overlays, source identities and private rosters remain private. Public output should contain only anonymous IDs and aggregate/sample measurements. See [GT7 results](../results/colfispoof_raw_gt7_summary.md).

## Decision

The evaluated raw model preserves real fingertip localization in several general photos but fails the close-up and undercovers some pads. It is not integrated into `protect_fingerprint.py`, not approved for protection and not a replacement for the preserved legacy route. No new heuristic was used to repair its outputs. GT7 is evaluation-only and must not be reused for training/fine-tuning.
