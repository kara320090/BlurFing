import os
import cv2
import mediapipe as mp
import numpy as np


class FingertipCropper:

  def __init__(self, min_detection_confidence=0.5, padding_ratio=1.2):
    """padding_ratio: 끝마디 관절 간 거리에 곱해줄 패딩 계수 (1.0~1.3 권장)"""
    self.mp_hands = mp.solutions.hands
    self.hands = self.mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=2,
        min_detection_confidence=min_detection_confidence,
    )
    self.padding_ratio = padding_ratio

    # (손가락 식별자, Tip 랜드마크 번호, 직전 마디 관절 번호)
    self.finger_map = [
        ("thumb", 4, 3),  # 엄지: IP 관절(3) 기준
        ("index", 8, 7),  # 검지: DIP 관절(7) 기준
        ("middle", 12, 11),  # 중지: DIP 관절(11) 기준
        ("ring", 16, 15),  # 약지: DIP 관절(15) 기준
        ("pinky", 20, 19),  # 소지: DIP 관절(19) 기준
    ]

  def process_image(self, image_path, min_crop_size=20):
    """이미지 한 장을 받아 검출된 손끝 패치 리스트를 반환합니다.

    Returns:
        list of dict: [ { 'finger_id': ..., 'bbox': (x1, y1, x2, y2),
        'crop_img': ndarray, 'tip_coord': (cx, cy) } ]
    """
    image = cv2.imread(image_path)
    if image is None:
      print(f"[Error] 이미지를 불러올 수 없습니다: {image_path}")
      return []

    h, w, _ = image.shape
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = self.hands.process(image_rgb)

    cropped_results = []

    if not results.multi_hand_landmarks:
      print(f"[Info] 손을 검출하지 못했습니다: {image_path}")
      return []

    for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
      for name, tip_idx, joint_idx in self.finger_map:
        tip = hand_landmarks.landmark[tip_idx]
        joint = hand_landmarks.landmark[joint_idx]

        # 픽셀 절대 좌표 변환
        cx, cy = int(tip.x * w), int(tip.y * h)
        jx, jy = int(joint.x * w), int(joint.y * h)

        # 관절 간 거리 기반 동적 패딩 반지름 계산
        joint_distance = np.hypot(cx - jx, cy - jy)
        radius = int(joint_distance * self.padding_ratio)

        # 이미지 경계를 벗어나지 않도록 좌표 클리핑 (예외처리)
        x1 = max(0, cx - radius)
        y1 = max(0, cy - radius)
        x2 = min(w, cx + radius)
        y2 = min(h, cy + radius)

        # 유효 크기 검증 (너무 작거나 슬라이싱 오류 방지)
        crop_h, crop_w = y2 - y1, x2 - x1
        if crop_h < min_crop_size or crop_w < min_crop_size:
          continue

        crop_patch = image[y1:y2, x1:x2].copy()

        cropped_results.append({
            "finger_id": f"hand_{hand_idx}_{name}",
            "bbox": (x1, y1, x2, y2),
            "crop_img": crop_patch,
            "tip_coord": (cx, cy),
        })

    return cropped_results


# --- 테스트 실행부 ---
if __name__ == "__main__":
  cropper = FingertipCropper(padding_ratio=1.2)

  # 테스트할 이미지 경로 설정 (11k Hands 사진 또는 직접 찍은 사진 경로)
  test_image_path = "test_hand.jpg"
  output_dir = "finger_patches_output"
  os.makedirs(output_dir, exist_ok=True)

  if os.path.exists(test_image_path):
    results = cropper.process_image(test_image_path)
    print(f"총 {len(results)}개의 손끝 패치가 검출되었습니다.")

    for item in results:
      finger_id = item["finger_id"]
      bbox = item["bbox"]
      patch = item["crop_img"]

      save_path = os.path.join(output_dir, f"{finger_id}.png")
      cv2.imwrite(save_path, patch)
      print(f" - {finger_id} 저장 완료 | BBox: {bbox} | 크기: {patch.shape[:2]}")
  else:
    print(
        f"'{test_image_path}' 파일이 경로에 없습니다. 테스트할 사진 파일명을"
        " 지정해주세요."
    )