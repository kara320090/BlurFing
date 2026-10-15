# Independent protection runtime source snapshot

V12 native PHOTO and V13 distal geometry entrypoints retain a separate
protection source inventory before work and compare it after work. This
does not modify the V6 training protocol, its existing 16-file source hash,
checkpoint, learned mask, thresholds, renderer math or default pipeline.

`protection_runtime_sources_v1.py` inventories public source files under
the AI root's `scripts/` and `platform/` directories, recursively. Selected
suffixes are Python, Java, PowerShell and C/C++ source/header files. This
includes the previously omitted context, crop, router, canonical ROI,
platform SourceAFIS loader and Java worker dependencies without maintaining
another manual list of imported filenames.

The manifest uses sorted AI-root-relative POSIX paths and SHA256 of exact
file bytes. It includes a digest of the complete sorted source map, so
changed files, added source files, deleted source files and renamed paths
are detected. Copies at different absolute roots yield the same manifest
when selected bytes and relative names match. Timestamps are not used as
content identity. Private absolute source roots are not serialized.

Environment/site-packages, third-party/vendor directories, caches, weights
and private directories are excluded. Non-source photos, masks, JSON
outputs, model weights, bytecode and compiled Java classes are not read.
Source-directory symlinks/junctions and selected file symlinks/reparse points
are rejected; selected files must resolve within the fixed AI root.
Unreadable/missing mandatory source directories cannot silently shrink the
manifest. The source map is immutable after capture.

The native `run`/`protect_bundle` and distal `run`/`protect_prepared` results
add `runtime_source_snapshot` provenance. The final result adds
`runtime_source_snapshot_verified=true` only after the complete before/after
comparison passes. Per-image intermediate reports carry capture provenance;
their enclosing batch result certifies the final source-set comparison.
The previous curated `protection_code_sha256`/`runtime_code_sha256` fields
remain available for compatibility.

This snapshot describes public protection source bytes. External models,
runtime configuration, scientific packages, JARs and compiled binaries keep
their existing separate asset/hash contracts; they are not folded into the
frozen training hash. A source inventory is not detector accuracy, Linux
equivalence, loaded-process attestation or a privacy/security proof.

Regression tests use synthetic sources and mocked pipeline IO. They cover
previously omitted dependency edits, new/deleted source, same-size edits
with restored timestamps, ignored outputs/private assets, root-relative
determinism, actual symlink/junction rejection, immutable snapshots, all
four guarded entrypoints and compatibility with the frozen V6 training hash.
No actual input, model inference or renderer must rerun to verify this
source-provenance change.
