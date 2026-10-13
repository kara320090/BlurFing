# Private PHOTO pad refinement training protocol

Current state: annotation/crop preparation and code are complete; actual training is blocked by unavailable official pretrained encoder weights. No GT7 refinement test has run. See [status](../results/pad_refinement_training_summary.md).

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

## Encoder acquisition and training

Keep PyTorch and TensorFlow in their existing separate environments. The tested installed PyTorch/Torchvision versions are 2.13.0+cu130 / 0.28.0+cu130; no environment downgrade or installation was performed.

Acquire the official torchvision ImageNet checkpoint from:

`https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth`

The loader checks the official SHA-256 filename prefix and records the full acquired SHA-256. It never downloads implicitly or silently falls back to random initialization. Weights must remain private/outside Git.

```bash
/path/to/torch-env/bin/python ai/scripts/train_pad_refinement.py \
  --dataset /path/to/private/new_crop_dataset \
  --encoder-weights /path/to/private/mobilenet_v3_small-047dcff4.pth \
  --output /path/to/private/new_training_run
```

The fixed protocol is declared in code and saved before training: MobileNetV3-small pretrained encoder, 4-channel input, lightweight skip decoder, BCE+Dice, 5 folds, seed 20261014, max 40 epochs, patience 6, threshold 0.5. Final training uses all ten sources once for the median best-epoch count. BatchNorm remains fixed; other encoder layers are frozen except input convolution. RGB weights are copied and the extra channel zero-initialized. Augmentation is limited to training crops.

Validation measures full-source masks restored through crop/letterbox geometry and clipped to semantic body. Missing GT outside crop coverage remains a validation error; crop-only scores do not hide it.

## One-shot final test

Do not run GT7 until all folds and final training complete with a hash-bound checkpoint. Freeze architecture, threshold, epoch count and transforms first. Apply that single model version to all seven test images, restore native masks, clip to finger body and report the unchanged metrics/matching rule. No GT7-based re-training or threshold/epoch changes are allowed. The current task did not consume this final test because no pretrained encoder/final checkpoint is available.

A PHOTO protection adapter remains disabled until quantitative and private visual safety gates pass. Existing frozen PHOTO renderer and scanner are unchanged. Model weights, photos, human GT, crops and overlays must never be committed.
