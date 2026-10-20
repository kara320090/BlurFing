# BlurFing AI 한글 인수인계

후속 실제 인수 기록: 사용자 제공 비공개 묶음의 2,251개 파일 복원·해시 검증, Windows의 고정 시드 V23 RGB·마스크 기준 재현, Android 에뮬레이터의 실제 모델 HTTP·저장 재읽기를 확인했습니다. 현재 PC의 앱 경로 약 177초는 120초 목표 미달입니다. [후속 실측·남은 검증](../docs/worklogs/2026-10-20-이봉헌-private-handoff-replay.md)을 따르며, 아래 초기 인수 시점의 미전달 상태와 구분합니다. 학교 Ubuntu·실물 장비·새 촬영 독립 평가는 남아 있습니다.

2026-10-20 후속 인수 범위: 사용자는 Android 자동 V23을 주 시연으로, FFV 센서 비교를 보조 시연으로 확정했습니다. 비공개 자산과 새 촬영 자료를 인수·확보할 수 있다고 답했으며 실물 휴대폰과 센서는 10월 21~22일 사용합니다. 이번 마감에서는 전용 PC 자동 업로드 화면과 수동 검토 마스크의 Android API 확장은 제외합니다. [현재 인수·시연 절차](../demo/README.md)를 우선하고, 아래 PC UI 우선순위·자료 확보 제약은 작성 당시의 인계 기록으로 구분합니다. 실제 자산 전달·학교 서버 연결·장비 검증 완료를 의미하지 않습니다.

작성 기준: **2026-10-20**, 알고리즘 기준 커밋 **`272e639`**.
이후 붙은 문서/공개 준비 커밋과 혼동하지 않습니다. 담당자 변경 후에는 먼저 실제 `HEAD`와 원격 이력을 다시 확인합니다.

## 1. 현재 결론과 인계 범위

목표는 **Android에서 사진을 선택하면 손끝의 노출된 지문을 자동으로 찾아 보호 사본을 돌려주는 것**입니다.
현재 Android → PC 서버 → 실제 검출 모델 → V23 합성 → 응답 검증 → 저장/재읽기까지 개발 환경에서 동작합니다.
다만 임의의 새 사진에서 누락 없이 보호되는 완성품으로 판정할 근거는 부족합니다.

다음 네 가지는 구분해서 보고해야 합니다.

1. **구현 완료**: 자동 전송, 모델 실행, 조건부 합성, 적용 범위 검사, 사본 저장.
2. **제한된 재현 검증**: 기존 개발 사진, 합성 단위 검사, Windows와 Android 에뮬레이터.
3. **현재 알고리즘 한계**: 손끝 누락·잘못된 범위, 가시성 오판, 인공적인 질감, 긴 처리 시간.
4. **미완료 검증**: 새 촬영 그룹의 독립 성능, 별도 동일인 참조 매칭, 최신 Linux 동등성, 실물 휴대폰과 배포 운영.

현재 승인 상태는 다음과 같습니다.

```text
CURRENT_PHOTO_ENGINE=synthetic_v23
CURRENT_SEGMENTATION_MODEL=whole_pad_context_v6
AUTOMATIC_BOUNDARY_RECOVERY=local_axis_v24
AUTOMATIC_VISIBILITY_POLICY=joint_raw_witness_v11
automatic_visibility_approved=false
production_approved=false
privacy_validated=false
complete_photo_protection_verified=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
```

위 상태는 기존 frozen 파이프라인의 10-case Windows/Linux 동등성 완료 기록을 취소하는 것이 아닙니다.
**그 기록을 최신 V23 전체에 확대 적용하지 않기 위한 구분**입니다.

## 2. 사용할 코드와 Git 작업

