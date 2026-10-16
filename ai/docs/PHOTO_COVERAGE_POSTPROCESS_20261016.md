# PHOTO 보호 범위 후처리 및 스캐너 입력 점검 — 2026-10-16

후속 작업: 같은 날짜에 수행한 [세 손가락 누락 원인 및 EdgeTAM/YOLO26/MobileNetV4 비교](PHOTO_EXTERNAL_MODELS_20261016.md)를 참고한다. 아래 모델 미실행 상태와 테스트 수는 이 후처리 작업 당시의 기록이다.

## 결론과 범위

현재 코드의 검은 가림은 선택된 마스크 안의 RGB를 제거하지만, 모든 지문 영역을 검출했다는 보장은 없다. 기존 Coverage 모드에 **같은 손가락 후보 내부의 닫힌 구멍만 채우는 선택 기능**을 추가했다. 학습에 사용된 정답 13장에서는 누락된 정답 화소 175개를 추가로 가렸고, 추가 오검출 화소는 없었다. 개선 폭은 작으며 완전한 지문 보호는 아직 미검증이다.

사진 21장은 정답이 있는 기존 학습 사진 13장, 같은 촬영의 추가 사진 7장, 사용자가 제시했던 기존 단일 손가락 사진 1장이다. 새 독립 평가 자료가 아니다. 정답은 평가에만 사용했고 추론에 넣지 않았다. 재학습·임계값 탐색·새 정답 생성은 하지 않았다.

## 1. 실제 파이프라인과 문제 원인

PHOTO: encoded RGB/EXIF 계약 → COLFISPOOF body/tip → distal coarse pad → V6 mask → 선택적 단일 손가락 coarse 보완 및 관측 손 자세 → 선택적 owner 내부 구멍 채움 → 검은 가림 → 실제 PNG 저장·재검사.

기존 단일 손가락 사례는 V6가 넓은 coarse 후보의 일부만 남겨 작은 검은 조각이 생겼다. 이미 구현된 단일 손가락 coarse 보완은 그 사례의 마스크를 146,751에서 508,604화소로 확장한다. 이번 작업에서 그 기존 개선을 새 개선으로 계산하지 않았다. 다중 손가락에서는 손가락별 연결·첫마디 경계 추정이 여전히 불완전하다. 닫힌 구멍 채움으로 열린 틈, 완전히 누락된 손가락, 잘못된 첫마디 경계를 복구할 수는 없다.

이 가림 경로는 지문 간격이나 feature acceptance gate를 사용하지 않는다. 따라서 여기서 남는 노출을 pitch 측정 실패 때문이라고 해석하면 안 된다. 자연스러운 지문 변환을 하는 frozen 경로와 별개의 실험이다.

## 2. 구현 변경

- `photo_owner_hole_completion_v1.py`: coarse/body/tip 결합을 검증하고, 같은 owner의 닫힌 구멍만 채운다. 영상 외곽을 명시적 0으로 패딩하고 4연결 배경 규칙을 사용한다. 손가락 간 연결·팽창·convex hull은 적용하지 않는다.
- `photo_source_rgb_v1.py`: 기존 RGB/L/RGBA decode와 EXIF 1–8 계약을 경량 모듈로 분리했다. EXIF 누락은 1, 명시적 잘못된 값은 거절한다. RGBA는 기존 정수 연산의 흰 배경 합성을 보존한다.
- `protect_photo_pitch_free_v1.py`: 선택 플래그 `--complete-holes`, `--allow-scanner`, 단계별 진단과 실제 결과 저장을 추가했다. 기본 PHOTO 픽셀 동작은 회귀 확인했다.
- `pitch_free_artifacts_v1.py`: original/candidate/refined/protected/comparison 결과를 저장한다. 원본 RGB·EXIF·지원되는 RGB ICC를 보존하며, 화면용 비교 썸네일만 표시 방향 및 sRGB로 변환한다.
- 로컬 PowerShell 실행기: 선택 파일 경로·해시·모드와 오류 JSON을 비공개 기록에 남긴다. CMD는 실제 실패 종료 코드를 보존한다.

모델 가중치, 자연 변환 수학, frozen renderer, 기존 detector/pitch/feature 임계값은 변경하지 않았다.

## 3. 후처리·외부 모델 비교

후처리 세 가지는 사전에 정한 규칙으로 각각 독립 비교했다. 채택 조건은 기존 Coverage 대비 모든 정답 사진에서 recall/IoU 저하 및 FP 증가가 없고, 실제 누락 정답 화소를 하나 이상 복구하는 것이다.

