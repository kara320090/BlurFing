# Class-balanced whole-pad development experiment

V4 final training did not sufficiently recover full pad coverage. Its native
training-fit IoU is 0.574985 on the new whole-pad 13 photos and 0.205768 on
legacy GT10. It is not adopted as an improved model. An independent code and
checkpoint audit found correct epoch selection, optimizer membership/learning
rates, actual updates to every trainable parameter, unchanged frozen encoder
and BatchNorm, aligned augmentation, and matching saved weights. Low coverage
is not evidence of a checkpoint/gradient wiring bug.

The dataset has 657 GT-free planned body tiles. Source-weighted empty targets
occupy 73.78%, while foreground pixels occupy 6.9648%; padding is only 2.19%.
Equal source weight does not balance classes. This motivates a separate fixed
objective experiment, without asserting imbalance is the only limitation.

## V5 objective

`whole_pad_balanced_loss_v1.py` computes foreground fraction `p` as the mean
over training sources, then tiles within each source, then all 256x256 label
pixels including padding, before augmentation. Only a fold's training IDs are
read; validation targets do not supply class statistics. The final all-source
model computes its own statistics. The statistics, IDs and crop hashes are
frozen with the training protocol. Invalid/empty class populations reject;
there is no fallback or clamp.

The loss is class-weighted unreduced BCE with `w+ = 1/(2p)` and
`w- = 1/(2(1-p))`, plus the original smoothed Dice only for nonempty target
tiles. Empty tiles retain BCE and background gradients. Every tile still
participates, including nails/background. Existing source weights and division
by configured batch size, including partial batches, are preserved.

Weighted BCE changes calibration and the effective decision boundary. Keeping
the numeric prediction threshold at 0.5 does not preserve the unweighted
posterior decision meaning. Recall and false positives must both be measured;
foreground expansion alone is not an improvement or authorization to transform
skin/nails. Predicted probabilities are not declared calibrated confidence.

`train_whole_pad_target_v5.py` uses the unchanged V4 dataset, architecture,
official fresh initialization for every fold, augmentation, optimizer, seed,
group splits, stopping/epoch rule, GT-free validation geometry and probability
merge. V3/V4 code and checkpoints are preserved. Asset/code checks also run
after final checkpoint save; changed inputs prevent a completed config.

```powershell
python ai/scripts/train_whole_pad_target_v5.py --dataset <private-V4-dataset> --encoder-weights <official-weights> --output <fresh-private-V5-folder>
```

The separate opt-in runtime uses `infer_whole_pad_target_v5.py` and
`protect_photo_whole_pad_v3.py`; it rejects V4 checkpoints. Optional
`--experimental-multiscale-observation` selects the same component-local V10
observer described in [the V4 target experiment](PHOTO_WHOLE_PAD_TARGET_V4.md).
Quality thresholds, renderer/compositor math, same-component profile support,
renderer remeasurement, exterior and rejected-pixel preservation are unchanged.
Default unified/GUI paths are not activated by this experiment.

The 23 sources contain only three conservative development groups and mixed
legacy/new annotation policies. All results remain consumed development or
training fit, not independent final validation. This loss cannot recover
finger pixels outside observed body or establish anatomical ownership. Model
and complete-photo protection approval remain false.
