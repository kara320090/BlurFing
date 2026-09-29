import os
import site
import cv2
import numpy as np

# Windows MediaPipe C++ 바이너리 경로 인식 버그(한글/공백 경로) 패치
for p in site.getsitepackages():
  mp_path = os.path.join(p, "mediapipe")
  if os.path.exists(mp_path):
    os.environ["MEDIAPIPE_RESOURCE_DIR"] = mp_path
    break

import mediapipe.python.solutions.hands as mp_hands


class FingerprintExtractor:

  def __init__(self, min_detection_confidence=0.5, padding_ratio=1.2):
    self.hands = mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=2,
        min_detection_confidence=min_detection_confidence,
    )
    self.padding_ratio = padding_ratio

    # (손가락 식별자, Tip 랜드마크 번호, DIP/IP 관절 번호)
    self.finger_map = [
        ("thumb", 4, 3),
        ("index", 8, 7),
        ("middle", 12, 11),
        ("ring", 16, 15),
        ("pinky", 20, 19),
    ]

  def is_palmar_surface(self, crop_patches):
    """MediaPipe의 Left/Right 분류 라벨에 의존하지 않고, 크롭된 손끝 패치 내부의 피부 영역에서 '손톱(Nail)'

    존재 여부를 직접 검사하여 지문 면(Palmar)인지 손등(Dorsal)인지 판별합니다.
    """
    nail_detected_count = 0
    valid_patches = 0

    for patch in crop_patches:
      if patch is None or patch.size == 0:
        continue

      h, w = patch.shape[:2]
      # 흰 배경 및 여백 영향을 배제하기 위해 패치 중심부(60%)만 분석
      center_crop = patch[
          int(h * 0.2) : int(h * 0.8), int(w * 0.2) : int(w * 0.8)
      ]

      # 피부 영역만 선별 (YCrCb)
      ycrcb = cv2.cvtColor(center_crop, cv2.COLOR_BGR2YCrCb)
      skin_mask = cv2.inRange(
          ycrcb,
          np.array([0, 133, 77], dtype=np.uint8),
          np.array([255, 175, 130], dtype=np.uint8),
      )

      skin_pixels = center_crop[skin_mask > 0]
      if len(skin_pixels) < 50:
        continue

      valid_patches += 1

      # 피부 내부 손톱 특성 분석: 고명도(V > 185) 및 저채도(S < 55)
      hsv_skin = cv2.cvtColor(skin_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV)
      s_vals = hsv_skin[:, 0, 1]
      v_vals = hsv_skin[:, 0, 2]

      nail_ratio = np.sum((v_vals > 185) & (s_vals < 55)) / len(skin_pixels)

      # 피부 면적 중 12% 이상이 손톱 반사광이면 손톱(손등)으로 카운트
      if nail_ratio > 0.12:
        nail_detected_count += 1

    if valid_patches == 0:
      return False

    # 검사한 손가락 중 손톱이 과반수 이상 발견되면 손등(Dorsal)
    if (nail_detected_count / valid_patches) >= 0.5:
      return False

    # 손톱이 없으면 지문 면(Palmar) 확정
    return True

  def extract_skin_and_ridge(self, crop_patch):
    """손끝 패치에서 CLAHE 명암 평활화 및 순수 피부/지문 바이너리 마스크(0과 255)를

    생성합니다.
    """
    # 1. 융선 대비 극대화 (CLAHE)
    gray = cv2.cvtColor(crop_patch, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 2. 피부 영역 마스크 (YCrCb: 흰색 배경 및 잡티 분리)
    ycrcb = cv2.cvtColor(crop_patch, cv2.COLOR_BGR2YCrCb)
    lower_skin = np.array([0, 133, 77], dtype=np.uint8)
    upper_skin = np.array([255, 175, 130], dtype=np.uint8)
    skin_mask = cv2.inRange(ycrcb, lower_skin, upper_skin)

    # 3. 모폴로지 닫기(Close) 연산으로 내부 홀 채우기
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_cleaned = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel)

    # 4. 가장 큰 연결 영역(손가락 피부)만 추출
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask_cleaned
    )
    if num_labels > 1:
      largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
      final_mask = np.zeros_like(mask_cleaned)
      final_mask[labels == largest_label] = 255
    else:
      final_mask = mask_cleaned

    # 5. 배경이 0으로 날아간 융선 패치 생성
    masked_enhanced = cv2.bitwise_and(enhanced, enhanced, mask=final_mask)

    return final_mask, enhanced, masked_enhanced

  def process_image(self, image_path, min_crop_size=20):
    image = cv2.imread(image_path)
    if image is None:
      print(f"[Error] 이미지를 찾을 수 없습니다: {image_path}")
      return []

    h, w, _ = image.shape
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = self.hands.process(image_rgb)

    if not results.multi_hand_landmarks:
      print(f"[Info] 손이 검출되지 않았습니다: {image_path}")
      return []

    extracted_patches = []

    for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
      # 1. 5개 손가락 끝마디 사각 크롭
      temp_patches = []
      raw_crops_for_check = []

      for name, tip_idx, joint_idx in self.finger_map:
        tip = hand_landmarks.landmark[tip_idx]
        joint = hand_landmarks.landmark[joint_idx]

        cx, cy = int(tip.x * w), int(tip.y * h)
        jx, jy = int(joint.x * w), int(joint.y * h)

        # 관절 간 거리 기반 동적 반경 계산
        distance = np.hypot(cx - jx, cy - jy)
        radius = int(distance * self.padding_ratio)

        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w, cx + radius)
        y2 = min(h, cy + radius)

        if (y2 - y1) < min_crop_size or (x2 - x1) < min_crop_size:
          continue

        crop_patch = image[y1:y2, x1:x2].copy()
        temp_patches.append({
            "name": name,
            "bbox": (x1, y1, x2, y2),
            "crop": crop_patch,
        })
        raw_crops_for_check.append(crop_patch)

      # 2. 크롭된 패치들의 외형(손톱 유무)으로 지문 면 판별
      is_palmar = self.is_palmar_surface(raw_crops_for_check)

      if not is_palmar:
        print(f"[Info] 손 {hand_idx}번: 손등(손톱 면)으로 판정되어 스킵합니다.")
        continue

      print(
          f"[Success] 손 {hand_idx}번: 지문 면(Palmar) 확인 완료! 4종 데이터"
          " 생성을 시작합니다."
      )

      # 3. 지문 면인 경우 마스킹 및 융선 강화 연산 수행
      for item in temp_patches:
        mask, enhanced, masked_enhanced = self.extract_skin_and_ridge(
            item["crop"]
        )

        extracted_patches.append({
            "finger_id": f"hand_{hand_idx}_{item['name']}",
            "bbox": item["bbox"],
            "raw_crop": item["crop"],
            "enhanced": enhanced,
            "mask": mask,
            "masked_enhanced": masked_enhanced,
        })

    return extracted_patches


