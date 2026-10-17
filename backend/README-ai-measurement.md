# 학교 Linux의 실제 AI 처리 시간 확인

실제 AI를 공개하기 전에 `measure_photo_ai.py`로 학교 Linux에서 측정한다.
현재 모델은 개발 중이므로 사용자 요청에 따라 [Mock 배포](README-deployment.md)를
먼저 진행한다. Mock 배포에는 이 측정이 필요하지 않으며, Mock 응답 시간으로
실제 AI 시간을 대신하지 않는다.
기존 V1/V2 API와 AI 코드는 변경하지 않는다. 서버 시작·종료, 패키지 설치,
Docker 실행, Tunnel 설정, Git 변경도 이 도구에서 실행하지 않는다.

## 1. 환경만 확인하기

Linux의 실제 BlurFing 저장소에서 실행한다. 이 단계에는 Python 3.10 이상과
표준 라이브러리만 필요하며 AI를 실행하지 않는다.

```bash
python3 -B backend/measure_photo_ai.py preflight
```

JSON에 Linux/Python 정보, 커밋 SHA, V2 파일 존재 여부, 실행한 서버 Python의
패키지 버전, 도구 명령 유무, AI 환경변수 경로의 존재 여부만 출력한다.
경로 값·비밀번호·키·registry 내용은 출력하지 않는다. `present`는 존재한다는
뜻일 뿐, 모델 실행 가능이나 GPU 사용 확인은 아니다. `commands_available`은
컨테이너 내부 설치 여부나 서비스 가동 여부를 증명하지 않는다.
패키지 버전이 필요한 경우 아래 측정과 같은 서버 Python으로 다시 실행한다.

## 2. 실제 런타임 준비

- 최신 V2 구현(`experimental_photo_main.py` 등)과 `requirements-photo-v2.txt`의
  의존성이 있는 **서버 Python**이 필요하다. 오래된 체크아웃을 자동 갱신하지 않는다.
- AI 담당자가 준비한 **AI Python**, bridge, 비공개 consumed registry,
  해당 엔진의 실제 모델이 필요하다. 환경변수는 기존 V2와 동일하다.
  `BLURFING_PHOTO_PYTHON`, `BLURFING_PHOTO_BRIDGE`,
  `BLURFING_PHOTO_CONSUMED_REGISTRY`, `BLURFING_PHOTO_MODEL`,
  `BLURFING_PHOTO_ENGINES`, `BLURFING_PHOTO_TIMEOUT_SECONDS`,
  `BLURFING_PHOTO_TEMP_ROOT`, `BLURFING_PHOTO_DEVELOPMENT_REPLAY`를 사용한다.
- 기본 엔진 `native_v12`는 모델 폴더의 `final_config.private.json`과
  `final_context_whole_pad.pt`가 필요하다. 다른 엔진으로 자동 전환하지 않는다.
  V2와 동일하게 기본 제한 시간은 600초이며 설정을 덮어쓰지 않는다.
- 측정은 API와 별도 프로세스이므로 **기존 서버의 접수 한도를 공유하지 않는다.**
  실제 서비스/학습 작업과 충돌하지 않는 유휴 시간에 서버 관리자가 실행한다.
  기존 작업을 도구가 임의 종료하지 않는다.
- 사용 허가된 개발 사진만 비공개 경로에서 사용한다. 입력은 V2의 canonical
  opaque RGB PNG여야 한다(15MiB·2,000만 화소 이하). 자동 변환·축소·메타데이터
  제거는 하지 않는다. 실제 사진·모델·결과를 저장소에 추가하지 않는다.
- 평가에 소비된 입력은 기본적으로 거절된다. 개발 재현 허가가 있는 경우에만
  운영자가 replay를 명시하며, 도구가 이를 자동 활성화하지 않는다.
  반복 측정은 새로운 독립 성능 평가가 아니다.

## 3. 먼저 1회, 이후 반복·대기 포함 측정

아래 경로는 예시다. 실제 서버 Python과 허가된 입력 경로로 바꾸고,
위 환경변수는 Linux 셸에 직접 설정한다. 비밀값을 채팅에 보내지 않는다.

```bash
/path/to/server-venv/bin/python -B backend/measure_photo_ai.py measure \
  --image /private/authorized-canonical.png \
  --input-kind development-photo --engine native_v12 --runs 1
```

기본 실행 횟수는 1회다. 1회 결과를 확인한 후 같은 명령의 `--runs`를 `3`으로 바꾸어 반복한다.
대기 시간까지 확인할 때만 `--runs 2 --concurrency 2`를 사용한다.
동시 요청 2개도 기존 V2처럼 AI child는 1개만 실행되고 나머지는 대기한다.
합성 입력을 사용하는 경우 반드시 `--input-kind synthetic`을 명시한다.
Mock 결과로 대체하지 않으며 실제 보호 성능은 별도 검증 대상이다.

## 출력 해석

표준 출력의 JSON만 공유하면 된다. 이미지, mask, Base64, 입력 hash,
비공개 파일 경로, AI 내부 로그/예외 본문은 출력하지 않는다. 측정 결과 파일을
자동 저장하지 않는다. AI 임시 입출력은 기존 V2 런타임의 생성·정리 규칙을 따른다.

| 항목 | 의미 |
|---|---|
| `input_read_validate_ms` | 입력 파일 읽기와 canonical PNG 검사 시간(측정 준비 시 1회) |
| `bridge_processing_ms` | 검증된 bridge 응답의 원래 `processing_ms`; 순수 GPU 추론만의 시간은 아님 |
| `wall_ms` | 요청별 대기 + child 시작 + AI 처리 + 결과 검증 + 임시 자료 정리 시간 |
| `result_status` | `success`, `partial_success`, `rejected`; 거절도 유효한 반환 결과일 수 있음 |
| `completed` | 요청한 횟수의 검증된 응답을 받았는지; 보호 성공/배포 완료를 뜻하지 않음 |

매 요청마다 새 child를 실행한다. 두 번째·세 번째 요청을 모델 상주 상태의
warm inference로 해석하지 않는다. 반복 최대 10회, 동시 접수 최대 2개이며,
실패가 나오면 현재 묶음까지만 마치고 후속 묶음을 실행하지 않는다.
중단은 Ctrl+C로 요청한다. child 종료 확인에 실패하면 기존 V2의 unavailable/
비공개 임시 자료 보존 규칙을 유지하므로 관리자의 확인 없이 재시도하지 않는다.

종료 코드: `0`=환경 보고 생성 또는 모든 측정 응답 검증, `1`=실행 중 실패,
`2`=설정/입력/준비 오류, `130`=사용자 중단. preflight의 `0`은 AI 준비 완료가 아니다.

이 도구는 HTTP 업로드·응답 직렬화·Nginx·Cloudflare·앱 구간을 측정하지 않는다.
이후 실제 HTTPS에서 별도로 검증해야 한다. 특히 Cloudflare의 기본 proxy read
timeout은 현재 125초이므로, 관측 시간과 업로드·반환 여유를 확인하기 전에는
현재 동기식 API의 외부 서비스 가능 여부를 확정하지 않는다.
[Cloudflare 524 공식 설명](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)

## 검증 범위

`test_measure_photo_ai.py`는 가짜 런타임으로 출력 제한·반복·접수·오류·취소
제어를 검사한다. 이 테스트의 실행 시간은 실제 AI 측정값이 아니다.
학교 Linux의 실제 모델 실행, GPU 사용, 처리 시간, 외부 HTTPS 검증은 별도로
실행한 결과가 있을 때만 완료로 기록한다.