| 방법 | 합산 IoU | 정답 화소 recall | 누락 비율 | 과잉 가림 비율 | 판단 |
|---|---:|---:|---:|---:|---|
| V6 | 0.880402 | 0.901453 | 0.098547 | 0.025840 | 기존 좁은 모드 |
| Wide | 0.874911 | 0.908372 | 0.091628 | 0.040402 | 기존 선택 모드 |
| Coverage | 0.869604 | 0.909848 | 0.090152 | 0.048403 | 비교 기준 |
| owner 내부 구멍 채움 | 0.869647 | 0.909894 | 0.090106 | 0.048400 | 선택 기능으로 채택 |
| local closing | 0.869603 | 0.909965 | 0.090035 | 0.048532 | 5장 퇴행, 미채택 |
| owner/coarse 내부 convex hull | 0.780709 | 0.911486 | 0.088514 | 0.155246 | 6장 퇴행, 미채택 |
| 이전 SAM2.1 dense prompt 결과 | 0.725716 | 0.915851 | 0.084149 | 0.222436 | 11장 퇴행, 미채택 |

IoU = TP/(TP+FP+FN), recall = TP/(TP+FN), 누락 = FN/(TP+FN), 과잉 가림 = FP/(TP+FP). 합산 화소 지표이며 사진별 macro 평균이나 독립 성능이 아니다. 과거 GT7 coarse IoU 0.7529와 데이터·정의가 달라 직접 비교하면 안 된다. 선택 기능의 개선은 Coverage 대비이며 V6보다 종합 정확도가 더 높다는 뜻도 아니다.

