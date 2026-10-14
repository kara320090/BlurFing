# Refinement coverage and acquisition-group development plans

`pad_refinement_experiment_plan_v2.py` provides standalone planning functions. It is not imported by PHOTO protection, the historical trainer or inference. The rejected historical refinement model stays disabled. Renderer/compositor math, existing thresholds, historical folds/results and original input files are unchanged.

The training audit found geometric support loss before a model can predict: coarse-guided crops plus semantic body clipping made 197,906 target pixels unreachable in the ten development sources. Of these, 76,927 were inside body but outside crops; 120,979 were outside semantic body. This does not establish a training-code failure or explain all PHOTO quality-gate rejections.

## GT-free coverage plan

The immutable versioned engineering policy uses all native body components, four-connectivity, deterministic 512-pixel windows, 384-pixel stride and last-edge anchors. A 512-to-256 model input permits at most two native pixels per model axis. Windows are included only by observed body support, never by GT. Identical boxes are deduplicated. No tiny component is silently filtered. Source raster limits are checked before native allocations; more than 256 components or 256 unique windows rejects the entire source and returns no partial plan. This is a resource rule, not a detector threshold.

The planner accepts only source identity plus exact-shape Boolean body/coarse arrays. Coarse outside body is rejected. It returns source/mask/policy hashes, exclusive boxes, body coverage and overlap multiplicity. Annotation fields are forbidden. Policy parameters were frozen from this sampling/resource design before target comparison; no parameter search was performed.

On the ten existing development sources, 295 windows (15–41 per source) cover every original body pixel. The geometric target recall ceiling becomes 0.9460 macro / 0.9599 pooled, compared with the coarse-guided crop/body ceiling 0.9107 / 0.9344. All 76,927 body-interior crop misses are reachable; the 120,979 body-exterior pixels remain excluded. These are support ceilings, **not predicted model scores, demonstrated improvement or protection success**. No new crop labels were fitted, checkpoint produced or final test consumed.

Full-body coverage can introduce wrist/background semantics and many empty-label windows. More overlapping windows can change max-probability aggregation and give larger sources more training weight. A new protocol must freeze inference merge, normalization, per-source weighting, negative sampling, augmentation and checkpoint crop-policy compatibility before real training. The old checkpoint cannot be used with this tile plan.

## Acquisition-group development plan

`group_splits` takes explicit anonymous acquisition-group labels and verified raw-file, encoded-RGB and upright-RGB identities. It rejects duplicate source IDs, raw or decoded pixel duplicates (including cross-orientation identities), unknown/missing groups and reserved source hashes. Case variants normalize to the same group; padded group labels are rejected. Every crop/source stays with its group in leave-one-group-out development folds.

The current ten sources provide only two provenance groups (7 and 3 sources), so two developmental folds are possible. Folder/date provenance is not independently verified biometric identity. Existing GT7 and diagnostic holdouts are already consumed. Neither these two folds nor the crop-support measurement constitute a new independent test. The historical five-fold training protocol is retained separately.

New model validation needs additional capture groups with original photos and human-reviewed pad masks, plus explicit provenance to keep related captures together. Preserve the encoded source and EXIF; masks must be binary 8-bit PNG in the exact encoded-original shape/coordinates. Model-generated body/tip/segmentation files are not human GT. Freeze a separately reserved new test cohort before fitting; missing reserved-test identities cannot be reported as verified exclusion.