공개 저장소: [kara320090/BlurFing](https://github.com/kara320090/BlurFing).
이번 인계 이후의 기준은 공개 `main`의 `ai/`와 함께 커밋된 `backend/`, `android/`, `contracts/`입니다.
과거 `BlurFing_Windows_Validation`이나 AI ZIP 복사본으로 덮어쓰지 않습니다.
로컬 편의 실행기 경로는 개발자의 PC에 종속되므로 새 담당자는 저장소의 매개변수형 실행기를 씁니다.

```powershell
git fetch origin
git status --short
git log --graph --decorate --oneline --all -25
git rev-list --left-right --count origin/main...HEAD
git diff
git diff --cached
```

작업 트리가 깨끗하고 원격만 앞서 있으면 `git merge --ff-only origin/main`으로 동기화합니다.
양쪽 변경이 있으면 팀원 이력을 보존해 merge합니다. `reset --hard`, `clean -fd`, 강제 push, 전체 파일 stage를 사용하지 않습니다.
기존 `data/` 작업과 다른 팀원 변경을 AI 정리 과정에서 삭제하거나 재작성하지 않습니다.

실행 중 코드 변경을 감지하는 장치가 있습니다. **AI 요청이 실행되는 동안 `ai/scripts/`나 플랫폼 소스를 수정하지 마세요.**
실행 완료 후 수정하고 새 출력 폴더로 재검사합니다. `.gitattributes`의 LF 규칙과 모델에 결합된 소스 해시도 유지합니다.

## 3. 현재 알고리즘과 코드 진입점

### 3.1 자동 PHOTO 경로

| 단계 | 핵심 파일 | 검사할 내용 |
|---|---|---|
| 입력·전송 | `export_photo_permissions_v1.py`, `photo_experimental_transport_v1.py` | sRGB 정규화된 RGB8 PNG, 방향 1, 15MiB/2천만 화소, 요청 ID 결합 |
| 자동 조정 | `photo_automatic_v23.py` | 후보 생성→경계→관측→합성→응답 연결 |
| 후보 생성 | `photo_new_input_v23.py`, `protect_photo_pitch_free_v1.py` | COLFISPOOF/V6/관측 자세의 출처와 좌표 |
| V6 분할 | `infer_whole_pad_context_v6.py`, `whole_pad_context_model_v6.py` | 모델/config/소스 해시, 전체 문맥·국소 타일의 좌표 대응 |
| 경계 보정 | `photo_crease_native_adapter_v1.py`, `photo_crease_pad_v1.py` | BODY 외곽과 실제 관측 관절 주름, 손가락별 소속 |
| 국소 축 복구 | `photo_local_axis_v24.py` | 기존 경계 미확정 후보만 보완. 엄지에서 전체 손 주축이 잘못 적용되던 문제 대응 |
| 지문선 관측 | `photo_visibility_joint_witness_v11.py` | 원본 검사선의 공동 반복 증거. 자동 경로의 bbox 최대 변 640/1280, 유효 창 최대 4,096 |
| 공통 합성 | `photo_visibility_reviewed_apply_v1.py` | 선택된 영역에 원자적으로 적용하고 실패 영역 복귀 |
| 질감 | `photo_synthetic_replacement_v19.py`, `photo_organic_surface_v19.py` 및 이전 의존 파일 | 원본의 넓은 외관을 참고하되 미세 능선은 독립 생성 |
| 외곽·주름 연결 | `photo_silhouette_appearance_v21.py`, `photo_skin_seam_v22.py`, `photo_junction_appearance_v23.py` | 경계 색·실루엣·이음부·2차원 관절 연결 |
| CPU 최적화 | `photo_junction_fit_runtime_v1.py` | 요청별 최대 4개 프로세스, 순서 유지, 오류·종료 시 정리 |
| 서버 | `../backend/experimental_photo_main.py`, `experimental_photo_transport_v2.py` | 큐·timeout·취소·응답 계약·private 임시 파일 정리 |
| 앱 | `../android/`의 `experimental` 관련 소스 | 정규화, 오래된 요청 무효화, 실제 PNG 재읽기, 적용/보류 표시 |

위 표에서 AI 파일은 모두 `ai/scripts/` 기준입니다. 파일 이름에 낮은 버전이 있어도 최신 엔진의 공통 의존 코드일 수 있으므로 삭제하지 않습니다.

**판정 의미**

- 반복 증거를 못 찾거나 관측 예산이 소진되었다고 해서 “지문 없음”을 확정하지 않습니다.
- `success` / `partial_success` / `rejected`는 후보 처리 상태입니다. 후보가 놓친 손가락까지 평가하지 않습니다.
- `returned.png`의 실제 RGB와 적용/거절 마스크를 함께 검사합니다. 후보 마스크, 변경 픽셀, 보호 효과는 서로 다른 개념입니다.
- 적용 마스크 밖·거절된 영역은 원본과 동일해야 합니다. 같은 RGB를 유지했다는 사실이 그 영역의 개인정보 보호를 뜻하지는 않습니다.
- 자동 선택 출처를 사람 라벨이나 사람이 승인한 결과로 바꾸지 않습니다.

### 3.2 기존 변환·스캐너 경로

기존 PHOTO frozen V4는 관측 너비·pitch·구조 조건을 확인하고 `natural_auto_04` + `boundaryblend_02`로 변환합니다.
원본 pitch를 안정적으로 얻지 못한 사진이 많아 실제 적용이 제한되었습니다.
현재 V23은 같은 pitch 실패를 임계값 완화로 통과시키는 방식이 아니라 별도의 합성 경로입니다.

기존 `protect_fingerprint.py` CLI는 `legacy`, `native_v12`, `distal_v13`, `pose_v14` 선택을 유지합니다.
**여기에 `--photo-engine synthetic_v23`을 넣지 마세요.** 자동 V23은 `export_photo_permissions_v1.py`와 V2 서버를 통해 실행합니다.

지문 스캐너는 기존 unified routing/ROI/변환 경로로 검사합니다.
자동 V23의 손 사진 입력에서 scanner/UNKNOWN을 미적용으로 반환하는 것은 의도된 분리입니다.
NBIS·SourceAFIS는 개발 검증용이며 Android의 매 요청 합성에 필수인 매칭 단계가 아닙니다.

## 4. 버전별 개선과 보존 대상

| 계열 | 변경 이유·주요 내용 | 읽을 기록 |
|---|---|---|
| 기존 frozen V4 | 측정 가능한 원본 지문을 변환하는 기준 유지 | [기존 README](README_HISTORY_PRE_V23_20261020.md) |
| 학습 refinement 초기 | 소규모 학습 후 GT7 성능 악화로 거절. 현재 모델과 구분 | [당시 최종 결과](results/pad_refinement_final_summary.md) |
| 학습 V4/V5/V6 | 전체 손끝 라벨, 손실 균형, 전체 손가락 문맥 추가. V6의 일반화 개선은 미입증 | [V6](docs/PHOTO_WHOLE_PAD_CONTEXT_V6.md) |
| rounded / crease | 과대·파편 후보를 손끝 외곽·관절 주름 범위로 보완 | [rounded](docs/PHOTO_ROUNDED_PAD_20261016.md), [crease](docs/PHOTO_CREASE_BOUNDARY_V1.md) |
| 합성 V1–V2 | 조건부 native 적용이 안 되는 후보에 별도 불투명 합성·사진 외관 복원 실험 | [V1](docs/PHOTO_SYNTHETIC_REPLACEMENT_V1.md), [V2](docs/PHOTO_SYNTHETIC_REPLACEMENT_V2.md) |
| 합성 V3–V6 | 지문 흐름, 국소 색 경계, 능선 변화와 큰 피부 주름 | [V3](docs/PHOTO_SYNTHETIC_REPLACEMENT_V3.md), [V6](docs/PHOTO_SYNTHETIC_REPLACEMENT_V6.md) |
| 합성 V7–V9 | 3회 외관 비교: 사진 규모에 맞는 능선·주름·미세 질감 | [3회 외관](docs/PHOTO_SYNTHETIC_APPEARANCE_ITERATIONS_20261017.md) |
| 합성 V10–V12 | 3회 피부 재질 비교: 표면 요철·기공·주름과 경계 연결 | [3회 재질](docs/PHOTO_SKIN_MATERIAL_THREE_ROUNDS_20261017.md) |
| 합성 V13–V17 | 5회 추가 비교: 재질과 주름·조명 결합, 지나친 매끈함 한계 기록 | [5회 재질](docs/PHOTO_SKIN_FIVE_ROUNDS_20261017.md) |
| V18 / V19 | 생성 질감이 최종 해상도에서 사라지는 원인 보완 / 불규칙 피부 표면 | [V18](docs/PHOTO_TEXTURE_RESOLUTION_V18_20261018.md), [V19](docs/PHOTO_ORGANIC_SURFACE_V19_20261018.md) |
| V20 | 외곽 색 복원과 matcher 후속 진단. 실험을 기본값으로 승격하지 않음 | [후속 검사](docs/PHOTO_CONTOUR_NBIS_FOLLOWUP_20261020.md) |
| V21 / V22 / V23 | 실루엣, 이음부, 관절의 2차원 외관을 단계적으로 개선 | [V21](docs/PHOTO_SILHOUETTE_APPEARANCE_V21_20261020.md), [V22](docs/PHOTO_SKIN_SEAM_V22_20261020.md), [V23](docs/PHOTO_JUNCTION_APPEARANCE_V23_20261020.md) |
| 가시성 실험 | 사람 판정과 원본 관측 비교. 최종 자동 경로는 V11 증거 사용 | [사람 검토·공동 증거](docs/PHOTO_VISIBILITY_JOINT_REVIEWED_20261020.md) |
| 자동 V23 + V24 | Android 연결과 엄지의 잘못된 전역 축 대응 | [자동 연동](docs/PHOTO_AUTOMATIC_V23_20261020.md) |
| 실행 비용 최적화 | 같은 결과를 유지한 프로세스 병렬화·중복 계산 감소 | [성능](docs/PHOTO_V23_PERFORMANCE_20261020.md) |

SAM/MediaPipe/COLFISPOOF 및 이후 외부 모델 비교는 [외부 모델 기록](docs/PHOTO_EXTERNAL_MODELS_20261016.md)에 있습니다.
사용자가 SAM 3 가중치를 보유하지 않아 다른 공개 모델부터 비교한 이력이 있습니다.
외부 일반 분할 모델이 손끝 첫 관절 경계와 지문 가시성을 바로 해결한다고 가정하지 않습니다.
새 모델을 채택하려면 현재 V6와 같은 촬영 그룹·같은 GT·같은 후처리 조건으로 비교합니다.

## 5. 다음 담당자의 실행 환경 준비

### 5.1 환경을 분리해야 하는 이유

현재 AI 본체는 NumPy 2 계열이고 COLFISPOOF는 TensorFlow 2.10·NumPy 1 계열입니다.
하나의 가상환경에 모두 설치하면 의존성 충돌 또는 수치 차이가 생길 수 있습니다.
기존 환경을 무작정 최신 버전으로 올리지 않습니다.

| 환경 | 이 PC에서 확인한 버전 | 역할 |
|---|---|---|
| AI | Python 3.11.9, NumPy 2.2.6, Pillow 12.3.0, OpenCV headless 5.0.0.93, SciPy 1.15.3, scikit-image 0.25.2 | 기하·합성·입출력 |
| AI 학습/추론 추가 | torch 2.14.1+cpu, torchvision 0.29.1+cpu | V6 모델. 기본 `ai/requirements.txt`에는 포함되지 않음 |
| COLFISPOOF worker | Python 3.10.11, TensorFlow 2.10.0, NumPy 1.21.6, Pillow 9.3.0, opencv-python 4.6.0.66 | 공식 DeepLab 모델 별도 실행 |
| MediaPipe worker | Python 3.10.11, mediapipe 1.1.1 | 관측한 손 자세 보완 |
| 서버 | Python 3.11.9, FastAPI 0.141.1, Starlette 1.6.0, uvicorn 0.53.0, python-multipart 0.0.32, httpx 0.28.1 | V2 HTTP |

이 표는 **설치된 환경 관측값**이며 다른 OS의 설치 성공 보증이나 전체 lockfile이 아닙니다.
COLFISPOOF용 [requirements](platform/windows/requirements_colfispoof.txt)는 OpenCV headless 빌드를 지정합니다. 검증 PC의 일반 OpenCV 빌드와 구분하고, 바꾸면 출력 동등성을 확인합니다.
실제 재현 시 비공개 인계본의 전체 패키지 목록·모델 체크섬도 함께 확인합니다.

```powershell
# 저장소 루트에서 실행. 각 python 경로는 실제 별도 가상환경으로 교체합니다.
& "<AI-python>" -m pip install -r ai/requirements.txt
& "<backend-python>" -m pip install -r backend/requirements-photo-v2.txt -r backend/requirements-dev.txt
& "<COLFISPOOF-python>" -m pip install -r ai/platform/windows/requirements_colfispoof.txt
```

V6용 torch/torchvision CPU 조합과 MediaPipe 환경은 위 확인 버전에 맞게 별도로 준비합니다.
설치가 안 되면 버전·플랫폼 차이를 기록하고 원인을 해결하며, 검증되지 않은 버전으로 조용히 교체하지 않습니다.
각 환경에서 `python -m pip check`를 수행합니다.

### 5.2 필요한 모델과 레지스트리

- V6 폴더에 `final_context_whole_pad.pt`와 대응하는 `final_config.private.json`이 있어야 합니다.
- V6 최종 가중치 SHA-256: `0c9d057ab220daadc369ed425a67f732d44e32a9da63155cc53842c2a545e14b`.
- COLFISPOOF `deeplab_model.tar.gz` SHA-256: `f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f`.
- V6 학습에 쓴 공식 `mobilenet_v3_small-047dcff4.pth` SHA-256: `047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f`.
- MediaPipe `hand_landmarker.task`는 인계 manifest와 runtime 검사를 통해 식별합니다.
- 사용 자료 레지스트리를 그대로 인계받습니다. 이력을 지우면 기존 사진을 미사용 사진으로 오판할 수 있습니다.
- 현재 개발 체크포인트는 `approved_for_inference=false`, `development_only=true`를 유지하며 로더도 이 상태를 검사합니다. 실험 실행이 가능하다고 승인 플래그를 바꾸지 않습니다.

모델/config는 공개하지 않습니다. 학습 소스 해시가 맞지 않을 때 체크섬 값을 바꿔 통과시키지 않습니다.
이미 확인한 한 방향의 추가 검증 분기만 허용한 [V6 호환 기록](docs/V6_CHECKPOINT_VALIDATOR_COMPATIBILITY.md)을 먼저 확인합니다.

### 5.3 Windows 서버 실행

새 PowerShell 세션에서 아래 경로를 실제 인계 위치로 설정합니다.

```powershell
$env:BLURFING_COLFISPOOF_PYTHON = "<COLFISPOOF-env>\Scripts\python.exe"
$env:BLURFING_COLFISPOOF_SOURCE = "<COLFISPOOF-git>"
$env:BLURFING_COLFISPOOF_MODEL = "<COLFISPOOF-git>\pre-processing\Segmentation\model\deeplab_model.tar.gz"
$env:BLURFING_HAND_PYTHON = "<MediaPipe-env>\Scripts\python.exe"
$env:BLURFING_HAND_MODEL = "<private-runtime>\hand_landmarker.task"

& ".\backend\Start-Photo-V23.ps1" `
  -ServerPython "<backend-env>\Scripts\python.exe" `
  -AiPython "<AI-env>\Scripts\python.exe" `
  -ModelPath "<private-V6-training-folder>" `
  -RegistryPath "<private>\consumed_registry.private.json" `
  -Port 8001
```

기존 학습·개발 사진 재실행은 **명시적으로 `-DevelopmentReplay`**를 붙입니다. 이를 독립 검증으로 기록하지 않습니다.
기존 서버 재사용은 `-ReuseRunning`이며, 기존 서버 설정을 유지합니다. 새 환경변수를 적용하려면 해당 서버를 정상 종료한 후 다시 실행하거나 다른 포트를 사용합니다.
임의의 포트 소유 프로세스를 자동 종료하지 않습니다.

- PC 준비 상태: `http://127.0.0.1:8001/ready`.
- Android 에뮬레이터 주소: `http://10.0.2.2:8001`.
- API: `POST /v2/photo/protect`, 엔진 `synthetic_v23`.
- 서버는 loopback 전용, 실행 1건 + 대기 1건, timeout 600초입니다.
- 기존 서버 재사용 안내 창을 닫아도 서버가 종료되지 않는 것은 정상입니다.
- `.cmd` 내용을 PowerShell에 붙여 넣지 마세요. 파일을 실행하려면 `& "<launcher>.cmd"`를 사용합니다.

이 서버는 외부 공개 배포 구성이 아닙니다. 인증·HTTPS·보관 정책을 갖춘 실제 배포는 별도 작업입니다.

### 5.4 에뮬레이터 없이 검사하기

현재 가능한 방법은 **기존 PC 수동 검토 UI** 또는 **정규화된 입력을 자동 브리지에 전달**하는 것입니다.
새 사진을 넣기만 하면 같은 자동 API 결과를 보여 주는 전용 PC 화면은 아직 구현 완료되지 않았습니다.

수동 검토 UI:

```powershell
& ".\ai\platform\windows\start_new_photo_v23.ps1" `
  -PythonPath "<AI-env>\Scripts\python.exe" `
  -ModelPath "<private-V6-training-folder>" `
  -RegistryPath "<private>\consumed_registry.private.json" `
  -OutputRoot "<private-output>\new-photo-review"
```

후보를 사람이 검토하는 경로이며 자동 V23 전체 성능 평가를 대신하지 않습니다.
출력 위치와 접속 URL은 실행기에 표시됩니다.

자동 브리지:

```powershell
& "<AI-env>\Scripts\python.exe" ".\ai\scripts\export_photo_permissions_v1.py" `
  --input "<private>\canonical-request.png" `
  --output "<private-output>\fresh-v23-run" `
  --photo-engine synthetic_v23 `
  --photo-model "<private-V6-training-folder>" `
  --consumed-registry "<private>\consumed_registry.private.json" `
  --request-id "handoff-v23-001"
```

`canonical-request.png`는 방향·색상을 이미 변환한 RGB8 PNG여야 합니다. JPEG의 확장자를 바꾸거나 ICC를 단순 삭제하면 안 됩니다.
브리지는 임의 업로드의 색상 변환을 대신하지 않습니다. 최신 허용 PNG chunk 계약은 소스와 [전송 문서](docs/PHOTO_EXPERIMENTAL_TRANSPORT_V2.md)를 따릅니다.
기존 사용 사진에는 `--development-replay`가 필요합니다. 출력 폴더는 매번 새로 지정합니다.
`result.transport.json`은 이미지·마스크를 포함하므로 공개하면 안 됩니다.

## 6. 데이터·학습·평가 상태

### 6.1 실제 자료 수와 중복 해석

| 자료 | 수량 | 주의점 |
|---|---|---|
| 초기 사람이 만든 학습 GT | 10장 | 모델이 만든 segmentation 결과와 구분 |
| 추가 검토 전체 손끝 GT | 13장 | 초기 10장과 합쳐 현재 학습 원본 23장 |
| V6 학습 타일 | 657개 | 독립 사진 657장이 아님 |
| 보수적 개발 분할 | 3그룹 | 사람·촬영 회차의 완전한 독립성은 미확인 |
| 가시성 사람 라벨 | 30장·67영역 | 기존 23장과 GT7 계열을 포함한 사용 자료. 추가 30장으로 합산 금지 |
| 가시성 분포 | 보임 53 / 미관찰 6 / 불확실 8 | 부정·모호 사례가 적음 |
| 사람 검토 V23 재생 | 기존 23장·57영역 중 보임 44영역 | 자동 검출 정확도가 아니라 검토된 범위의 실행 검사 |

가시성 자료에서 원본 파일 중복 0이 확인됐어도 촬영 그룹의 독립성을 의미하지 않습니다.
같은 촬영의 추가 사진·크롭·회전·다른 인코딩은 독립 최종 평가로 쓰지 않습니다.
AI가 만든 라벨 초안과 사람이 검토 완료한 정답을 분리합니다.
기존 30장 반복 검토가 진행되어 지금 다시 “미사용 holdout”으로 선언할 수 없습니다.

### 6.2 학습은 실제로 수행되었는가

V6의 38개 학습 가능 파라미터 텐서 변경, optimizer 포함, 고정 encoder/BatchNorm 유지, 유한값, 저장/재로딩, 모델·자료·소스 결합을 검사했습니다.
단순히 학습이 실행되지 않았다는 증거는 없습니다.

- 개발 OOF source-macro IoU: **V6 0.4836**, **V4 0.5527**.
- 그룹 동일 가중 IoU: V6 0.4705, V4 0.5005.
- 최종 학습 자료 적합 IoU: V6 **0.8243**.
- fold best epoch 4 / 1 / 12, 최종 epoch 4.

학습 적합과 그룹 평가의 차이는 일반화 위험을 보여 줍니다. 소수 촬영 그룹, 라벨 범위 정책, 입력 문맥, 분할 방식의 영향을 분리해야 합니다.
OOF에도 early stopping에 사용한 평가 정보가 있으므로 완전히 손대지 않은 최종 평가가 아닙니다.
사람 라벨이 잘못됐다고 확정하거나 epoch만 늘리면 해결된다고 단정하지 않습니다.
V6는 **영역 검출**을 학습합니다. 가시성 판단과 인공 지문 생성 전체를 end-to-end로 학습한 모델이 아닙니다.

### 6.3 보호 검증의 범위

[사람 검토 V23 기록](docs/PHOTO_REVIEWED_V23_DEMO_20261020.md)의 44영역에서 두 ROI 시야를 검사했습니다.
88개 ROI는 서로 연관된 자료이며 독립 88명/88장으로 표현하지 않습니다.
NBIS 전체 ROI 최대 127, SourceAFIS 전체 ROI 최대 64.189가 관측됐고, 특징점 부족 사례도 남았습니다.
마스크 밖 픽셀이 일부 높은 점수에 기여하는 진단 결과가 있지만 모든 매칭 원인을 규명한 것은 아닙니다.
잔존 질감 상관 경고 1영역도 원본 지문 잔존인지 오경보인지 확정되지 않았습니다.

위 검사는 사람이 정한 범위의 결과입니다. **자동 검출 누락까지 포함한 최신 V23 전체 보호 성능의 검증이 아닙니다.**
원본 자기 매칭만으로 별도 촬영의 동일인 참조 비교를 대신하지 않습니다.
가정 DPI·정규화·특징점 최소 수와 matcher별 척도를 기록하고, 점수 0·특징점 실패를 성공으로 바꾸지 않습니다.

## 7. 최근 수정과 회귀 검사

### 7.1 중요한 수정 이력

- 작은 mask 파편으로 전역 scale이 폭증하던 문제를 메모리 안전 검사와 컴포넌트·좌표 감사로 분리했습니다. 안전 거절과 검출 정확도는 별개입니다.
- RGB/L/RGBA·EXIF·색상 메타데이터를 경로별 계약에 맞게 검사합니다. scanner PNG에 PHOTO 로직을 억지 적용하지 않습니다.
- 후보 마스크와 실제 적용 mask가 달라 검은 가림이 조각으로 보이는 문제를 후보/적용/거절 표시와 별도 범위 경로로 구분했습니다.
- V6 체크포인트의 학습 소스 해시와 알려진 추가 검증 코드 사이의 한 방향 호환을 명시했습니다.
- 전체 손 BODY 주축이 엄지 방향을 잘못 결정하는 문제를 V24 국소 축 복구로 보완했습니다.
- 서버 중복 실행 시 같은 서버만 재사용하고 다른 프로세스·설정을 덮어쓰지 않게 했습니다.
- 최적화는 수학·임계값을 유지한 경계 적합 병렬화, 호출 내부 64MiB 캐시, 불필요한 중간 RGB 생략입니다.

### 7.2 최신 성능 근거

같은 3024×4032 개발 사진, 같은 모델·시드, 실제 검출 재실행 각 2회에서 AI 평균 **90.47초 → 78.85초**였습니다.
반환 RGB·적용/거절 마스크는 동일했습니다. 다른 개발 사진 3장은 기존 검출 출력을 재사용한 후속 경로 검사였습니다.
두 종류의 검사를 섞어 모두 새 사진·새 추론으로 보고하지 않습니다.
최적화 후 Android 실제 HTTP→저장/재읽기 1회는 약 96.77초였습니다.
현재 실시간 처리로 평가하지 않습니다.

### 7.3 재실행할 공개 검사

저장소 루트에서 다음을 시작점으로 사용합니다. 테스트는 합성 입력의 계약 검증이며 실제 모델 정확도 검사는 별도입니다.

```powershell
Push-Location ai/scripts
& "<AI-env>\Scripts\python.exe" -m unittest -v `
  test_photo_automatic_v23 test_photo_local_axis_v24 `
  test_photo_new_input_v23 test_photo_reviewed_demo_v23 `
  test_photo_v23_performance_v1 test_photo_junction_appearance_v23 `
  test_photo_skin_seam_v22 test_photo_silhouette_appearance_v21
Pop-Location

Push-Location backend
& "<backend-env>\Scripts\python.exe" -m pytest -q `
  test_experimental_photo_v2.py test_photo_v23_launcher.py
Pop-Location
```

추가로 [공개 기하 CI](../.github/workflows/photo-geometry.yml)의 합성 기준 비교·이전 합성 회귀를 유지합니다.
Android 변경 시 `android/`에서 `.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug`와 관련 계측 검사를 수행합니다.
JDK/SDK는 [Android 안내](../android/README.md)를 따릅니다.
검사를 실제로 실행한 날짜·커밋·환경·개수·skip·경고를 기록합니다. 과거의 665개/150개 등 서로 다른 범위의 수를 합치지 않습니다.

실제 사진 재현 시에는 원본 SHA, decoded RGB, 후보/적용/거절 mask, seed, 모델/코드 결합, 실제 저장 PNG 재읽기와 바깥 RGB 보존을 비공개 기록으로 남깁니다.
모델 출력을 캐시한 검사인지 fresh 추론인지 반드시 표시합니다.

## 8. 남은 작업 — 우선순위와 완료 조건

### P0. 인계받은 환경에서 실행 재현

1. Git 상태·모델·config·레지스트리·환경 버전을 확인합니다.
2. 공개 단위/계약 검사, private 개발 사진의 고정 시드 기준 재현을 수행합니다.
3. 거절·후보 없음·scanner 입력·잘못된 EXIF·과대 입력·timeout·중복 실행도 확인합니다.

**완료 조건:** 현재 버전의 실제 PNG·마스크·미적용 사유를 재현하고, 다른 결과는 첫 분기 지점을 설명할 수 있어야 합니다.
동일 시드 비교가 실패하면 원본→정규화→class map→BODY→소속 컴포넌트→경계→가시성→합성→PNG 순으로 최초 차이를 찾습니다.
임계값 완화로 차이를 숨기지 않습니다.

### P0. 전용 PC 자동 업로드 화면

사용자는 에뮬레이터 없이 사진만 넣어 자동 결과를 확인하는 방식을 요청했습니다.
기존 수동 검토 UI는 있지만 **같은 자동 V23 API를 사용하는 전용 업로드 화면은 구현 완료되지 않았습니다.**
이전 요청 중 설명·검토로 전환됐던 작업이며 완료로 표시하면 안 됩니다.

- 파일 선택 → 방향/색상 정규화 → `synthetic_v23` 요청 → 실제 결과/마스크 표시 → PNG 다운로드를 연결합니다.
- 대기·처리·취소·시간 초과·원본 유지/부분 처리 상태를 명확히 표시합니다.
- 서버 내부 파일 경로나 private 진단을 응답·로그에 불필요하게 노출하지 않습니다.
- 새로운 변환 알고리즘을 화면에 복제하지 않고 기존 API 검증을 사용합니다.
- 같은 입력에 대해 기존 API와 결과 계약이 일치하는지 검사합니다.

**완료 조건:** 새 사진의 정상/부분/거절/오류 흐름을 실제 업로드로 확인하고, 저장된 PNG가 서버 검증 결과와 일치해야 합니다.

### P1. 독립 검출·가시성 평가 자료 확보

현재 사용자는 추가 자료 준비가 어렵다고 답했습니다. 기존 자료로 개발은 가능하지만 이 제약을 독립 성능 완료로 대체할 수 없습니다.
준비가 가능해지면 서로 다른 새 촬영 회차 최소 2개 이상에서 선명/미관찰/모호 사례를 확보하고, 인원·기기·거리·빛·자세·가림·반사 조건을 기록합니다.
회차당 6–10장은 수집 시작 제안이며 충분한 통계적 검증량을 보장하는 숫자가 아닙니다.

- 손끝 외곽부터 첫 관절 주름까지의 범위와 지문선 가시성을 별도로 라벨링합니다.
- 모호한 경계·반사·흐림은 불확실로 남기며, 자동 결과를 보고 정답을 따라 그리지 않습니다.
- 그룹 split을 먼저 고정한 뒤 타일·증강을 만듭니다. 사람/촬영 그룹 중복을 audit합니다.
- 최종 평가 자료는 개발 중 시각 검사·threshold 선택·early stopping에 사용하지 않습니다.

**완료 조건:** 그룹 근거와 라벨 정책이 있는 자료에서 후보 재현율, 누락 손끝 수, IoU, 과대 영역, 가시성 confusion matrix, 불확실 비율을 각각 보고합니다.
실제 목표 수치는 사용 목적과 오판 비용을 담당자·팀이 사전에 정합니다.

### P1. 검출·경계·가시성 개선

검출 누락과 합성 거절을 먼저 나눕니다.

1. 후보 자체 없음: COLFISPOOF class map, V6, 프레임 잘림·크기·회전·연결 소속을 점검합니다.
2. 범위 오류: 전역/국소 축, 손끝 외곽, 첫 관절 주름, 작은 파편의 크기 추정 영향을 확인합니다.
3. 범위는 맞지만 거절: 흐림·반사·실제 무늬 부족과 관측 방향/해상도/유효 창 오류를 구분합니다.
4. 주기적 무늬의 오탐: 손등·손톱·피부 주름·배경 질감으로 부정 사례를 검사합니다.

V4/V6 또는 외부 분할 모델의 비교는 같은 데이터·그룹·평가 계약에서 수행합니다.
정확도가 좋아 보이는 사진만 선택하거나 같은 개발 사진에 threshold를 맞춰 독립 향상이라고 보고하지 않습니다.
**완료 조건:** 어떤 오류군이 개선됐는지와 나머지 오류군의 악화 여부를 동시에 제시하고, 채택/보류 버전을 명시합니다.

### P1. 실제 보호 효과 검증

- 검출하지 못한 지문과 마스크 바깥 노출까지 포함한 최종 반환 이미지로 평가합니다.
- 원본과 독립 촬영한 동일 지문 참조가 매칭 가능한지 먼저 확인합니다.
- 전체 ROI, 완전 내부 ROI, 압축/리사이즈 후 결과를 같은 조건으로 비교합니다.
- NBIS/SourceAFIS 추출 가능 비율·특징점 부족·원본 자기 매칭·독립 참조 비교를 분리합니다.
- 현재 남은 잔존 질감 경고를 확대 원본/결과로 확인합니다. 경고 임계값만 낮춰 없애지 않습니다.
- 합성 시드나 matcher 점수를 탐색해 유리한 결과만 선택하지 않습니다.

**완료 조건:** 평가 가능한 자료의 범위, 실패/불확실 수, 잔존 노출, matcher별 결과와 한계를 함께 설명할 수 있어야 합니다.
이 과정도 모든 인식기·공격에 대한 보편적인 개인정보 보호 증명은 아닙니다.

### P2. 자연스러움·속도·플랫폼

- 자연스러움: 내부가 과도하게 매끈한 현상, 능선 규칙성, 손끝 외곽·큰 주름의 이음새를 익명 순서의 전후 비교로 평가합니다.
  보기 좋게 만들려고 원본의 미세 지문 텍스처를 되살리지 않습니다.
- 속도: 여러 해상도·손가락 수에서 cold/warm, p50/p95, 최대 메모리, timeout·취소를 측정합니다.
  현재 후보 준비 약 50–56초, 그 안의 COLFISPOOF 약 21–24초가 한 개발 사진의 관측입니다.
  모델 상주 worker를 검토할 수 있지만 요청 간 이미지/seed/state 누출과 오류 복구부터 설계합니다.
- Linux: 최신 V23 실제 모델/중간 mask/가시성/반환 RGB를 비교합니다. 합성 기하 CI 통과만으로 최신 TensorFlow/모델 동등성을 주장하지 않습니다.
- 실물 Android: 사용자는 지금까지 에뮬레이터 검증만 선택했습니다. 실제 기기·네트워크·갤러리·대형 사진·백그라운드 전환은 다음 검증 대상입니다.
- 배포: 인증·HTTPS·업로드 제한·사용자별 격리·파일 보관/삭제·동시 요청·관측 가능한 오류를 구현하고 실제 운영 환경에서 검증합니다.

**완료 조건:** 목표 기기·배포 환경·성능 기준을 명시하고 해당 범위의 증거가 있어야 합니다. “코드가 있음”과 “제품 승인”을 분리합니다.

## 9. 흔한 오류와 대응

| 증상 | 먼저 확인할 것 | 해서는 안 되는 대응 |
|---|---|---|
| `photo_runtime_not_configured` | 새 shell의 COLFISPOOF 환경변수, 실행 파일·source·model | 후보 없음으로 덮어쓰기 |
| `consumed_source_or_decoded_pixels_forbidden` | 사용 자료 이력. 개발 재생이면 명시적 replay | 레지스트리 지우기, 독립 평가 주장 |
| `invalid_source_exif_orientation` | 실제 선택 파일, EXIF 값·형식, decode/정규화 진입점, scanner 분류 | 모든 방향을 무조건 1로 간주 |
| `completed_whole_pad_context_V6_development_checkpoint_required` | config/weights pairing, 학습 소스 해시와 문서화된 호환 | 체크섬이나 승인 플래그 직접 변경 |
| `fresh_*_output_required` | 출력 폴더가 이미 존재하는지 | 이전 결과 덮어쓰기 |
| 요청 중 source/config 변경 | 동시 편집·다른 작업·모델 교체 | 실행 중 무결성 검사 제거 |
| 후보는 있지만 적용 0 | 경계 확정·가시성 관측·예산 소진·원본 해상도 | 지문이 없다고 확정, 임의 pitch 생성 |
| `/ready` JSON만 보임 | 정상 상태 주소. 사진 선택 화면이 아님 | 서버 실패라고 보고 |
| “already running” | 기존 포트 프로세스·설정 재사용 안내 | 기존 설정이 새 옵션으로 바뀌었다고 가정 |
| 거대한 resize/메모리 오류 | 소속 컴포넌트·단위·행열·scale 추정과 사전 할당 한도 | guard 제거·샘플별 크기 강제 조절 |
| 결과가 오래 걸림 | 실제 검출 시간과 합성 시간, cold import, 동시 요청 | 동일 결과 검증 없이 해상도/임계값 하향 |

이 표는 오류를 무조건 환경 문제로 단정하는 지침이 아닙니다. 실제 입력과 최초 실패 지점을 재현한 뒤 논리 버그와 성능 한계를 분리합니다.

## 10. 다음 담당자의 작업 원칙과 보고

- read-only 감사, 의존성 확인, 일반 버그 수정과 테스트는 작업 범위 안에서 계속 진행합니다.
- frozen 수학 변경, 보호/가시성 기준 완화, 원본/사람 정답 수정, 미사용 평가 자료 재사용, 외부 공개 범위 변경은 팀과 결정합니다.
- 자동 판정을 사람 정답으로 승격하지 않고, 기존 모델/결과를 보존한 별도 버전으로 비교합니다.
- 변경 후 실제 설계대로 동작하는지 검사하고, 실패하면 원인을 해결한 뒤 다음 단계로 넘어갑니다.
- 자료·실물 기기·프로젝트 정책이 없어서 검증할 수 없는 경우에는 그 조건을 명시합니다. 임의의 완료 플래그를 만들지 않습니다.

보고는 평소에는 짧게 하되, 인계 가능한 기록에 다음을 남깁니다.

```text
SOURCE_COMMIT=
CHANGED_FILES=
DATA_ROLE=synthetic / consumed-development / untouched-final
MODEL_AND_RUNTIME_VERIFIED=
DETECTOR_MISSES_AND_OVERREACH=
VISIBILITY_FALSE_POSITIVE_FALSE_NEGATIVE_UNCERTAIN=
ACTUAL_RGB_AND_OUTSIDE_MASK_VERIFIED=
PROTECTION_EVALUATION_SCOPE=
TESTS_RUN_PASSED_FAILED_SKIPPED=
UNRESOLVED_LIMITATIONS=
NEXT_ACTION_AND_REQUIRED_HUMAN_INPUT=
```

공개 문서에는 집계·근거·재현 방법만 기록하고 개인 사진·원본 해시·정답·가중치·private diagnostics는 [비공개 인계 정책](PUBLIC_PRIVATE_DATA_KO.md)에 따라 분리합니다.
