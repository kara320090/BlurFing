# AI 공개·비공개 자료 구분

공개 대상은 **재현 가능한 소스·합성 테스트·개인 정보를 제거한 결과 요약**입니다.
실제 지문과 손 사진은 원본뿐 아니라 마스크·변환본·썸네일·매칭 특징도 별도로 관리합니다.
폴더 이름이 `results`나 파일 이름이 `report.json`이라는 이유만으로 공개 가능한 것은 아닙니다.

## 1. GitHub에 포함하는 자료

| 자료 | 포함 조건 |
|---|---|
| `ai/scripts/` Python 소스 | 실제 사진·가중치·비밀 설정을 코드 안에 삽입하지 않음 |
| 테스트 소스 | 실행 시 생성하는 합성 무늬·배열·가짜 fixture 사용 |
| `ai/app/`, `ai/platform/` | 화면 소스·플랫폼 어댑터·일반화한 실행기만 포함 |
| README, 인수인계, 설계·검증 문서 | 개인 경로·사진·개별 지문 특징 없이 버전과 검증 범위를 설명 |
| `ai/results/`, 공개 status JSON/CSV | 익명 ID·집계 수치 등 검토된 요약만. 실제 private report 복사 금지 |
| `ai/config/` 예시 | 자리표시자와 합성 기준만. 토큰·실제 private 경로 제외 |
| 모델 명세·공식 다운로드 출처·공식 체크섬 | 모델 라이선스·배포 조건을 따름. 실제 가중치는 별도 취득 |
| backend / Android / contracts의 AI 연결 변경 | 자동 V23 실행에 필요한 전송·검증·UI·테스트도 함께 보존 |

## 2. GitHub에 포함하지 않는 자료

| 자료 | 예시 / 이유 |
|---|---|
| 실제 손·지문 원본 | JPEG/PNG/BMP/TIFF/WSQ, 스캐너 영상, 촬영 폴더 |
| 원본으로부터 만든 결과 | 보호 PNG, 검은 가림, crop, overlay, 비교 HTML 속 사진, PDF·영상 |
| 사람 정답과 검토 상태 | `ground_truth_mask.png`, 라벨링 ZIP, 대표 사각형, visibility state, roster |
| 개인 단위 진단 | `*.private.json`, 원본·픽셀 식별 해시, 이미지 경로, 세부 실행 로그 |
| 학습/사용 자료 레지스트리 | `consumed_registry.private.json`, 샘플별 split·manifest·학습 config |
| 학습 산출물 | `.pt`, `.pth`, `.onnx`, `.h5`, `.safetensors`, TensorFlow graph/checkpoint |
| 모델 입력·캐시 | `.npy`, `.npz`, pickle, 학습 타일·중간 feature |
| NBIS/SourceAFIS 개인 결과 | minutiae/template, 실제 지문 점수 목록·특징점 파일 |
| 외부 프로그램·저장소 복제본 | COLFISPOOF 전체 복사본, SDK·DLL·JAR·가상환경, private kit |
| 인증·신원 자료 | `.env`, 토큰·키·동의서·사진 속 식별정보, 개인 계정 설정 |
| 배포 빌드·로컬 실행 결과 | APK, EXE, ZIP, 개인 경로가 고정된 편의용 CMD/PS1 |

비공개 경로에서 생성된 비교 결과는 팀 내부 공유 시에도 포함 사진의 공유 권한을 확인합니다.
검은 가림 또는 합성 처리본도 일반적인 익명화가 검증된 자료로 취급하지 않습니다.

## 3. 새 담당자에게 별도로 전달할 최소 자산

읽기 권한이 제한된 팀 드라이브 등으로 전달하고, GitHub issue나 공개 첨부로 올리지 않습니다.

1. **V6 모델 폴더**: `final_context_whole_pad.pt`와 대응하는 `final_config.private.json`.
2. **사용 자료 레지스트리**: 실제 사용 이력이 기록된 `consumed_registry.private.json`. 빈 레지스트리로 재작성하지 않습니다.
3. **검증용 입력 최소 세트**: 동의 범위 내 개발 사진, 원본 좌표 마스크·가시성 라벨, 기준 반환 결과, 고정 시드와 실행 버전.
4. **재학습용 자료**: GT10 + 추가 검토 13장, manifest·촬영 그룹 근거, 30장 가시성 검토 상태. 사진 수가 겹치므로 단순 합산하지 않습니다.
5. **공식 외부 자산**: COLFISPOOF·MediaPipe 모델 및 필요시 NBIS/SourceAFIS runtime. 라이선스가 허용하면 내부 전달, 아니면 공식 출처에서 재취득합니다.
6. **무결성 목록**: 전달 파일별 SHA-256, 패키지 버전, source commit, 학습/평가에 이미 사용했는지 기록. 이 목록도 비공개입니다.

공개 코드만으로 합성 단위 검사는 가능하지만, 위 자산 없이 실제 모델 추론·동일 결과·재학습 재현을 완료했다고 보고하면 안 됩니다.

## 4. 업로드 전 확인 방법

`.gitignore`는 실수 방지 장치이며 **이미 추적 중인 파일과 이전 커밋을 제거하지 않습니다.**

```powershell
git fetch origin
git status --short
git log --oneline origin/main..HEAD
git diff --name-status origin/main...HEAD
git diff --cached --name-status
git ls-files ai
git rev-list --objects origin/main..HEAD
```

검토할 것은 최종 파일뿐 아니라 **push로 새로 공개되는 모든 커밋에서 도달 가능한 파일 내용**입니다.
확장자, 실제 바이너리/이미지 헤더, 긴 Base64 삽입, 개인 경로, 토큰 패턴을 함께 확인합니다.
자동 패턴 검사만으로 완전한 개인정보 검사가 되지는 않으므로 JSON/CSV·문서 내용도 확인합니다.

검토한 파일을 `git add <명시적 경로>`로만 stage합니다. `git add .`, `git add -A`, `push --force`는 사용하지 않습니다.
공유 이력을 임의로 재작성하지 않습니다. 이미 공개된 민감 자료를 찾으면 추가 공개를 멈추고 접근 제한·자격 증명 폐기 등 해당 자료에 맞는 대응을 정합니다.

## 5. 이번 정리의 범위

자동 V23·V24 경계 보완·최적화까지의 AI 소스, 이전 버전 소스, 관련 앱/서버 계약, 테스트와 공개 요약을 함께 인계합니다.
개인 사진·마스크·가중치·private 진단·기존 비교 결과는 로컬 비공개 위치에 보존하며 GitHub에 포함하지 않습니다.
개인 경로가 고정된 로컬 편의 실행기 대신 저장소의 매개변수형 실행기를 사용합니다.
