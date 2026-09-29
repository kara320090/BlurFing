import os
import site
import sys
import glob
import csv
import cv2
import numpy as np

# 1. [방어 1] Windows MediaPipe C++ 한글/공백 경로 인식 버그 방어
packages_paths = site.getsitepackages()
for p in packages_paths:
    mp_path = os.path.join(p, 'mediapipe')
    if os.path.exists(mp_path):
        os.environ['MEDIAPIPE_RESOURCE_DIR'] = mp_path
        break

import mediapipe.python.solutions.hands as mp_hands


class BatchFingertipPipeline:
    def __init__(self, 
                 min_detection_confidence=0.6, 
                 min_tracking_confidence=0.5,
                 padding_ratio=1.2,
                 min_patch_size=40,
                 blur_threshold=60.0):
        """
        min_patch_size: 너무 멀리서 찍힌 작은 손가락을 거르는 최소 해상도 (가로/세로 40px 미만 탈락)
        blur_threshold: 초점 나가거나 흔들린 사진을 거르는 라플라시안 분산 기준치
        """
        self.hands = mp_hands.Hands(
            static_image_mode=True,
            max_num_hands=2,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )
        self.padding_ratio = padding_ratio
        self.min_patch_size = min_patch_size
        self.blur_threshold = blur_threshold

        # (손가락명, 끝점 Tip 번호, 직전 마디 DIP/IP 번호, 뿌리 MCP 번호)
        self.finger_map = [
            ("thumb", 4, 3, 2),
            ("index", 8, 7, 5),
            ("middle", 12, 11, 9),
            ("ring", 16, 15, 13),
            ("pinky", 20, 19, 17)
        ]

    def is_palmar_surface(self, crop_patches):
        """[방어 2] MediaPipe의 Left/Right 라벨 및 회전각도와 무관하게 
        피부 내부의 손톱 반사광 존재 여부로 지문 면 판별"""
        nail_detected_count = 0
        valid_patches = 0

        for patch in crop_patches:
            if patch is None or patch.size == 0:
                continue

            h, w = patch.shape[:2]
            center_crop = patch[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]
            if center_crop.size == 0:
                continue

            ycrcb = cv2.cvtColor(center_crop, cv2.COLOR_BGR2YCrCb)
            skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77], dtype=np.uint8), 
                                           np.array([255, 175, 130], dtype=np.uint8))
            
            skin_pixels = center_crop[skin_mask > 0]
            if len(skin_pixels) < 40:
                continue

            valid_patches += 1
            hsv_skin = cv2.cvtColor(skin_pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV)
            s_vals = hsv_skin[:, 0, 1]
            v_vals = hsv_skin[:, 0, 2]

            nail_ratio = np.sum((v_vals > 185) & (s_vals < 55)) / len(skin_pixels)
            if nail_ratio > 0.12:
                nail_detected_count += 1

        if valid_patches == 0:
            return False
        return (nail_detected_count / valid_patches) < 0.5

    def check_blur(self, patch):
        """손끝 패치의 선명도(라플라시안 분산) 측정"""
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def extract_skin_and_ridge(self, crop_patch):
        """CLAHE 명암비 개선 및 배경 분리 마스크 생성"""
        gray = cv2.cvtColor(crop_patch, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        ycrcb = cv2.cvtColor(crop_patch, cv2.COLOR_BGR2YCrCb)
        lower_skin = np.array([0, 133, 77], dtype=np.uint8)
        upper_skin = np.array([255, 175, 130], dtype=np.uint8)
        skin_mask = cv2.inRange(ycrcb, lower_skin, upper_skin)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_cleaned = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_cleaned)
        if num_labels > 1:
            largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            final_mask = np.zeros_like(mask_cleaned)
            final_mask[labels == largest_label] = 255
        else:
            final_mask = mask_cleaned

        masked_enhanced = cv2.bitwise_and(enhanced, enhanced, mask=final_mask)
        return final_mask, enhanced, masked_enhanced

    def process_single_image(self, image_path, output_dir):
        """단일 이미지를 처리하고 예외 로그 및 추출 결과를 반환"""
        filename = os.path.basename(image_path)
        img = cv2.imread(image_path)
        if img is None:
            return {"file": filename, "status": "FAIL_CORRUPT", "extracted_count": 0, "reason": "이미지 로드 실패"}

        h, w, _ = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.hands.process(img_rgb)

        if not results.multi_hand_landmarks:
            return {"file": filename, "status": "FAIL_NO_HAND", "extracted_count": 0, "reason": "손 인식 불가"}

        extracted_in_image = 0
        skip_reasons = []

        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # 1단계: 각 손가락 패치 후보 추출
            temp_candidates = []
            crops_for_palmar_check = []

            for name, tip_idx, joint_idx, mcp_idx in self.finger_map:
                tip = hand_landmarks.landmark[tip_idx]
                joint = hand_landmarks.landmark[joint_idx]
                mcp = hand_landmarks.landmark[mcp_idx]

                # [방어 3: 물건 가림/Occlusion 필터링]
                # 관절 간 거리가 비정상적으로 압축되었거나 끝점 가시성(visibility) 신단
                cx, cy = int(tip.x * w), int(tip.y * h)
                jx, jy = int(joint.x * w), int(joint.y * h)
                mx, my = int(mcp.x * w), int(mcp.y * h)

                dist_tip_dip = np.hypot(cx - jx, cy - jy)
                dist_dip_mcp = np.hypot(jx - mx, jy - my)

                # 물건에 쥐여서 손가락이 완전히 접혔거나 가려져 거리가 0에 수렴할 때
                if dist_tip_dip < 5 or (dist_tip_dip / (dist_dip_mcp + 1e-6)) < 0.15:
                    skip_reasons.append(f"{name}_occluded")
                    continue

                radius = int(dist_tip_dip * self.padding_ratio)

                # [방어 4: 화면 모서리 np.clip 안전 보정]
                x1 = np.clip(cx - radius, 0, w)
                y1 = np.clip(cy - radius, 0, h)
                x2 = np.clip(cx + radius, 0, w)
                y2 = np.clip(cy + radius, 0, h)

                crop_w = x2 - x1
                crop_h = y2 - y1

                # [방어 5: 초소형 패치 필터링 (너무 멀리서 찍힌 경우)]
                if crop_w < self.min_patch_size or crop_h < self.min_patch_size:
                    skip_reasons.append(f"{name}_too_small({crop_w}x{crop_h})")
                    continue

                crop_patch = img[y1:y2, x1:x2].copy()

                # [방어 6: 모션 블러 필터링]
                blur_score = self.check_blur(crop_patch)
                if blur_score < self.blur_threshold:
                    skip_reasons.append(f"{name}_blurred({blur_score:.1f})")
                    continue

                temp_candidates.append({
                    "name": name,
                    "bbox": (x1, y1, x2, y2),
                    "crop": crop_patch,
                    "blur": blur_score
                })
                crops_for_palmar_check.append(crop_patch)

            # 지문 면(Palmar) 종합 판정
            if not self.is_palmar_surface(crops_for_palmar_check):
                skip_reasons.append(f"hand_{hand_idx}_dorsal(손등)")
                continue

            # 유효 지문 패치 저장
            for item in temp_candidates:
                mask, enhanced, masked_enhanced = self.extract_skin_and_ridge(item["crop"])
                
                # 최소 유효 피부 면적(지문 면적) 검증 (살점이 사각형의 15% 미만이면 탈락)
                if (np.sum(mask > 0) / mask.size) < 0.15:
                    skip_reasons.append(f"{item['name']}_no_skin")
                    continue

                save_prefix = f"{os.path.splitext(filename)[0]}_h{hand_idx}_{item['name']}"
                cv2.imwrite(os.path.join(output_dir, f"{save_prefix}_raw.png"), item["crop"])
                cv2.imwrite(os.path.join(output_dir, f"{save_prefix}_mask.png"), mask)
                cv2.imwrite(os.path.join(output_dir, f"{save_prefix}_enhanced.png"), enhanced)
                cv2.imwrite(os.path.join(output_dir, f"{save_prefix}_masked_ridge.png"), masked_enhanced)
                
                extracted_in_image += 1

        status = "SUCCESS" if extracted_in_image > 0 else "SKIPPED"
        return {
            "file": filename,
            "status": status,
            "extracted_count": extracted_in_image,
            "reason": ", ".join(skip_reasons) if skip_reasons else "정상 처리"
        }


