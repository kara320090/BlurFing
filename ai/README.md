# AI

주담당: 유재윤

## 담당 범위
BlurFing의 지문 변환 알고리즘과 NBIS / SourceAFIS 기반 성능 검증 파트.

## Frozen baseline
- Renderer: natural_auto_04 (`scripts/natural_auto_04.py`)
- Compositor: boundaryblend_02 (`scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py`)
- Matchers: NBIS 5.0.0 / SourceAFIS 3.18.1

## 현재 상태
기술 파이프라인, Linux NBIS 및 SourceAFIS 검증을 완료했습니다. NBIS 공식 ZIP 기반 clean rebuild 재현과 development ROI 평가를 완료했습니다. 최종 독립 촬영본 검증은 추후 진행 예정입니다.

```text
TECHNICAL_PIPELINE_COMPLETE=true
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```

## 데이터
실제 지문/손 사진은 개인정보·생체정보 보호를 위해 공개 저장소에 포함하지 않습니다. 데이터, private runtime, JAR, archive, historical 개인 manifest도 포함하지 않습니다.

## Repository layout
- `ai/scripts/`: frozen 코드, 필요한 custom helper, Java/native bridge source.
- `ai/docs/`: pipeline, development validation, 제한사항 및 SourceAFIS artifact metadata.
- `ai/results/`: 익명 development 결과와 NBIS clean rebuild 요약.
- `ai/requirements.txt`: 공개 Python 코드의 실제 외부 package dependencies.
- `ai/.gitignore`: private 데이터·runtime·생성물 제외 규칙.

## 설치
Python 3.10 이상 및 Linux 환경을 사용합니다. 아래 명령은 저장소 root 기준입니다.

```sh
python3 -m venv ai/.venv
ai/.venv/bin/python -m pip install -r ai/requirements.txt
ai/.venv/bin/python ai/scripts/reproduce_frozen_pipeline.py --check
```

공개 `--check`는 코드 존재만 확인하며 원래 private 작업본의 촬영본 55개·archive·runtime 검증을 대신하지 않습니다. private NBIS runtime 검사는 `--nbis-config /path/to/nbis_runtime_linux.json`을 추가합니다.

SourceAFIS 실행에는 Java/Javac 11 이상과 별도로 준비한 SourceAFIS 3.18.1 및 전이 의존성 JAR 15개가 필요합니다. `docs/sourceafis_runtime.json`의 공식 URL·SHA-256을 사용하고 JAR을 `ai/private/sourceafis/lib/`에 준비합니다. Java bridge source는 공개되며 adapter는 필요 시 `/tmp`에서 Java 11 target으로 컴파일합니다. 다운로드와 Java 실행은 공개 준비 작업에서 수행하지 않았습니다.

NBIS는 공식 NBIS 5.0.0 source로 별도 빌드합니다. `scripts/native/nbis_local_linux.cpp`와 공식 headers/static libraries를 사용합니다. runtime JSON은 다음 계약을 따르며 실제 absolute ELF path와 SHA-256을 지정해야 합니다.

```json
{"version":"NBIS5.0.0","contract":"blurfing-raw-match-v1","exe":"/path/to/nbis_local_linux","exe_sha256":"<actual_sha256>"}
```

실행 command에만 `BLURFING_NBIS_LINUX_CONFIG=/path/to/nbis_runtime_linux.json`을 지정합니다. 생성물은 공개 저장소에 commit하지 않습니다.

## 실행

```sh
ai/.venv/bin/python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input /path/to/input.jpg
```

입력은 사용 권한이 있는 private 사진을 사용합니다. 반환 이미지·diagnostic은 새 `/tmp` 디렉터리에만 기록됩니다. 구조 검사 실패 시 해당 영역은 원본을 반환합니다. 직접 Python API를 사용할 때도 Linux entry point의 matcher/OUT wiring을 사용해야 합니다.

## 검증
공개 결과는 development-only입니다. 세 development ROI에서 두 matcher 모두 original→transformed score가 self-match보다 크게 낮았습니다. 최종 독립 검증 결과는 아직 없습니다. matcher별 score scale이 다르므로 직접 비교하지 않습니다.

## 제한사항
일반적인 지문 보호 효과 또는 완전한 자연스러움 입증이 아닙니다. synthetic ridge regularity와 texture seam이 일부 남아 있습니다. Windows full equivalence와 independent holdout validation은 미완료입니다. matcher 점수는 본인 일치 확률이 아니며 특징점 추출 실패를 보호 성공으로 계산하지 않습니다.

추가 설명: [pipeline](docs/PIPELINE.md), [validation](docs/VALIDATION.md), [limitations](docs/LIMITATIONS.md).
