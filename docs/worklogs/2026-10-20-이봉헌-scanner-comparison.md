# 2026-10-20 FFV 센서·서버 처리·매칭 3열 프로그램

요청: Windows FFV에서 BioMini Slim 2 영상을 취득한 뒤 학교 Ubuntu 서버에서 처리하고 원본·처리본·매칭 점수를 나란히 표시한다. 사용자가 실제 학교 서버 연결은 다음 날 진행하기로 명시했다. 관련 범위 BF-08·10·12. Windows·시스템 통합 구현은 이봉헌이며 센서·AI·백엔드 담당자의 실장비·성능 검증을 대신한 것으로 기록하지 않는다.

## 구현

- `sensor/BlurFing.ScannerComparison`: .NET 10 Windows Forms 독립 프로그램. 원본/실제 서버 처리본/SourceAFIS 원시 점수의 3열, 파일 입력, 서버 설정 확인, 수동·FFV 새 취득 자동 처리, 취소, 새 입력·늦은 응답 격리.
- `sensor/ffv-extension/BlurFingComparisonBridge.cs`: 공식 FFV 샘플의 새 미리보기 영상만 복사해 같은 Windows 사용자의 named pipe로 전달한다. 기존 취득·등록·검증 SDK 호출을 바꾸지 않는다. 전송은 기본 꺼짐이며 이전 화면 영상은 보내지 않는다. 기존 파일을 유지하도록 `BlurFingFfvCompare.exe`라는 별도 이름으로 컴파일했다.
- `sensor/server`: 기존 scanner 실험 처리기·SourceAFIS를 호출하는 별도 FastAPI/child 어댑터. PHOTO 라우트는 처리기 호출 전 거절한다. 기존 AI 수학·품질 임계값·matcher·V1/PHOTO V2 계약은 변경하지 않았다.
- 반환의 요청·원본 byte/pixel SHA256·해상도·PNG SHA256·실제 변경 픽셀·점수 상태를 확인한다. worker의 추가 필드·템플릿·비공개 경로는 반환하지 않는다. matcher 미준비·실패·특징점 0은 임의 0점이나 보호 성공으로 표시하지 않는다.
- 저장은 사용자가 고른 새 폴더의 `original.png`, `processed.png`, `comparison.json`, `hstack.png`다. SDK 원본 파일은 변경하지 않으며 업로드용 PNG는 픽셀을 유지해 정규화한다. DPI는 설정값이다. 원본/처리본 직접 매칭은 독립 신원 참조나 보호 성능 승인이 아니며 점수를 백분율로 변환하지 않는다.
- 이미지·템플릿은 서버의 요청별 임시 폴더에 격리하고 정상·실패·취소 뒤 정리한다. Unix process group/Windows process tree 종료를 구현했다. 앱은 사진을 자동 저장하지 않으며 주소·DPI만 로컬 설정에 보관한다.

## 실행한 검증

Windows, .NET SDK 10.0.400, Python 3.13의 기존 검증 환경에서 실행했다. 모든 입력은 합성 그라데이션·체커보드 또는 작은 공개 합성 회색조다. Python child 시험의 AI·매칭 함수는 제어된 fixture이며 실제 AI/SourceAFIS 실행으로 집계하지 않는다.

- 새 Windows 검사 **19/19 통과**. 회색조 픽셀·해시 보존, 잘못된/컬러/과대 입력, 100을 초과하는 원시 점수, 미측정·빈 특징점, 이전 요청·원본·해시 불일치, 중복 JSON, HTTPS 주소, multipart 전송, 취소, 실제 named pipe의 잘못된 발신 뒤 복구, PNG·JSON·3열 저장을 검사했다.
- 실제 loopback HTTP를 추가한 최신 Windows 검사 **21/21 통과**. Windows 클라이언트→실제 Uvicorn→scanner API→실제 Python child→제어된 합성 처리/매칭→Windows 응답 검증을 실행했다. 실행 중 실제 HTTP 취소가 child 종료·임시 폴더 정리로 이어지는 것을 확인했다. 앞의 19개를 포함하는 수치다.
- 서버 검사 **28개 통과·경고 1개**(기존 Starlette의 httpx 사용 안내). 입력·DPI·중복·크기/실제 수신량·응답 위변조·추가 비공개 필드 차단·혼잡·정상/실패 정리·실제 child timeout·연결 종료·취소 후 slot 재사용·PHOTO fallback 차단을 검사했다.
- 기존 `BlurFing.SensorCapture.Checks` **16/16 통과**. 기존 UFS 수집 소스는 변경하지 않았다.
- FFV 확장 `.NET Framework 4.8 / x64` 컴파일 완료. 기존 FFV SDK 바이너리를 재배포하거나 수정하지 않았다.
- Windows x64 자체 포함 단일 EXE publish 완료. 최초 build는 경고 0·오류 0이다. native runtime도 포함하도록 `IncludeNativeLibrariesForSelfExtract=true`를 사용했다.
- 실제 Windows 창에서 3열 배치와 합성 패턴 표시·미측정 점수·전송 전 비활성 상태를 확인했다. 합성 화면에 가짜 AI 영상·실제 측정 점수를 넣지 않았다.

최초 API 검사에서 PNG의 EXIF 조회가 load를 유발해 `verify()` 순서를 위반하는 문제를 재현했다. 검증 직후 다시 연 이미지에서 EXIF를 읽도록 수정했다. multipart 해석 전에 실제 envelope를 제한하는 ASGI 계층을 추가해 초과 시 413을 유지했다. 동시 .NET restore로 발생한 최초 publish 자산 충돌은 검사·publish를 순차 실행해 해결했다. 최종 검증과 publish는 모두 성공했다.

## 미실행과 다음 연결

학교 Ubuntu 접속·설치·Nginx/Tunnel 변경·실제 AI 모델/NBIS/SourceAFIS 점수 계산·새 FFV 확장의 실제 센서 취득→서버 전체 흐름은 이번에 실행하지 않았다. 사용자가 요청한 다음 날 연결에서 수행한다. Ubuntu의 실제 process-group 종료·SDK/센서 취득 성공·일반 보호 성능을 Windows 합성 검사로 승인하지 않는다. 기존 배포는 Mock 중심이며 센서 API를 배포했다고 표시하지 않는다.

관련 안내: [프로그램](../../sensor/SCANNER_COMPARISON.md), [Ubuntu 준비](../../sensor/server/README.md). 기본 main `bdfcbdf`의 팀원 Android 주소 변경을 fast-forward로 반영했으며 팀원 커밋·작성자를 유지했다. 작업 전 존재하던 data 미커밋 파일 5개는 해시로 보존 확인한다. 실제 지문·개인 사진·SDK·서버 비밀정보는 Git에 추가하지 않는다.

AI 도구 사용: Codex로 Windows·IPC·API 어댑터와 합성 회귀 검사를 작성·실행했다. 실제 서버/센서 시험과 담당자의 최종 검토는 별도다.
