# 2026-10-21 Windows 새 센서 취득 버튼·같은 서버 연결

담당: 이봉헌(Windows·서버 연결). 기존 AI 처리기·SourceAFIS 어댑터·공식 FFV SDK는 재사용했다. Android를 실행하는 학교 서버를 Windows에서도 이용해 새 센서 영상의 원본·처리본·매칭 점수를 보는 요청을 구현했다. 서버 담당자의 `0894c02`를 fast-forward로 반영했고 Android 기능 코드는 수정하지 않았다.

## 변경

- `지문 취득 후 자동 비교` 버튼: 센서 API 준비 확인 → 요청별 FFV helper 실행 → 새 SDK PNG 취득 → 기존 센서 API 호출 → 검증한 원본·처리본·SourceAFIS 원시 점수 표시. 첫 설정 이후 별도 FFV 창 조작·처리 버튼이 필요 없다.
- helper는 설치된 FFV 공개 Enroll/GetBitmap을 호출한다. 요청 전용 임시 등록 DB만 사용하고 정리 후 영상을 전달한다. 구형 FFV 미리보기/기존 등록 지문을 요청 결과로 재사용하지 않는다. 취소·실패·정리 실패는 새 영상/점수가 아니다.
- 같은 사용자 전용 요청별 pipe, 길이·형식 검사, 소유 프로세스 종료/취소, 구형 미리보기와 버튼 작업 분리. 설정은 서버·DPI·취득기 위치만 저장하며 지문·전송 동의를 복원하지 않는다.
- 학교 Ubuntu의 별도 센서 API(8002)를 기존 HTTPS의 `/scanner/ready`, `/scanner/v1/scanner/compare`에 연결하는 실행·검사·백업·원복 도구와 systemd 템플릿을 추가했다. 기존 사진/V1 경로·터널을 재생성하지 않는다.
- [실행·서버 적용 안내](../../sensor/ONE_CLICK.md). SourceAFIS 원시 점수를 백분율로 바꾸거나 매칭 실패에 가짜 점수를 부여하지 않았다.

## 이번 실행 결과

| 검사 | 이번 결과 | 범위 |
|---|---|---|
| Windows 계약·요청별 helper pipe | 22/22 통과 | 합성 영상·자식 프로세스, 취소·형식·정리 실패·다음 요청·기존 계약 |
| Windows + loopback 실제 HTTP | 25/25 통과 | 위 22개 + 실제 로컬 HTTP/worker 응답·취득 fixture부터 저장·HTTP 취소. matcher fixture이며 실제 점수 아님 |
| 센서 API·신규 경로·기존 사진 프록시 검사 | 56 통과, 29 subtests | `sensor/server/test_scanner_api.py`, `sensor/server/test_gateway.py`, `backend/test_photo_gateway.py`. Docker 없이 합성 검사 |
| Windows 배포 | 자체 포함 win-x64 0.2.0 빌드 | .NET 별도 설치 불필요. 새 EXE 합성 preview 4초 조기 종료 없음 |
| 공식 FFV 확장 | Framework 4.8 x64 컴파일 성공 | 설치된 SDK 공개 클래스 참조. 실제 장치 취득 아님 |
| 공개 서버 읽기 확인 | 사진 `/v2/ready` 200, `/scanner/ready` 404 | 실제 추론·점수 측정이 아님. 센서 API 미연결 상태 |

첫 HTTP 묶음에서는 취소 시험 직후 다음 시험을 실행해 자식 정리 중 429가 발생했다. 전체 취득·저장 검사를 취소 검사보다 먼저 수행하도록 시험 순서를 분리한 뒤 25개가 통과했다. 서버의 사용 중 거절을 완화하거나 실제 취소·정리 시간을 제거하지 않았다.

현재 PC의 연결 장치 목록에서 BioMini/Suprema/Xperix 지문 장치를 확인하지 못했다. 실제 BioMini 취득, 학교 scanner AI/NBIS/SourceAFIS, 외부 HTTPS 처리·성능, Ubuntu systemd·Nginx 적용은 미검증이다. 학교 서버 SSH 대상이 제공되지 않아 원격 설정을 변경하지 않았다. 사용자는 Android 서버를 그대로 재사용하기 원하며 새 서버·Android 재배포는 필요 없다.

## 전달과 남은 확인

바탕화면 `BlurFing_센서원클릭_20261021`에 EXE·확장 helper·설정·서버 안내·소스를 묶는다. 공식 SDK·모델·실제 지문은 전달 ZIP과 Git에 넣지 않는다. `validation.json`의 SHA256과 소스 커밋을 확인한다. 공개 지문/학습 자료 추가, 가짜 성공률, 모델 학습은 하지 않았다.

서버 담당자가 같은 호스트에서 센서 runtime을 준비하고 안내의 검사·실행·프록시 연결을 적용한 뒤, 실제 새 센서 취득 → 학교 서버 처리 → 유효한 원시 점수 → 비교 저장을 연속 3회 확인해야 한다. 준비 200과 합성 검사만으로 전체 구현의 실제 장비 검증을 완료 처리하지 않는다.
