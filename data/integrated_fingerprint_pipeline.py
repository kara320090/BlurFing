import os
import sys
import site
import glob
import csv
import cv2
import numpy as np

# 1. Windows 환경 MediaPipe C++ 바이너리 경로 인식 버그 방어
packages_paths = site.getsitepackages()
for p in packages_paths:
    mp_path = os.path.join(p, 'mediapipe')
    if os.path.exists(mp_path):
        os.environ['MEDIAPIPE_RESOURCE_DIR'] = mp_path
        break

import mediapipe.python.solutions.hands as mp_hands


class EndToEndFingerprintPipeline:
    def __init__(self, 
                 min_detection_confidence=0.5, 
                 padding_ratio=1.2,
                 min_patch_size=30,
                 blur_threshold=15.0):
        """
        blur_threshold: 피부 표면의 부드러운 특성을 고려해 15.0으로 완화 조정
        min_patch_size: 손가락 끝마디 최소 해상도 기준 (가로/세로 30px 미만 필터링)
        """
        self.hands = mp_hands.Hands(
            static_image_mode=True,
            max_num_hands=2,
            min_detection_confidence=min_detection_confidence
        )
        self.padding_ratio = padding_ratio
        self.min_patch_size = min_patch_size
        self.blur_threshold = blur_threshold

        # (손가락명, 끝점 Tip 번호, 직전 DIP 관절 번호, 뿌리 MCP 번호)
        self.finger_map = [
            ("thumb", 4, 3, 2),
            ("index", 8, 7, 5),
            ("middle", 12, 11, 9),
            ("ring", 16, 15, 13),
            ("pinky", 20, 19, 17)
        ]

    def is_palmar_surface(self, crop_patches):
        """MediaPipe의 Left/Right 라벨 오판 및 상하 반전 구도에 영향을 받지 않도록
        피부 영역 내 손톱(Nail) 반사광 존재 비율로 손바닥(지문 면) 여부 판정"""
        nail_detected_count = 0
        valid_patches = 0

        for patch in crop_patches:
            if patch is None or patch.size == 0:
                continue

            h, w = patch.shape[:2]
            # 흰색 배경 영향을 배제하기 위해 패치 중심부(60%)만 분석
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

            # 고명도(V > 185) & 저채도(S < 55) 특성을 갖는 손톱 영역 측정
            nail_ratio = np.sum((v_vals > 185) & (s_vals < 55)) / len(skin_pixels)
            if nail_ratio > 0.12:
                nail_detected_count += 1

        if valid_patches == 0:
            return False
        # 손톱이 과반수 미만이면 지문 면(Palmar)으로 확정
        return (nail_detected_count / valid_patches) < 0.5

    def check_blur(self, patch):
        """라플라시안 분산 기반 모션 블러 필터링"""
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def process_fingerprint_ridge(self, crop_patch):
        """피부 마스킹, CLAHE 융선 강조, 다방향 가버 필터링 및 적응형 이진화 통합 연산"""
        # 1. Grayscale 변환 및 CLAHE 1차 대비 강화
        gray = cv2.cvtColor(crop_patch, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 2. 피부 분할 마스크 생성 (YCrCb 배경 차단)
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

        # 3. 다방향 가버 필터(Gabor Filter) 은행을 통한 융선 결 복원
        angles = np.linspace(0, np.pi, 8, endpoint=False)
        gabor_responses = []

        for theta in angles:
            gabor_kernel = cv2.getGaborKernel(
                ksize=(15, 15), sigma=2.5, theta=theta, lambd=5.0, gamma=0.5, psi=0, ktype=cv2.CV_32F
            )
            filtered = cv2.filter2D(enhanced, cv2.CV_32F, gabor_kernel)
            gabor_responses.append(filtered)

        max_gabor = np.max(np.stack(gabor_responses, axis=0), axis=0)
        max_gabor = cv2.normalize(max_gabor, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # 4. 적응형 이진화 (흑백 융선 패턴 생성)
        binary_ridge = cv2.adaptiveThreshold(
            max_gabor, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blockSize=11, C=-2
        )
        clean_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned_ridge = cv2.morphologyEx(binary_ridge, cv2.MORPH_OPEN, clean_kernel)

        # 5. 배경 영역은 검정색(0)으로 마스킹
        final_binary_ridge = cv2.bitwise_and(cleaned_ridge, cleaned_ridge, mask=final_mask)

        return final_mask, enhanced, final_binary_ridge

    def process_image(self, image_path, save_output_dir=None):
        """단일 사진 처리 및 검증 수행"""
        filename = os.path.basename(image_path)
        img = cv2.imread(image_path)
        if img is None:
            return {"file": filename, "status": "FAIL_CORRUPT", "patches": [], "reason": "이미지 로드 실패"}

        h, w, _ = img.shape
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.hands.process(img_rgb)

        if not results.multi_hand_landmarks:
            return {"file": filename, "status": "FAIL_NO_HAND", "patches": [], "reason": "손 검출 실패"}

        extracted_results = []
        skip_reasons = []

        for hand_idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # [1] 지문 면/손등 판정을 위해 5개 손끝 패치를 먼저 온전히 크롭
            crops_for_palmar_check = []
            finger_crops_info = []

            for name, tip_idx, joint_idx, mcp_idx in self.finger_map:
                tip = hand_landmarks.landmark[tip_idx]
                joint = hand_landmarks.landmark[joint_idx]
                mcp = hand_landmarks.landmark[mcp_idx]

                cx, cy = int(tip.x * w), int(tip.y * h)
                jx, jy = int(joint.x * w), int(joint.y * h)
                mx, my = int(mcp.x * w), int(mcp.y * h)

                dist_tip_dip = np.hypot(cx - jx, cy - jy)
                dist_dip_mcp = np.hypot(jx - mx, jy - my)
                radius = max(10, int(dist_tip_dip * self.padding_ratio))

                x1 = np.clip(cx - radius, 0, w)
                y1 = np.clip(cy - radius, 0, h)
                x2 = np.clip(cx + radius, 0, w)
                y2 = np.clip(cy + radius, 0, h)

                crop_patch = img[y1:y2, x1:x2].copy()
                if crop_patch.size > 0:
                    crops_for_palmar_check.append(crop_patch)
                    finger_crops_info.append({
                        "name": name,
                        "bbox": (x1, y1, x2, y2),
                        "crop": crop_patch,
                        "dist_tip_dip": dist_tip_dip,
                        "dist_dip_mcp": dist_dip_mcp
                    })

            # [2] 지문 면(Palmar) 검증을 최우선 수행
            if not self.is_palmar_surface(crops_for_palmar_check):
                skip_reasons.append(f"hand_{hand_idx}_dorsal(손등)")
                continue

            # [3] 지문 면 통과 후 개별 손가락 품질(가림/크기/블러) 검사
            for item in finger_crops_info:
                name = item["name"]
                crop_patch = item["crop"]
                x1, y1, x2, y2 = item["bbox"]
                crop_w, crop_h = x2 - x1, y2 - y1

                # 물건에 쥐여 접히거나 가려진 손가락 예외 방어
                if item["dist_tip_dip"] < 5 or (item["dist_tip_dip"] / (item["dist_dip_mcp"] + 1e-6)) < 0.15:
                    skip_reasons.append(f"{name}_occluded")
                    continue

                # 초소형 패치 필터링
                if crop_w < self.min_patch_size or crop_h < self.min_patch_size:
                    skip_reasons.append(f"{name}_too_small({crop_w}x{crop_h})")
                    continue

                # 블러 필터링 (완화된 15.0 기준)
                blur_score = self.check_blur(crop_patch)
                if blur_score < self.blur_threshold:
                    skip_reasons.append(f"{name}_blurred({blur_score:.1f})")
                    continue

                # [4] 융선 바이너리 패턴 추출
                mask, enhanced, binary_ridge = self.process_fingerprint_ridge(crop_patch)

                if (np.sum(mask > 0) / mask.size) < 0.10:
                    skip_reasons.append(f"{item['name']}_no_skin")
                    continue

                finger_id = f"{os.path.splitext(filename)[0]}_h{hand_idx}_{name}"
                if save_output_dir:
                    os.makedirs(save_output_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(save_output_dir, f"{finger_id}_raw.png"), crop_patch)
                    cv2.imwrite(os.path.join(save_output_dir, f"{finger_id}_mask.png"), mask)
                    cv2.imwrite(os.path.join(save_output_dir, f"{finger_id}_enhanced.png"), enhanced)
                    cv2.imwrite(os.path.join(save_output_dir, f"{finger_id}_ridge_binary.png"), binary_ridge)

                extracted_results.append({
                    "finger_id": finger_id,
                    "bbox": item["bbox"],
                    "ridge_binary": binary_ridge
                })

        status = "SUCCESS" if len(extracted_results) > 0 else "SKIPPED"
        return {
            "file": filename,
            "status": status,
            "extracted_count": len(extracted_results),
            "patches": extracted_results,
            "reason": ", ".join(skip_reasons) if skip_reasons else "정상 처리"
        }


# --- 실행 진입점 (단일 테스트 또는 100장 배치 동시 지원) ---
if __name__ == "__main__":
    pipeline = EndToEndFingerprintPipeline()

    # 1. 단일 테스트 사진이 있는 경우 우선 실행
    single_test_image = "test_hand.jpg"
    single_output_dir = "stage5_single_output"

    if os.path.exists(single_test_image):
        print(f"[*] 단일 이미지 테스트 시작: {single_test_image}")
        res = pipeline.process_image(single_test_image, save_output_dir=single_output_dir)
        print(f" -> 결과: {res['status']}, 추출된 지문 패치: {res['extracted_count']}개, 사유: {res['reason']}")
        print(f" -> '{single_output_dir}' 폴더에 '_ridge_binary.png' 결과물이 생성되었습니다.\n")

    # 2. 100장 데이터셋 폴더가 있는 경우 배치 루프 실행
    dataset_dir = "dataset_100"
    batch_output_dir = "batch_result"

    if os.path.exists(dataset_dir):
        image_files = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"]:
            image_files.extend(glob.glob(os.path.join(dataset_dir, ext)))

        if len(image_files) > 0:
            print(f"[*] 100장 배치 테스트 시작 (총 {len(image_files)}장)")
            patches_dir = os.path.join(batch_output_dir, "extracted_patches")
            report_list = []

            for idx, img_path in enumerate(image_files, 1):
                res = pipeline.process_image(img_path, save_output_dir=patches_dir)
                report_list.append({"file": res["file"], "status": res["status"], 
                                    "count": res["extracted_count"], "reason": res["reason"]})
                print(f"[{idx:03d}/{len(image_files):03d}] {res['file']} -> {res['status']} ({res['extracted_count']}개)")

            # CSV 리포트 자동 생성
            csv_path = os.path.join(batch_output_dir, "pipeline_evaluation_report.csv")
            with open(csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["file", "status", "count", "reason"])
                writer.writeheader()
                writer.writerows(report_list)

            print(f"\n[+] 배치 처리 완료! 결과 리포트: {csv_path}")