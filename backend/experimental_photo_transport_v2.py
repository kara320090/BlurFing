"""Strict server validation of the opt-in photo V2 transport.

The trusted AI bridge validates component labels and native gate evidence.
This boundary independently checks the actual HTTP source, returned RGB and
full-resolution accepted/rejected masks. Rectangles are display metadata only.
"""
import base64
import binascii
import hashlib
import io
import math
import re
import struct
from dataclasses import dataclass

import numpy as np
from PIL import Image
from native_photo_result_contract_v1 import _png_preflight
try:
    import cv2
except ImportError:
    cv2=None

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_COMPONENTS = 256
MAX_TRANSPORT_BYTES = 64 * 1024 * 1024
ENGINE_METHODS = {
    "native_v12": "photo_native_v12_experimental",
    "distal_v13": "photo_distal_v13_geometry_experimental",
    "pose_v14": "photo_pose_v14_geometry_experimental",
    "synthetic_v23": "photo_synthetic_v23_automatic_experimental",
}
RESPONSE_KEYS = frozenset({
    "contract_version", "request_id", "result_kind", "method", "photo_engine", "status",
    "image_base64", "mime_type", "image_width", "image_height", "source_exif_orientation",
    "coordinate_system", "source_sha256", "source_RGB_sha256", "returned_RGB_sha256",
    "candidate_components", "transformed_components", "rejected_components", "changed_RGB_pixels",
    "accepted_permission_mask", "rejected_permission_mask", "region_display_bounds",
    "bounds_are_not_filled_permission", "processing_ms", "warnings", "privacy_validated",
    "production_approved", "complete_photo_protection_verified", "independent_final_test", "evaluation",
})
MASK_KEYS = frozenset({"encoding", "image_base64", "png_sha256", "boolean_pixel_sha256", "pixels"})
REGION_KEYS = frozenset({
    "region_id", "status", "reason_code", "mask_pixels", "changed_RGB_pixels",
    "permission_boolean_sha256", "x", "y", "width", "height", "bounds_are_not_filled_permission",
})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class TransportValidationError(ValueError):
    """Contains a fixed code only, never processor data or private paths."""


