# PHOTO adapter v2 memory safety

`photo_coarse_adapter_v2` preserves the historical v1 adapter and unchanged detector, width normalization formula, pitch rules, feature criteria and frozen renderer mathematics. The PHOTO quality gate now selects v2. This is a post-holdout safety version, not a new independent accuracy evaluation.

The historical crash was caused by one large coarse component and ten tiny components. Their diameter median was 2 pixels; the unchanged width normalization formula `400 / median_diameter` produced scale 200. An RGB uint8 source of 726 x 862 therefore requested a 145200 x 172400 buffer: 25,032,480,000 pixels and 75,097,440,000 bytes. This was not an integer overflow or width/height swap. The mask, component count and measured diameters are retained; no component cleanup was added.

## Deterministic implementation contract

Before resize, validate finite positive scale and dimensions, integer dimensions/channel sizes and the calculated allocation using Python arbitrary-precision integer products. Historical rounding remains unchanged. Reject instead of clamping or downscaling:

- maximum working dimension: 32768;
- maximum working raster: 32 MiPixels;
- planning estimate: 64 bytes per working pixel for multiple gray/RGB/mask/distance/renderer buffers;
- maximum planning estimate: 2 GiB.

These fixed engineering limits bound multi-buffer camera processing, including the existing 400-pixel width normalization. They are resource limits, not learned thresholds or target performance settings. The 64-byte planning estimate is not a measured RSS or guarantee about total process memory, TensorFlow or other processes. Shared square-padding dimensions are checked as well. Inputs outside the supported envelope return `adapter_memory_limit_exceeded`; malformed/nonfinite requests return `adapter_resize_invalid`. No requested scale or pitch is silently substituted.

A rejected allocation returns the exact source RGB and one rejected outcome for each unchanged coarse component. All components remain visible in metadata, including tiny semantic fragments; these counts do not certify actual fingerprints. Native masks are not expanded. No renderer runs for the rejected request. The public result contains `adapter_version` and `resize_audit`.

The v1 adapter remains directly available for historical reproduction. Its numerical behavior is not patched. Tests cover finite/invalid/huge dimensions, huge integer products, extreme aspect ratios, deterministic rejection and bbox clipping. Normal PHOTO and scanner results are compared to prior pixel references.

## Canonical input design, not enabled in this safety version

The current unified API still accepts RGB and L only. A future separately versioned canonical decoder can replicate L into three RGB channels; discard RGBA alpha only when every alpha value is opaque; otherwise require an explicit caller-selected compositing background and record it. Nonopaque alpha must never be silently discarded. Preserve native dimensions, source bytes/hash and the EXIF coordinate contract; reject unconfigured high-bit-depth/dynamic-range conversion. This design is not applied to the historical holdout or this RGB retry.

## Evaluation and Windows

Results are `PROTOCOL_AMENDED_OPERATIONAL_VALIDATION` / `POST_HOLDOUT_ADAPTER_FIX`, never pristine untouched independent validation. Original reports stay frozen. Independent validation and PHOTO production approval remain false.

For actual Windows parity use the same source version, configured runtimes and the newly generated private reference kit. Run its PowerShell script with the AI source directory. It contains private sources and outputs and must not be uploaded. Rejection parity alone does not verify successful PHOTO rendering: include successful PHOTO development and scanner reference cases and GUI checks. Actual Windows measurements remain required.
