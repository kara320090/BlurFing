import csv
import glob
import os
import cv2
import numpy as np

# 아이폰 ProRAW (.dng) 지원 여부 확인
try:
  import rawpy

  HAS_RAWPY = True
except ImportError:
  HAS_RAWPY = False


class RidgeCoherenceFingerprintPreprocessor:

  def __init__(self, standard_size=320, blur_thresh=12.0):
    self.standard_size = standard_size
    self.blur_thresh = blur_thresh
    # 16방향 대칭 가버 필터 뱅크 사전 생성 (320x320 기준 융선 주기 lambda=7.5 최적화)
    self.num_angles = 16
    self.gabor_kernels = self._build_gabor_bank(
        ksize=15, sigma=2.6, lambd=7.5, gamma=0.5
    )

  def _build_gabor_bank(self, ksize, sigma, lambd, gamma):
    kernels = []
    for i in range(self.num_angles):
      theta = i * (np.pi / self.num_angles)
      kern = cv2.getGaborKernel(
          (ksize, ksize),
          sigma=sigma,
          theta=theta,
          lambd=lambd,
          gamma=gamma,
          psi=0,
          ktype=cv2.CV_32F,
      )
      kern -= np.mean(kern)
      kernels.append(kern)
    return kernels

  def load_image(self, img_path):
    ext = os.path.splitext(img_path)[1].lower()
    if ext == ".dng":
      if not HAS_RAWPY:
        print(
            f"[!] {os.path.basename(img_path)}: .dng 처리를 위해 'pip install"
            " rawpy'가 필요합니다."
        )
        return None
      with rawpy.imread(img_path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True, no_auto_bright=True, output_bps=8
        )
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    else:
      stream = np.fromfile(img_path, dtype=np.uint8)
      return cv2.imdecode(stream, cv2.IMREAD_COLOR)

  def detect_and_crop_finger_core(self, img):
    """배경 사물을 배제하고 주기적인 방향성 융선이 존재하는 실제 손가락 영역만 정밀 추적"""
    orig_h, orig_w = img.shape[:2]

    scale = 640.0 / max(orig_h, orig_w)
    work_w, work_h = int(orig_w * scale), int(orig_h * scale)
    work_img = cv2.resize(img, (work_w, work_h), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(work_img, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    norm_g = clahe.apply(gray).astype(np.float32)

    hp = norm_g - cv2.GaussianBlur(norm_g, (0, 0), 2.2)
    hp_clipped = np.clip(hp, -25.0, 25.0)

    gx = cv2.Sobel(hp_clipped, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(hp_clipped, cv2.CV_32F, 0, 1, ksize=3)

    gxx = cv2.GaussianBlur(gx**2, (0, 0), 8.0)
    gyy = cv2.GaussianBlur(gy**2, (0, 0), 8.0)
    gxy = cv2.GaussianBlur(gx * gy, (0, 0), 8.0)

    coherence = np.sqrt((gxx - gyy) ** 2 + 4 * (gxy**2)) / (gxx + gyy + 1e-5)
    rms_energy = np.sqrt(cv2.GaussianBlur(hp_clipped**2, (0, 0), 8.0))

    ycrcb = cv2.cvtColor(work_img, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb[:, :, 1].astype(np.float32)
    is_grayscale = np.std(work_img[:, :, 0] - work_img[:, :, 2]) < 2.0
    if is_grayscale:
      skin_weight = np.ones_like(coherence)
    else:
      skin_weight = np.where((cr >= 128) & (cr <= 185), 1.2, 0.7).astype(
          np.float32
      )

    ridge_prob = (coherence * skin_weight > 0.30) & (rms_energy > 9.5)
    cand_mask = (ridge_prob.astype(np.uint8)) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    cand_mask = cv2.morphologyEx(cand_mask, cv2.MORPH_CLOSE, kernel)
    cand_mask = cv2.morphologyEx(cand_mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(
        cand_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
      return None, None

    best_cnt = None
    best_score = -1.0
    for cnt in contours:
      area = cv2.contourArea(cnt)
      if area < (work_h * work_w * 0.015):
        continue
      temp_m = np.zeros_like(cand_mask)
      cv2.drawContours(temp_m, [cnt], -1, 255, -1)
      mean_coh = cv2.mean(coherence, mask=temp_m)[0]
      score = area * (mean_coh**2)
      if score > best_score:
        best_score = score
        best_cnt = cnt

    if best_cnt is None:
      return None, None

    hull = cv2.convexHull(best_cnt)
    finger_mask_work = np.zeros_like(cand_mask)
    cv2.drawContours(finger_mask_work, [hull], -1, 255, -1)

    x, y, bw, bh = cv2.boundingRect(hull)
    if bh > int(bw * 1.35):
      bh = int(bw * 1.35)

    cx = x + bw // 2
    cy = y + bh // 2
    half_side = int(max(bw, bh) * 0.52)

    wx1, wy1 = max(0, cx - half_side), max(0, cy - half_side)
    wx2, wy2 = min(work_w, cx + half_side), min(work_h, cy + half_side)

    ox1, oy1 = int(wx1 / scale), int(wy1 / scale)
    ox2, oy2 = int(wx2 / scale), int(wy2 / scale)

    crop_orig = img[oy1:oy2, ox1:ox2].copy()
    crop_mask_work = finger_mask_work[wy1:wy2, wx1:wx2].copy()

    crop_std = cv2.resize(
        crop_orig,
        (self.standard_size, self.standard_size),
        interpolation=cv2.INTER_LANCZOS4,
    )
    mask_std = cv2.resize(
        crop_mask_work,
        (self.standard_size, self.standard_size),
        interpolation=cv2.INTER_NEAREST,
    )

    return crop_std, mask_std

  def build_eroded_core_mask(self, crop_std, mask_std):
    """손끝 외곽 테두리선과 외부 배경을 깎아내는 내부 침식 마스크"""
    h, w = crop_std.shape[:2]

    erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (29, 29))
    inner_mask = cv2.erode(mask_std, erode_kernel, iterations=1)

    M = cv2.moments(inner_mask)
    if M["m00"] > 0:
      mcx = int(M["m10"] / M["m00"])
      mcy = int(M["m01"] / M["m00"])
    else:
      mcx, mcy = w // 2, h // 2

    ellipse = np.zeros((h, w), dtype=np.uint8)
    cv2.ellipse(
        ellipse, (mcx, mcy), (int(w * 0.40), int(h * 0.42)), 0, 0, 360, 255, -1
    )

    safe_mask = cv2.bitwise_and(inner_mask, ellipse)
    return safe_mask

  def extract_gabor_ridge(self, crop_std, mask_std):
    """16방향 적응형 가버 필터 기반 융선 및 세선화 추출"""
    gray = cv2.cvtColor(crop_std, cv2.COLOR_BGR2GRAY)

    safe_mask = self.build_eroded_core_mask(crop_std, mask_std)
    if np.sum(safe_mask == 255) < 2000:
      return None, None, None, "MASK_TOO_SMALL"

    blur_val = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_val < self.blur_thresh:
      return None, None, None, f"BLUR({blur_val:.1f})"

    clahe = cv2.createCLAHE(clipLimit=3.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    f_img = enhanced.astype(np.float32)
    bandpass = cv2.GaussianBlur(f_img, (0, 0), 0.8) - cv2.GaussianBlur(
        f_img, (0, 0), 4.2
    )

    gx = cv2.Sobel(bandpass, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(bandpass, cv2.CV_32F, 0, 1, ksize=3)
    Gxx = cv2.GaussianBlur(gx**2, (0, 0), 7.0)
    Gyy = cv2.GaussianBlur(gy**2, (0, 0), 7.0)
    Gxy = cv2.GaussianBlur(gx * gy, (0, 0), 7.0)

    theta_normal = 0.5 * np.arctan2(2 * Gxy, Gxx - Gyy)
    angle_norm = np.mod(theta_normal, np.pi)
    angle_idx = (
        np.floor(angle_norm / (np.pi / self.num_angles)).astype(np.int32)
        % self.num_angles
    )

    responses = [
        cv2.filter2D(bandpass, cv2.CV_32F, k) for k in self.gabor_kernels
    ]
    resp_stack = np.stack(responses, axis=0)

    Y, X = np.indices(gray.shape)
    oriented_ridge_resp = resp_stack[angle_idx, Y, X]

    binary_ridge = np.where(
        (oriented_ridge_resp > 0) & (safe_mask == 255), 255, 0
    ).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary_ridge, connectivity=8
    )
    clean_ridge = np.zeros_like(binary_ridge)
    for i in range(1, num_labels):
      if stats[i, cv2.CC_STAT_AREA] >= 20:
        clean_ridge[labels == i] = 255

    skeleton = self.morphological_skeleton(clean_ridge)
    enhanced_masked = cv2.bitwise_and(enhanced, enhanced, mask=safe_mask)

    return enhanced_masked, clean_ridge, skeleton, f"OK(blur:{blur_val:.0f})"

  def morphological_skeleton(self, binary_img):
    skel = np.zeros(binary_img.shape, np.uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    temp = binary_img.copy()
    while True:
      eroded = cv2.erode(temp, element)
      diff = cv2.subtract(temp, cv2.dilate(eroded, element))
      skel = cv2.bitwise_or(skel, diff)
      temp = eroded.copy()
      if cv2.countNonZero(temp) == 0:
        break
    return skel

  @staticmethod
  def create_inverted_and_transparent(binary_img):
    """색상 반전(흰 배경 + 검은 지문) 및 투명 배경 누끼(BGRA) 이미지 생성"""
    # 1. 색상 반전: 지문(0, 검은색), 배경(255, 흰색)
    inverted_img = cv2.bitwise_not(binary_img)

    # 2. 투명 배경(BGRA): 지문은 (0, 0, 0, 255) 불투명 검은색, 배경은 (255, 255, 255, 0) 완전 투명
    bgra_transparent = cv2.merge(
        [inverted_img, inverted_img, inverted_img, binary_img]
    )

    return inverted_img, bgra_transparent

  def process_single_image(self, img_path, out_dir):
    fname = os.path.basename(img_path)
    base_prefix = os.path.splitext(fname)[0]
    img = self.load_image(img_path)

    if img is None:
      return {"file": fname, "status": "FAIL", "log": "이미지 로드 실패"}

    crop_std, mask_std = self.detect_and_crop_finger_core(img)
    if crop_std is None:
      return {
          "file": fname,
          "status": "REJECT",
          "log": "유효 지문 융선 영역 미검출",
      }

    enhanced_masked, clean_ridge, skeleton, msg = self.extract_gabor_ridge(
        crop_std, mask_std
    )
    if clean_ridge is None:
      return {"file": fname, "status": "REJECT", "log": msg}

    # [추가] 3번(ridge), 4번(skeleton) 이미지의 색상 반전 및 투명 배경(누끼) 버전 생성
    ridge_inv, ridge_trans = self.create_inverted_and_transparent(clean_ridge)
    skel_inv, skel_trans = self.create_inverted_and_transparent(skeleton)

    # 기존 1~4번 결과물 저장
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_1_crop.png"), crop_std
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_2_enhanced.png"), enhanced_masked
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_3_ridge.png"), clean_ridge
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_4_skeleton.png"), skeleton
    )

    # [추가 저장] 반전(흰 배경+검은 지문) 및 투명 누끼(BGRA) 파일 저장
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_3_ridge_inv.png"), ridge_inv
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_3_ridge_transparent.png"),
        ridge_trans,
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_4_skeleton_inv.png"), skel_inv
    )
    self.imwrite_safe(
        os.path.join(out_dir, f"{base_prefix}_4_skeleton_transparent.png"),
        skel_trans,
    )

    return {"file": fname, "status": "SUCCESS", "log": msg}

  @staticmethod
  def imwrite_safe(path, img):
    ext = os.path.splitext(path)[1]
    result, encoded = cv2.imencode(ext, img)
    if result:
      encoded.tofile(path)


def run_batch(input_dir, output_dir):
  os.makedirs(output_dir, exist_ok=True)
  exts = ["*.jpg", "*.jpeg", "*.png", "*.dng", "*.JPG", "*.PNG", "*.DNG"]
  files = []
  for e in exts:
    files.extend(glob.glob(os.path.join(input_dir, e)))
  files = sorted(list(set(files)))

  if not files:
    print(f"[!] 입력 폴더에 사진이 없습니다: {input_dir}")
    return

  print(f"\n=======================================================")
  print(f"   지문 전처리 및 투명 누끼 생성 파이프라인 구동 (총 {len(files)}장)")
  print(f"=======================================================\n")

  processor = RidgeCoherenceFingerprintPreprocessor()
  rows = []
  success_cnt = 0

  for idx, fpath in enumerate(files, 1):
    res = processor.process_single_image(fpath, output_dir)
    rows.append(res)
    if res["status"] == "SUCCESS":
      success_cnt += 1
      print(f"[{idx:03d}/{len(files):03d}] {res['file']} -> [성공] {res['log']}")
    else:
      print(f"[{idx:03d}/{len(files):03d}] {res['file']} -> [제외] {res['log']}")

  csv_path = os.path.join(output_dir, "preprocessing_report.csv")
  with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["file", "status", "log"])
    writer.writeheader()
    writer.writerows(rows)

  print(f"\n=======================================================")
  print(f" - 처리 완료: {success_cnt}/{len(files)}장 성공")
  print(f" - 저장 위치: {output_dir}")
  print(f"=======================================================\n")


if __name__ == "__main__":
  INPUT_FOLDER = r"C:\Users\jhs\Desktop\새 폴더"
  OUTPUT_FOLDER = r"C:\Users\jhs\Desktop\새 폴더\preprocessed_output"

  run_batch(INPUT_FOLDER, OUTPUT_FOLDER)