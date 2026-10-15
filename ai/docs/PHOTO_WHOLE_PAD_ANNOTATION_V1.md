# Whole visible fingerprint pad annotation v1

The intended PHOTO protection target is the complete visible palmar distal
finger pad, from the fingertip silhouette to the first flexion crease. Clear
ridge pixels are evidence for the protection transform; they do not define a
smaller permission mask. A detected candidate outline is not proof of correct
anatomy or of a completed transform. The current learned detector and V8 remain
experimental and are not approved for complete-photo protection.

## Human boundary policy

`whole_visible_palmar_distal_pad_v1` includes the visible pad interior, including
blurred or shadowed portions whose anatomical boundary remains clear. Draw each
pad separately. Exclude nails, dorsal skin, proximal finger segments, background,
and occluded surfaces. Do not infer hidden anatomy or label only the clearest
ridge patch. Use `ambiguous_unusable` with a reason when the surface or boundary
cannot be determined reliably. `non_target` requires an empty mask; reviewed
`valid_positive` requires a nonempty mask and explicit per-photo attestation.

The previous development GT contains broad pad polygons but does not document
this exact first-crease policy. Preserve that material; do not silently relabel
it as a newly reviewed policy-compliant dataset.

## Local tool

Run the existing scientific Python environment, with NumPy and Pillow:

```powershell
python ai/scripts/photo_pad_annotation_v1.py --roster <private-roster.json> --state <separate-private-state-folder>
```

The tool prints a random session URL on `127.0.0.1`. Open it in a browser. It
does not load predictions, run training, or access an external service. Image
bytes and masks remain private. One server process must own a state folder;
multiple browser windows use optimistic revision checking through that server.

The private roster schema is `whole_pad_annotation_roster_v1`, with `data_role`
equal to `diagnostic_development` (real photos) or `synthetic_fixture`. Each
`sources` row provides a unique `source_id`, absolute `source_path`, expected
`source_sha256`, integer encoded `width`, `height`, and `exif_orientation` (1–8).
Optional `encoded_RGB_sha256` and `upright_RGB_sha256` bind decoded pixels too.
The current tool accepts RGB and L sources within the existing 32 MiPixel input
contract. It preserves original bytes and does not rewrite source files.

Use zoom and pan to trace a pad with clicks, then close the polygon. Add other
pads separately and subtract accidental background as needed. Drafts autosave
after edits and preserve an unfinished polygon and its add/erase mode. They are
not GT. Review each photo, select its status, and explicitly attest before
publishing its mask. A later edit creates a new draft, requiring another review.

Display coordinates follow EXIF orientation. Published binary L PNG masks use
the original encoded dimensions and inverse EXIF mapping. The original is never
rotated in place. Polygon interiors use even-odd fill in both canvas and Pillow;
browser antialiasing at the boundary is only a display aid, not mask values.

## Storage and export

Reviewed revisions contain `source.json`, `ground_truth_mask.png`, `preview.png`,
and `annotation.json`; draft revisions only contain `annotation.json`. Revisions
are immutable and a hashed `latest.json` pointer selects the current one. If
publication is interrupted, an orphan directory is preserved and the next save
uses a fresh revision number. Roster, source, and reviewed asset hash mismatches
are errors. A stale window must not overwrite another window's revision.

ZIP export includes only each photo's latest explicitly reviewed revision and
its original image, an anonymous internal source ID, metadata, and file hashes.
A latest draft excludes that photo even if an older reviewed revision exists.
The ZIP is verified with CRC and SHA-256 and gets a `.zip.sha256` sidecar. It
contains private biometric material: keep it outside the public repository.
Synthetic reviews always retain `human_annotation=false` and are never human GT.

New photos already inspected during debugging are diagnostic development data,
not a pristine final holdout. Capture-group fields are optional human declarations
and remain unverified. Do not claim person independence or split consecutive
photos of one session into independent groups. This tool does not append data
to the fixed GT10 protocol or approve a new model. Dataset preparation, grouped
evaluation, and a fresh final test require a separate recorded protocol.

## Verification

```powershell
cd ai/scripts
python -m unittest test_photo_pad_annotation_v1 -v
```

Synthetic tests cover non-square EXIF 1–8 round trips, drafts, explicit review,
negative/ambiguous labels, conflicts, interrupted publication/retry, source and
review-asset tampering, binary masks, original-byte preservation, verified export,
and loopback session/Host/Origin checks. Browser checks additionally exercise
polygon add/erase, navigation/reload, review, and export. These validate the tool;
they do not establish detector accuracy or protection performance.
