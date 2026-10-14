# 2026-10-14 main 통합 및 검증

Linux 보존 bundle의 `3b2e814eba82a051de74f72d600d3bd72a4289eb`까지 미push 커밋 22개와 Windows 호환성 커밋 `e3a0ec6cf477b76281f494401276556c3304c5ea`을 원격 main에 통합했다. 기존 커밋의 작성자·날짜·SHA는 보존했으며, 다른 담당자의 기존 구현을 새 구현으로 재작성하지 않았다.

## 병합 검토

- `471481a`: 로컬 Windows 검증 이력과 원격 `70edcb2`까지의 Android batch 09/10 및 backend 변경을 병합했다. Android 처리 시간과 진단 기록 내보내기를 모두 보존하고 AI 문서의 한국어 번역과 Windows 실행 근거를 유지했다.
- `2c281d2`: Linux PHOTO/scanner 개발 이력을 병합했다. 중복 추가된 raw loader와 unified GUI는 Windows 경로 정규화·UTF-8·console 숨김을 보존했다. Linux 실험 문서와 기존 Windows 실행 근거를 함께 유지했다.
- `4195b61`: 제공된 matrix의 parity 범위와 현재 runtime 분리를 문서·상태·공개 집계에 기록했다. 과거 결과 보고서와 private reference는 수정하지 않았다.
- `bcb2922`: 검증 중 추가된 데이터 담당자의 `5c42b0f`, `40d6abb`을 병합했다. 새 전처리 모듈을 별도 경로로 유지하고 frozen AI 경로에 연결하거나 threshold를 바꾸지 않았다.

Windows NBIS 순차 빌드, PNG/OpenJPEG 의존성과 native stderr/exit-code 처리는 유지됐다. Android/backend/data의 최종 tracked 내용은 검토한 최신 원격 내용과 일치하며, AI Python 103개는 기존 Windows parity 검증 사본과 텍스트가 모두 동일하다.

## 직접 실행한 검증

- 통합 source의 AI unit tests: 156개 실행, 153 PASS, 선택적 PyTorch 3 SKIP.
- GUI regression: 3 PASS. 실제 Windows GUI smoke는 앞선 parity 검증에서 수행됐으며 동일 GUI source를 보존했다.
- backend: 100 PASS. 테스트 의존성은 별도 격리 환경에 설치했다.
- Android: 단위 테스트 131개, failures=0, errors=0, skipped=0; `testDebugUnitTest` 및 `assembleDebug` 성공. 실제 기기 instrumentation 테스트는 이번 통합에서 실행하지 않았다.
- 통합 main의 private unified matrix: holdout 8개, development_success, scanner_reference 모두 exact PASS; 최대 픽셀 오차 0. 새 private 출력 위치를 사용했다.
- AI Python 110개 syntax/import, frozen 공개 재현 검사 및 NBIS/SourceAFIS prerequisite inventory PASS. inventory를 새 native matcher 실행으로 간주하지 않았다.
- 추가 데이터 전처리 모듈의 syntax/import 및 기본 Gabor kernel 결정성 smoke PASS. 실제 사진 탐지 정확도나 보호 성능 검증으로 간주하지 않았다.
- private input/reference/model/upstream loader 32개 hash가 동일했다. 새 커밋의 비공개 경로와 secret 의심 항목 검토에서도 새 누출은 발견되지 않았다.

Android 최초 실행은 SDK Build-Tools 34 준비 후 PATH에 포함된 잘못된 따옴표가 `java.library.path`로 전달되어 테스트 JVM이 `Files`를 main class로 해석하며 실패했다. 테스트 프로세스 PATH만 정리해 재실행했고 통과했다. JDK 21과 pinned Gradle 8.9 archive는 checksum 검증 후 작업용 환경에 준비했다. 프로젝트 코드나 사용자 시스템 PATH를 변경하지 않았다. 기존 SDK XML/Deprecated API 경고와 잘못된 이미지 입력의 decoder 진단은 오류 없는 최종 결과와 구분한다.

## 보존 및 완료 범위

원본 Windows checkout의 기존 `data/` 작업 4개와 legacy GUI 파일은 그대로 유지했다. 원격 data 변경과 겹치는 미커밋 작업을 덮어쓰지 않도록 별도의 통합 main checkout에서 일반 push를 수행한다. 원본 checkout을 자동 stash/reset/clean하거나 강제 동기화하지 않는다. scratch clone의 자동 CRLF 정규화 차이는 별도 보존 후 clone 내부 Git attribute로만 처리했으며 원본 데이터 파일은 변경하지 않았다.

private images/masks/returned images/manifest/JSON/model/runtime/JAR 및 가상 환경은 새 커밋에 포함하지 않았다. 기존 원격의 Gradle wrapper와 공개 예제 이미지는 새 private payload로 추가하지 않았다. 알고리즘·threshold·frozen renderer·scanner·matcher 의미와 Linux reference는 유지했다.

Windows equivalence는 제공된 10-case unified outcome/region/native RGB 및 actual GUI smoke의 선언된 범위다. raw Linux TensorFlow 중간 tensor와 matcher score 동등성은 검증하지 않았다. PHOTO detector/production 승인, 최종 독립 보호 성능 및 PROJECT_COMPLETE는 false를 유지한다.

push 직전 origin/main을 다시 fetch하고, 일반 merge 및 필요한 검증 후 정상 push한다. 원격 SHA 일치는 별도 local 보고서에 기록한다.
