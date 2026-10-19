"""Private subprocess adapter for the existing scanner renderer and SourceAFIS.

No model training, PHOTO fallback, threshold tuning, percentage conversion, or
biometric artifacts are written outside the caller's private temporary root.
"""
import argparse
import base64
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(source, output, ai_root, dpi):
    import numpy as np
    from PIL import Image
    sys.path.insert(0, str(ai_root / "scripts"))

    before = source.read_bytes()
    with Image.open(source) as image:
        original = np.asarray(image.convert("RGB")).copy()
    from fingerprint_input_router import route_input
    if route_input(original).get("input_type") != "FINGERPRINT_IMAGE":
        raise ValueError("SCANNER_INPUT_REQUIRED")
    from protect_fingerprint import protect_image
    returned, report = protect_image(source, output / "protection")
    if report.get("input_type") != "fingerprint_image":
        raise ValueError("SCANNER_INPUT_REQUIRED")
    if source.read_bytes() != before or returned.shape != original.shape or returned.dtype != np.uint8:
        raise ValueError("SCANNER_RESULT_INVALID")
    if not np.array_equal(returned[:, :, 0], returned[:, :, 1]) or not np.array_equal(returned[:, :, 1], returned[:, :, 2]):
        raise ValueError("SCANNER_RESULT_INVALID")
    processed = output / "processed.png"
    Image.fromarray(returned[:, :, 0]).save(processed)
    png = processed.read_bytes()
    changed = int(np.any(original != returned, axis=2).sum())
    status = report.get("status")
    if status not in ("success", "partial_success", "rejected") or (status == "rejected" and changed):
        raise ValueError("SCANNER_RESULT_INVALID")
    match = dict(status="unavailable", score=None, engine="SourceAFIS", engine_version=None,
                 dpi=dpi, probe_minutiae=None, candidate_minutiae=None, measured_at=None)
    try:
        from sourceafis_matcher import run_matcher_job
        raw = run_matcher_job({"original": source, "processed": processed},
            [{"key": "original_processed", "probe": "original", "candidate": "processed"}],
            dpi=float(dpi), run_name="scanner_comparison")
        pair = raw["pairs"][0]
        counts = [pair.get("probe_minutiae"), pair.get("candidate_minutiae")]
        if pair.get("status") != "ok" or any(type(n) is not int or n < 0 for n in counts):
            raise ValueError("MATCHER_FAILED")
        match.update(engine_version=raw["sourceafis_version"], probe_minutiae=counts[0], candidate_minutiae=counts[1])
        if min(counts) == 0:
            match["status"] = "unmeasurable"
        else:
            score = pair["score"]
            if type(score) not in (int, float) or not math.isfinite(score) or score < 0:
                raise ValueError("MATCHER_FAILED")
            match.update(status="measured", score=score, measured_at=datetime.now(timezone.utc).isoformat())
    except Exception:
        # Keep a valid AI image even if a separately installed matcher is absent.
        match.update(status="unavailable", score=None, measured_at=None)
    return dict(processed_image_base64=base64.b64encode(png).decode("ascii"),
        processed_sha256=hashlib.sha256(png).hexdigest(), width=original.shape[1], height=original.shape[0],
        protection_status=status, protection_engine="blurfing-scanner-experimental", changed_pixels=changed,
        match=match)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ai-root", type=Path, required=True)
    parser.add_argument("--dpi", type=int, required=True)
    args = parser.parse_args()
    args.output.mkdir()
    try:
        payload = run(args.input, args.output, args.ai_root, args.dpi)
        (args.output / "transport.json").write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    except Exception as error:
        # Paths, templates and native stdout/stderr are never HTTP error messages.
        sys.exit(3 if isinstance(error, ValueError) and str(error) == "SCANNER_INPUT_REQUIRED" else 1)