# --- 100장 일괄 배치 테스트 실행기 ---
def run_batch_test(input_folder="dataset_100", output_folder="batch_result"):
    os.makedirs(output_folder, exist_ok=True)
    patches_dir = os.path.join(output_folder, "extracted_patches")
    os.makedirs(patches_dir, exist_ok=True)

    # 지원 확장자 검색
    extensions = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]
    image_paths = []
    for ext in extensions:
        image_paths.extend(glob.glob(os.path.join(input_folder, ext)))

    total_images = len(image_paths)
    if total_images == 0:
        print(f"[!] '{input_folder}' 폴더에 사진이 없습니다. 폴더 경로와 사진을 확인해주세요.")
        return

    print(f"\n=======================================================")
    print(f"       100장 일괄 자동 전처리 파이프라인 시작")
    print(f"       총 검사 대상 이미지 수: {total_images}장")
    print(f"=======================================================\n")

    pipeline = BatchFingertipPipeline()
    report_data = []

    success_images = 0
    total_patches_extracted = 0

    for idx, path in enumerate(image_paths, 1):
        result = pipeline.process_single_image(path, patches_dir)
        report_data.append(result)

        if result["status"] == "SUCCESS":
            success_images += 1
            total_patches_extracted += result["extracted_count"]
            print(f"[{idx:03d}/{total_images:03d}] {result['file']} -> 성공 ({result['extracted_count']}개 패치)")
        else:
            print(f"[{idx:03d}/{total_images:03d}] {result['file']} -> 제외 [{result['reason']}]")

    # CSV 리포트 저장 (팀 보고용)
    csv_path = os.path.join(output_folder, "batch_evaluation_report.csv")
    with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "status", "extracted_count", "reason"])
        writer.writeheader()
        writer.writerows(report_data)

    print(f"\n=======================================================")
    print(f"                  최종 배치 테스트 결과")
    print(f"=======================================================")
    print(f" - 전체 대상 이미지: {total_images}장")
    print(f" - 크롭 성공 이미지: {success_images}장 ({success_images/total_images*100:.1f}%)")
    print(f" - 총 추출 지문 패치: {total_patches_extracted}개")
    print(f" - 리포트 저장 경로 : {csv_path}")
    print(f" - 패치 저장 경로   : {patches_dir}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    # 사진들이 모여 있는 폴더명 지정 (예: 'team_photos' 또는 'dataset_100')
    INPUT_DIR = "dataset_100"
    OUTPUT_DIR = "batch_result"
    
    run_batch_test(INPUT_DIR, OUTPUT_DIR)