SAM2.1/MediaPipe/COLFISPOOF의 기존 결과를 재사용했다. 같은 SAM2 실험을 반복하지 않았다. [SAM3 공식 저장소](https://github.com/facebookresearch/sam3)는 별도 환경과 [가중치 접근 신청](https://huggingface.co/facebook/sam3)이 필요하다. 현재 Torch 환경은 CPU 빌드이며, 장비에는 8 GiB RTX 4060 Laptop GPU가 있다. SAM3 실행 성능은 측정하지 않았다. [SAM3.1의 발표](https://github.com/facebookresearch/sam3/blob/main/RELEASE_SAM3p1.md)는 영상 다중 객체 추적 개선으로, 정지 사진의 첫마디 성능 우위를 의미하지 않는다.

[YOLO26-seg](https://docs.ultralytics.com/models/yolo26)의 공개 COCO 가중치는 [손끝 첫마디 클래스를 포함하지 않는다](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/datasets/coco.yaml). 이 목표에는 추가 학습과 손가락 instance 정답 계약, 촬영 그룹 분리 평가가 필요하다. [코드 라이선스](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)도 배포 설계에서 확인해야 한다. 이 모델의 다운로드·학습·비교 추론은 이번에 수행하지 않았다.

[EdgeTAM](https://github.com/facebookresearch/EdgeTAM)은 경량 prompt 분할 후보이며, 공개 모바일 수치를 이 프로젝트의 Android 성능으로 취급하지 않았다. [MobileNetV4](https://arxiv.org/abs/2404.10518)는 backbone 후보로 decoder 연결과 재학습이 필요하다. 둘 다 이번 실측 대상이 아니다.

## 4. 사진별 결과와 누락

정답 13장 중 2장에서만 이번 후처리로 실제 정답 화소가 추가됐다: 익명 사례 002에서 168개, 008에서 7개. 나머지 11장은 동일하다. 정답 13장의 합산 TP=3,473,791, FP=176,684, FN=344,007이다. 정답 영역의 약 9.01%가 아직 노출된다.

정답 마스크의 연결 성분 21개 중 20개에 최종 마스크가 일부 겹친다. 겹침이 없는 1개는 1화소 정답 조각이다. 사람의 손가락 instance ID가 없으므로 이를 손가락 검출률 20/21로 보고하지 않는다. 모든 정답 화소를 가렸다는 엄격한 조건으로는 0/13장이다. 이 조건 역시 정답 경계의 작은 오차와 의미 있는 누락을 구별하는 완성 지표는 아니다.

정답 없는 추가 7장에서는 3장에 각각 60, 1,204, 2화소가 더 가려졌다. 기존 단일 손가락 사례는 변화가 없다. 추가 영역이 올바른지는 사람 정답 없이 확인할 수 없다. 사진별 단계 이미지와 지표는 비공개 결과 보고서에 저장했다.

## 5. EXIF 오류와 지문 전용 입력

제공된 지문 전용 폴더의 PNG 1,712개는 L/512×512이며 유효하지 않은 EXIF 방향 값이 발견되지 않았다. 지정한 `00009.png`도 EXIF 누락의 정상 기본값 1로 읽힌다. 같은 파일은 이번 수정 전 커밋의 RGB decode 검사도 통과한다. 따라서 과거 `invalid_source_exif_orientation` 로그의 원인을 이 파일의 현재 내용으로 재현하지 못했다. 입력 유형 문제를 EXIF 오류의 직접 원인이라고 단정하지 않는다.

별도로 기존 실행기는 PHOTO 전용이어서 스캐너 이미지를 거절했다. 데스크톱 실행기는 이제 기존 FINGERPRINT_IMAGE routing/ROI detector로 연결한다. 손가락 V6·MediaPipe는 호출하지 않는다. scanner ROI detector는 기존 주기적 ridge 증거를 사용하지만, ROI를 검게 가리는 연산은 pitch를 추정하거나 지문을 합성하지 않는다.

스캐너 표본 12장 및 지정 파일의 실제 CMD 실행에서 결과 PNG를 저장했다. 지정 파일은 254,464화소를 가렸고 원본 및 마스크 밖 RGB를 보존했다. 상태는 `redacted_unverified_scope`다. 가장자리 누락 가능성이 있으므로 전체 지문 보호 성공으로 보고하지 않는다.

잘못된 EXIF 값 0을 넣은 합성 파일은 여전히 오류로 거절되며, 파일 경로·해시·방향 값/타입을 기록하는 실행기 오류 경로를 직접 검증했다. 원본 방향을 추측하거나 잘못된 값을 자동으로 1로 바꾸지 않았다.

## 6. 검증과 실제 산출물

Windows 전체 AI 테스트 719개 통과. Torch 없는 Windows 환경의 focused 테스트 54개와 portable geometry 48개 비교도 통과했다. 스캐너 routing, RGB/L/RGBA, EXIF 1–8, 실제 PNG RGB/마스크 보존, 닫힌 구멍·열린 틈·다중 owner·회전·좌우 반전을 검사한다.

21장에서는 기존 추론을 재사용하고 실제 새 후처리/PNG 저장을 실행했다. 추가 사진 1장은 CMD로 COLFISPOOF/V6/MediaPipe부터 새로 실행해 캐시 기반 결과와 대조했다. 비교 자료에서 일부 canonical 입력의 ICC가 누락된 점을 발견해, 해시와 decoded RGB가 확인된 원본에 다시 연결하여 최종 자료를 재생성했다. 학습이나 예측 마스크는 변경하지 않았다.

새 코드의 Linux 테스트는 실행하지 못했다. 현재 WSL/Docker가 없으며 이전 Ubuntu CI 결과를 새 코드 결과로 합산하지 않는다. CI에는 새 focused 테스트를 등록했지만 원격 push는 하지 않는다. 완전한 Windows/Linux 모델·픽셀 parity도 새로 검증했다고 주장하지 않는다.

## 7. 실행 및 남은 작업

기존 실행기를 유지한다. 새 선택 실행기 `BlurFing-Pitch-Free-Refined-Test.cmd`는 기존 Wide/Coverage와 owner 구멍 채움을 사용한다. 파일을 선택하면 별도 실행 폴더의 `protected.png`가 실제 반환 결과, `comparison.png`가 화면용 비교다. `original.png`, `candidate_mask.png`, `refined_mask.png` 및 비공개 진단도 생성한다. 원본 파일을 덮어쓰지 않는다.

남은 핵심은 실제 첫마디 경계와 누락 손가락 검출이다. 단순 closing/hull 및 이미 시험한 SAM2 설정은 과잉 가림을 늘려 채택하지 않았다. 새로운 detector 학습은 촬영 그룹을 나누고 현재 개발 자료에 대한 반복 선택과 독립 검증을 구분해야 한다. SAM3 접근 권한 확보와 별도 GPU 환경 검증, YOLO26의 목표 클래스 학습은 아직 수행하지 않은 후보 작업이다. 자동 구멍 채움만으로 이 문제를 해결했다고 판단하지 않는다.