def integer(value, maximum, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= maximum:
        raise TransportValidationError("invalid_integer")
    return value


def digest(value):
    return hashlib.sha256(value).hexdigest()


def array_digest(value):
    return digest(value.tobytes(order="C"))


def warnings_for(engine, rejected, precautionary=False):
    warnings = ["EXPERIMENTAL_UNAPPROVED", "UNDETECTED_FINGERPRINTS_POSSIBLE",
                "COUNTS_ARE_PERMISSION_COMPONENTS_NOT_FINGERS"]
    if rejected:
        warnings.append("REJECTED_REGIONS_RETAIN_ORIGINAL_PIXELS")
    if engine == "distal_v13":
        warnings.append("GEOMETRY_BOUNDARIES_REQUIRE_REVIEW_ACCURACY_REGRESSION_OBSERVED")
    if engine == "pose_v14":
        warnings.append("POSE_GEOMETRY_BOUNDARIES_REQUIRE_REVIEW")
    if engine == "synthetic_v23":
        warnings.extend(["AUTOMATIC_VISIBILITY_UNCALIBRATED", "SYNTHETIC_REPLACEMENT_V23"])
        if precautionary:
            warnings.append("PRECAUTIONARY_SURFACE_WITHOUT_RIDGE_CONFIRMATION")
    return warnings


def decode_png(content, *, mode, expected_size=None):
    """Check IHDR before any pixel allocation; do not convert or resize."""
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_IMAGE_BYTES:
        raise TransportValidationError("PNG_byte_limit")
    if (len(content) < 33 or content[:8] != b"\x89PNG\r\n\x1a\n" or
            content[8:16] != b"\x00\x00\x00\x0dIHDR"):
        raise TransportValidationError("PNG_required")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", content[16:29])
    if not 0 < width * height <= MAX_PIXELS:
        raise TransportValidationError("PNG_pixel_limit")
    if (depth != 8 or color != {"RGB": 2, "L": 0}[mode] or compression != 0 or
            filtering != 0 or interlace != 0):
        raise TransportValidationError("PNG_8bit_mode_required")
    if expected_size is not None and (width, height) != expected_size:
        raise TransportValidationError("PNG_shape_mismatch")
    try:
        _png_preflight(content, {"RGB": 2, "L": 0}[mode])
    except ValueError as exc:
        raise TransportValidationError("noncanonical_PNG") from exc
    try:
        if cv2 is not None:
            # Preflight already checks every chunk, EXIF=1, CRC, exact bounded
            # scanline stream and opaque RGB8/L8. Decode those same pixels;
            # never let a native decoder apply orientation or color conversion.
            result=cv2.imdecode(np.frombuffer(content,np.uint8),cv2.IMREAD_UNCHANGED)
            shape=(height,width,3) if mode=='RGB' else (height,width)
            if result is None or result.shape!=shape:raise TransportValidationError('PNG_mode_or_frames')
            if mode=='RGB':result=cv2.cvtColor(result,cv2.COLOR_BGR2RGB)
        else:
            with Image.open(io.BytesIO(content)) as image:
                if (image.format != "PNG" or image.mode != mode or getattr(image, "n_frames", 1) != 1 or
                        image.size != (width, height)):
                    raise TransportValidationError("PNG_mode_or_frames")
                orientation = image.getexif().get(274, 1)
                if type(orientation) is not int or orientation != 1:
                    raise TransportValidationError("PNG_EXIF_1_required")
                image.load()
                result = np.asarray(image).copy()
    except TransportValidationError:
        raise
    except Exception as exc:
        raise TransportValidationError("invalid_PNG") from exc
    if result.dtype != np.uint8:
        raise TransportValidationError("PNG_uint8_required")
    return result


@dataclass(frozen=True)
class UploadedPhoto:
    content: bytes
    rgb: np.ndarray
    source_sha256: str
    rgb_sha256: str

    @classmethod
    def decode(cls, content):
        rgb = decode_png(content, mode="RGB")
        return cls(content, rgb, digest(content), array_digest(rgb))


def _base64_png(value):
    if not isinstance(value, str) or not value or len(value) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise TransportValidationError("invalid_base64_size")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise TransportValidationError("invalid_base64") from exc


def _mask(value, size):
    if not isinstance(value, dict) or set(value) != MASK_KEYS or value.get("encoding") != "png_uint8_0_255":
        raise TransportValidationError("mask_contract")
    content = _base64_png(value.get("image_base64"))
    pixels = decode_png(content, mode="L", expected_size=size)
    if np.any((pixels != 0) & (pixels != 255)):
        raise TransportValidationError("binary_mask_required")
    mask = pixels > 0
    if (value.get("png_sha256") != digest(content) or value.get("boolean_pixel_sha256") != array_digest(mask) or
            integer(value.get("pixels"), MAX_PIXELS) != int(mask.sum())):
        raise TransportValidationError("mask_hash_or_count")
    return mask


def validate_transport(value, upload, *, request_id, engine):
    """Return the same strict, sanitized JSON dictionary after validation."""
    if not isinstance(value, dict) or set(value) != RESPONSE_KEYS:
        raise TransportValidationError("response_fields")
    height, width = upload.rgb.shape[:2]
    if (engine not in ENGINE_METHODS or value.get("photo_engine") != engine or
            value.get("method") != ENGINE_METHODS[engine] or value.get("request_id") != request_id or
            value.get("contract_version") != "photo-experimental-v2" or
            value.get("result_kind") != "experimental" or value.get("mime_type") != "image/png" or
            value.get("coordinate_system") != "encoded_original_pixels" or
            type(value.get("source_exif_orientation")) is not int or value["source_exif_orientation"] != 1):
        raise TransportValidationError("response_identity")
    if (integer(value.get("image_width"), MAX_PIXELS, positive=True) != width or
            integer(value.get("image_height"), MAX_PIXELS, positive=True) != height or
            value.get("source_sha256") != upload.source_sha256 or value.get("source_RGB_sha256") != upload.rgb_sha256):
        raise TransportValidationError("source_binding")
    for key in ("privacy_validated", "production_approved", "complete_photo_protection_verified", "independent_final_test"):
        if value.get(key) is not False:
            raise TransportValidationError("unapproved_experiment_required")
    if value.get("evaluation") is not None or value.get("bounds_are_not_filled_permission") is not True:
        raise TransportValidationError("display_only_bounds_required")
    integer(value.get("processing_ms"), 2**63 - 1)
    returned = decode_png(_base64_png(value.get("image_base64")), mode="RGB", expected_size=(width, height))
    if value.get("returned_RGB_sha256") != array_digest(returned):
        raise TransportValidationError("returned_RGB_hash")
    accepted = _mask(value.get("accepted_permission_mask"), (width, height))
    rejected = _mask(value.get("rejected_permission_mask"), (width, height))
    changed = (cv2.cvtColor(cv2.compare(returned,upload.rgb,cv2.CMP_NE),cv2.COLOR_RGB2GRAY)>0
        if cv2 is not None else np.any(returned != upload.rgb, axis=2))
    if np.any(accepted & rejected) or np.any(changed & ~accepted):
        raise TransportValidationError("accepted_rejected_changed_partition")
    count = integer(value.get("candidate_components"), MAX_COMPONENTS)
    transformed_count = integer(value.get("transformed_components"), MAX_COMPONENTS)
    rejected_count = integer(value.get("rejected_components"), MAX_COMPONENTS)
    changed_count = integer(value.get("changed_RGB_pixels"), MAX_PIXELS)
    expected_status = "success" if transformed_count and transformed_count == count else "partial_success" if transformed_count else "rejected"
    if (count != transformed_count + rejected_count or value.get("status") != expected_status or
            changed_count != int(changed.sum()) or (transformed_count == 0) != (changed_count == 0)):
        raise TransportValidationError("status_counts_or_warnings")
    rows = value.get("region_display_bounds")
    if not isinstance(rows, list) or len(rows) != count:
        raise TransportValidationError("display_region_count")
    ids = set()
    pixel_sums = {"transformed": 0, "rejected": 0}
    change_sum = 0
    actual_transformed = 0
    precautionary = False
    for row in rows:
        if not isinstance(row, dict) or set(row) != REGION_KEYS:
            raise TransportValidationError("display_region_fields")
        region_id = integer(row.get("region_id"), 65535, positive=True)
        if region_id in ids:
            raise TransportValidationError("duplicate_region_id")
        ids.add(region_id)
        state = row.get("status")
        if state not in pixel_sums or row.get("bounds_are_not_filled_permission") is not True:
            raise TransportValidationError("display_region_state")
        reason = row.get("reason_code")
        is_surface=engine=="synthetic_v23" and reason=="TRANSFORMED_PRECAUTIONARY_SURFACE"
        if ((state == "transformed" and reason != "TRANSFORMED" and not is_surface) or
                (state == "rejected" and (not isinstance(reason, str) or re.fullmatch(r"REJECT_[A-Z0-9_]{1,80}", reason) is None))):
            raise TransportValidationError("sanitized_reason_required")
        precautionary |= state=="transformed" and is_surface
        region_pixels = integer(row.get("mask_pixels"), MAX_PIXELS, positive=True)
        changes = integer(row.get("changed_RGB_pixels"), region_pixels)
        if (state == "transformed" and changes == 0) or (state == "rejected" and changes != 0):
            raise TransportValidationError("display_region_change_state")
        if not isinstance(row.get("permission_boolean_sha256"), str) or SHA256.fullmatch(row["permission_boolean_sha256"]) is None:
            raise TransportValidationError("display_region_hash")
        coordinates = []
        for key in ("x", "y", "width", "height"):
            coordinate = row.get(key)
            if type(coordinate) not in (int, float) or not math.isfinite(coordinate):
                raise TransportValidationError("finite_display_coordinate")
            coordinates.append(coordinate)
        x, y, w, h = coordinates
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 1 + 1e-12 or y + h > 1 + 1e-12:
            raise TransportValidationError("normalized_display_bounds")
        pixel_sums[state] += region_pixels
        change_sum += changes
        actual_transformed += int(state == "transformed")
    if (actual_transformed != transformed_count or pixel_sums["transformed"] != int(accepted.sum()) or
            pixel_sums["rejected"] != int(rejected.sum()) or change_sum != changed_count):
        raise TransportValidationError("display_region_aggregate")
    if value.get("warnings") != warnings_for(engine, rejected_count, precautionary):
        raise TransportValidationError("status_counts_or_warnings")
    return value