# --- 실행부 ---
if __name__ == "__main__":
  extractor = FingerprintExtractor(padding_ratio=1.2)

  test_image_path = "test_hand.jpg"
  output_dir = "stage4_output"
  os.makedirs(output_dir, exist_ok=True)

  if os.path.exists(test_image_path):
    results = extractor.process_image(test_image_path)
    print(f"\n최종 {len(results)}개의 유효 지문 패치 추출 완료.")

    for item in results:
      fid = item["finger_id"]
      # 1. 사각 원본 크롭
      cv2.imwrite(
          os.path.join(output_dir, f"{fid}_1_raw.png"), item["raw_crop"]
      )
      # 2. 피부/지문 바이너리 마스크 (0과 255)
      cv2.imwrite(os.path.join(output_dir, f"{fid}_2_mask.png"), item["mask"])
      # 3. CLAHE 융선 명암 강화 패치
      cv2.imwrite(
          os.path.join(output_dir, f"{fid}_3_enhanced.png"), item["enhanced"]
      )
      # 4. 마스크가 씌워진 최종 지문 패치 (배경 완전 제거본)
      cv2.imwrite(
          os.path.join(output_dir, f"{fid}_4_masked_ridge.png"),
          item["masked_enhanced"],
      )
      print(f" - {fid} 저장 완료 (BBox: {item['bbox']})")
  else:
    print(f"'{test_image_path}' 사진이 프로젝트 폴더에 없습니다.")