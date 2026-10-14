# Private PHOTO pad refinement training protocol

Current state: the historical model completed training and its one-shot GT7 evaluation was rejected (macro IoU 0.4149; coverage 3/10). It remains disabled in PHOTO inference. The earlier [preparation status](../results/pad_refinement_training_summary.md) is historical; see the [final result](../results/pad_refinement_final_summary.md). The V2 asset contract below fixes reproducible input/evaluation errors without changing the historical model, thresholds, crop policy or results.

Exactly ten allowed source IDs are enforced by code: TRN-001/002/003/004/006/010/014/016/020/022. Source-level folds keep every crop from a source together. GT7 source hashes are passed as an exclusion list; GT7 labels and images are never loaded by the trainer. GT7 cannot choose crops, hyperparameters, validation/early stopping, epochs or probability threshold.

## Data preparation

Use the existing scientific-Python environment, without changing the coarse frontend. Produce private per-source `body.png`, `tip.png`, and source/hash-bound `semantics.json` with the existing COLFISPOOF body adapter. Then:

```bash
/path/to/evaluation-env/bin/python ai/scripts/prepare_pad_refinement_data.py \
  --roster /path/to/private/training_annotation_roster.json \
  --annotations /path/to/private/ground_truth_training \
  --semantic-root /path/to/private/training_semantics \
  --test-hashes /path/to/private/reserved_GT7_source_hashes.json \
  --output /path/to/private/new_crop_dataset
```

The output is private RGB/coarse/label NPZ crops and source-level metadata. Bboxes are computed only from coarse candidate masks, with 35% context padding. Labels are applied afterwards. Empty/unusable source annotations fail; zero proposals block training rather than using GT bboxes or inventing negatives. A coarse false-positive crop can naturally have an empty label in an otherwise valid positive source; that is not conversion of an unusable annotation.

New preparation writes `pad_refinement_data_v2`: encoded source/RGB, EXIF, body/tip/semantic metadata, human annotation and individual crop hashes are bound to exact dimensions and coordinate systems. Consumers preflight every source/crop before a model, optimizer, test ledger or prediction output is created. Assets are checked again from the same bytes at consumption. Native masks cannot broadcast, NPZ members/header/raster/decompression reads are bounded, and crop paths are contained basenames with case-insensitive duplicate checks. Preparation captures identities before estimating crops and rejects changed inputs before publishing a manifest.

V1 manifests are not accepted or automatically re-signed. Regenerate into a fresh private directory from authoritative original photos, human masks and verified semantics. An empty reserved-test hash list permits development-only preparation, reports overlap as unavailable, and blocks training. Training still requires all seven reserved source hashes and no overlap. Declared blocked-source fields cannot hide missing crops. An existing historical checkpoint only accepts its unchanged `coarse_guided_v1` crop policy.

## Encoder acquisition and training

Keep PyTorch and TensorFlow in separate environments. The historical training used PyTorch/Torchvision 2.13.0+cu130 / 0.28.0+cu130. V2 Windows contract and synthetic gradient checks use a separate CPU environment (2.14.1+cpu / 0.29.1+cpu); the PHOTO TensorFlow and core environments are unchanged. These checks are not a new trained-model evaluation.

Acquire the official torchvision ImageNet checkpoint from:

`https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth`

The loader verifies the complete official SHA-256 `047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f`, rather than only its filename prefix. It never downloads implicitly or silently falls back to random initialization. Weights must remain private/outside Git.

```bash
/path/to/torch-env/bin/python ai/scripts/train_pad_refinement.py \
  --dataset /path/to/private/new_crop_dataset \
  --encoder-weights /path/to/private/mobilenet_v3_small-047dcff4.pth \
  --output /path/to/private/new_training_run
```

The fixed protocol is declared in code and saved before training: MobileNetV3-small pretrained encoder, 4-channel input, lightweight skip decoder, BCE+Dice, 5 folds, seed 20261014, max 40 epochs, patience 6, threshold 0.5. Final training uses all ten sources once for the median best-epoch count. BatchNorm remains fixed; other encoder layers are frozen except input convolution. RGB weights are copied and the extra channel zero-initialized. Augmentation is limited to training crops.

Validation measures full-source masks restored through crop/letterbox geometry and clipped to semantic body. Missing GT outside crop coverage remains a validation error; crop-only scores do not hide it.

## One-shot final test

GT7 was already consumed by the historical experiment. Do not treat it or subsequent diagnostic holdouts as a fresh independent test. Future improvements need a separately frozen development protocol and new capture groups with human-reviewed masks. Freeze architecture, threshold, epoch count and transforms before a new final test. No GT7-based re-training or threshold/epoch changes are allowed.

A PHOTO protection adapter remains disabled until quantitative and private visual safety gates pass. Existing frozen PHOTO renderer and scanner are unchanged. Model weights, photos, human GT, crops and overlays must never be committed.

## Resumed run outcome

The encoder was subsequently acquired and verified. The unchanged protocol completed all five folds and final training for median 13 epochs. The one-shot GT7 model was rejected: macro IoU 0.4149, coverage 3/10. See [final report](../results/pad_refinement_final_summary.md). Earlier blocked status is retained as a historical preparation record.

`prepare_pad_refinement_inference.py` creates GT-free inference crops from source-identity inputs and verified semantic masks. `infer_pad_refinement.py --one-shot-GT7` requires a completed, hash-bound final model and creates an exclusive test ledger before prediction; no threshold override is provided. `evaluate_pad_refinement_final.py` scores already frozen prediction files and creates private overlays. These are experiment/evaluation tools, not an approved PHOTO protection route.

The evaluator now excludes ambiguous/unresolved annotations from all metric totals, including false-positive components; missing ambiguous masks remain review-only. Historical GT7 annotations were valid positive, so this correction does not revise its reported result. A ledger provides local run control, not a new independent test or permission to repeat a consumed test.

## Historical GT7 source recovery (2026-10-15)

A private transfer restored seven original GT7 photos and hash-bound human-declared annotations. Archive SHA-256, CRC, internal file checksums, encoded dimensions/EXIF and binary masks passed. Export names beginning with `NEW-` do not change their consumed historical role. Participant/finger/session separation is unconfirmed. Prior source identities were matched; identical historical mask bytes were not independently established. The JPG-named MPO sources are recorded with their existing first-frame interpretation.

The verified seven reserved source hashes now bind a fresh V2 preparation of the original ten training sources, with no raw-source overlap and the same 27 RGB/coarse/label arrays and geometry. These GT7 samples are excluded from training and cannot supply a fresh independent final test. No model was fitted or GT7 scores rerun. Real improvements still need separately grouped, unused human annotations and a new reserved test cohort.

The import exposed a Windows locale error in the shared annotation reader for unescaped Korean UTF-8 JSON. Source metadata and CLI roster reads now explicitly accept UTF-8 with or without BOM. The original files, hashes and numerical annotation/metric rules are unchanged. A synthetic Korean-filename regression and 325 tests in the isolated CPU PyTorch environment passed.

The separate [V3 body-tile developmental experiment](PAD_REFINEMENT_TILES_V3.md) is now implemented and measured. It improves same-GT10 group-heldout IoU but increases missed pad pixels and transforms zero of ten heldout sources through unchanged protection gates. It does not adopt this historical rejected refinement or enable a new default detector.
