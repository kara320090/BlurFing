# BlurFing Backend

주담당: 한윤섭

## Docker 기반 Mock 배포

학교 Linux의 Docker·Compose·Nginx·Uvicorn·FastAPI 구성과 임시 HTTPS 실행은
[Mock 서버 배포 안내](README-deployment.md)를 따릅니다. 기본 공개 시험은 V1 Mock이며
실제 보호 처리를 하지 않습니다. 별도 [V2 API](README-photo-v2.md)는 보존하고 모델
미설정 시 503을 반환합니다. 아래 기존 V1 기능 설명과 진입점은 그대로 유지합니다.

요구사항 120개의 원문과 담당·백엔드 코드 참조는
[요구사항 추적표](requirements-traceability.json), 실제 모델이 완성된 뒤의 처리 시간
측정은 [AI 측정 안내](README-ai-measurement.md)를 확인하세요.

## 역할

백엔드는 보호 요청을 검사하고 연결된 처리 함수를 호출한 뒤, 결과를 검증해 API 응답으로 반환합니다. 현재 이 폴더에는 실제 블러 알고리즘이 없으며 AI 담당자의 모듈을 연결할 호출 지점과 개발용 Mock이 있습니다. 이 문서는 이 폴더의 코드·설정과 아래 명시한 실행 기록을 기준으로 작성했습니다.

## 파일 구성과 의존성

| 파일 | 역할 |
|---|---|
| `main.py` | FastAPI 앱, 요청 검사, 처리 함수 호출, 결과 검사, 응답과 중복 차단 |
| `mock_processor.py` | 지연 가능한 MockProcessor와 기본 인스턴스 |
| `mock_main.py` | 환경 변수로 지연 시간을 읽고 Mock을 연결하는 개발용 진입점 |
| `test_main.py` | 테스트 준비 도구와 함수 50개, 매개변수 포함 사례 114개; 실제 로컬 HTTP 연결 종료 검사 포함 |
| `check_mock_http.py` | 실행 중인 Mock 서버에 합성 PNG·JPEG를 보내는 HTTP 확인 도구 |
| `requirements.txt` | fastapi, pillow, python-multipart, uvicorn |
| `requirements-dev.txt` | 실행 의존성 포함 및 httpx, pytest 추가 |
| `README.md` | 구현 기능, 사용법, 테스트 범위와 제한 |

기존 `requirements.txt`와 `requirements-dev.txt`는 버전을 고정하지 않습니다.
배포용 `requirements-deploy.txt`는 직접 사용하는 패키지 버전을 별도로 고정합니다.

## 지금까지 구현한 것

- FastAPI 서버의 실행 확인용 `GET /`와 AI 모듈 연결 확인용 `GET /ready`
- `POST /v1/protect` 요청 검증: 이미지 형식·크기, 처리 방식·강도(0.1~1.0), 영역 좌표
- AI 처리 모듈을 호출할 연결 지점과 결과 이미지 형식·해상도 검사
- 성공·오류 응답 모델과 OpenAPI 응답 정의
- AI 처리 함수를 별도 스레드에서 실행하고 처리 결과 대기에 기본 30초 제한 적용
- 처리 중인 `request_id`의 중복 실행 차단
- 실행·대기 작업의 총 접수 한도 기본 4개와 한도 초과 시 `503 SERVER_BUSY` 반환
- 환경 변수로 처리 대기 시간·접수 한도 설정, 서버 시작 시 잘못된 값 거부
- 환경 변수의 모듈·호출 대상 경로로 처리기를 연결하고, 연결 실패 시 미연결 상태 유지
- 자동 연결 전에 위치 인자 4개의 호출 호환성을 검사하며 처리 함수는 실행하지 않음
- 오류 응답과 영역이 없을 때의 `no_regions` 응답
- 필수 입력값 누락을 포함한 오류 응답 형식 통일
- 없는 API의 404와 지원하지 않는 HTTP 메서드의 405도 공통 오류 형식으로 반환; 405의 Allow 헤더 유지
- 프레임워크 요청 검증 오류도 422 VALIDATION_ERROR와 공통 형식으로 반환; 요청 ID 외의 입력값·오류 상세는 비공개
- multipart 파싱을 포함한 HTTP 예외와 처리 블록 밖의 일반 예외도 공통 형식으로 반환; 업로드 읽기 실패 시 파일 닫기 시도
- 입력을 PNG로 저장해 반환하는 개발용 Mock과 별도 실행 진입점; 합성 RGB PNG·JPEG의 크기·픽셀 유지는 테스트로 확인
- 실행 중인 Mock 서버의 상태와 PNG·JPEG 입출력을 검사하는 HTTP 확인 스크립트
- 백엔드 테스트 114개 (서버 시작 설정·처리기 연결·인자 호환성 검사, 합성 이미지 기반 접수 한도, 실패·시간 초과·취소 후 자리 해제, 실제 HTTP 연결 종료 후 작업 유지·자리 반환, 지연 Mock, PNG·JPEG 반환, 용량 초과, 강도 경계·잘못된 값, 잘못된 영역, AI 결과 크기 오류, 404·405·422·multipart 파싱·업로드 I/O·처리 블록 밖 오류의 공통 응답, 내부 상세 비노출과 HTTP 헤더 보존 포함)

## 현재 상태

새 프로세스에서 `main:app` 실행 시 `BLURFING_PROCESSOR` 설정이 없거나 연결에 실패하면 처리 함수는 `None`입니다. 설정한 모듈의 동기 호출 대상을 불러오면 `app.state.protection_processor`에 연결합니다. 영역이 있는 보호 요청은 연결 전 `503 PROCESSOR_UNAVAILABLE`을 반환합니다. 개발용 `mock_main:app`은 같은 앱 객체의 처리기를 Mock으로 덮어씁니다. 이미지 검증까지 통과한 요청에 영역이 없으면 연결 여부와 관계없이 `200 no_regions`를 반환합니다. 실제 AI 알고리즘과 자동 영역 추출은 아직 이 폴더에 없으며, 아래 백엔드 검증 기록은 실제 AI 보호 성능을 검증한 결과가 아닙니다.

## 다음 할 일

1. 실제 AI 처리 함수 연결과 결과·오류 검증
2. 실제 AI 처리 환경에서 접수 한도·스레드 수와 메모리·처리 시간을 측정해 조정
3. 연결된 실제 처리기를 사용하는 앱·서버 통합 확인

위 목록은 계획이며 완료 항목이 아닙니다. 접수 한도·과부하 응답·코루틴 취소·처리 오류·파일 용량 초과는 아래 자동 테스트에 이미 포함돼 있습니다.

## 실행 및 테스트

`backend` 폴더에서 실행합니다.

```bash
pip install -r requirements-dev.txt
uvicorn main:app --reload
pytest -q
```

AI 모듈 연결 지점은 `app.state.protection_processor`입니다. 연결할 함수는 `(image_bytes, method, strength, regions)`를 받아 입력과 같은 크기의 완성된 PNG 바이트를 반환해야 합니다. 요청 강도는 BF-43 기준에 따라 양 끝값을 포함한 `0.1~1.0`의 유한한 숫자만 허용합니다. 실제 이미지 보호 방식과 강도 해석은 AI 담당자가 결정합니다.

백엔드 코드와 이 README는 BF-43 정의서의 강도 범위에 맞췄습니다. 백엔드 폴더 밖의 `contracts/protection-api.md`에는 아직 `0~1`로 표기되어 있으며, 이번 백엔드 전용 수정에는 포함하지 않았습니다. 앱·AI 연동 전에 공통 API 문서의 강도 표기도 맞춰야 합니다.

서버 실행 후 `GET /`는 서버가 실행 중이면 `200`을 반환합니다. `GET /ready`는 처리 함수가 연결되어 있으면 `200`과 `{"status":"ready"}`를, 연결되지 않았으면 `503`과 `PROCESSOR_UNAVAILABLE` 오류를 반환합니다. 예를 들어 `curl http://127.0.0.1:8000/ready`로 확인할 수 있습니다. 이 응답은 함수 연결 여부만 확인하며 실제 이미지 처리 성공이나 AI 보호 성능을 검증하지 않습니다.

처리 함수를 제출한 뒤 결과 대기에 설정된 제한 시간(기본 30초)을 적용합니다. 스레드 풀 대기 시간도 포함하지만 업로드·입력 검사·결과 이미지 검사·Base64 변환을 포함한 요청 전체의 제한은 아닙니다. 대기 제한을 넘으면 `504 PROCESSING_TIMEOUT`과 `retryable: true`를 반환합니다. 실행 중인 함수는 응답 뒤에도 계속 실행될 수 있습니다. 작업 자체를 중단하려면 처리 모듈의 취소 지원이나 별도 프로세스 격리가 필요합니다.

같은 `request_id`가 처리 중이면 후속 요청은 `409 REQUEST_IN_PROGRESS`와 `retryable: true`를 반환합니다. 실제 AI 함수가 종료되면 성공·실패와 관계없이 ID를 정리해 재시도할 수 있습니다. 시간 초과 응답을 반환했거나 요청이 취소됐어도 AI 실행이 남아 있다면 같은 ID를 계속 차단합니다. 이 중복 차단 상태는 서버 프로세스 안에서 관리되므로 여러 서버 프로세스를 함께 실행할 때는 공유 저장소를 이용한 중복 차단이 추가로 필요합니다.

시간 초과나 요청 취소는 AI 스레드를 강제로 중단하지 않습니다. AI 함수가 끝날 때까지 ID를 유지하므로 같은 ID의 이전 실행과 재시도가 겹치지 않습니다. 함수가 영구적으로 멈추면 해당 ID도 계속 차단되며 작업 자체의 취소·복구 기능은 별도 구현이 필요합니다. 완료된 결과를 저장하거나 같은 ID의 결과를 캐시하는 기능은 없습니다.

## 서버 환경 변수 설정

`main.py`를 처음 불러올 때 다음 환경 변수를 읽습니다. 기본 서버 `main:app`과 개발용 서버 `mock_main:app` 모두에 적용됩니다.

| 환경 변수 | 기본값 | 허용 값 |
|---|---|---|
| `BLURFING_PROCESSOR_TIMEOUT_SECONDS` | 30초 | 0보다 큰 유한한 숫자; 소수 허용 |
| `BLURFING_MAX_PENDING_PROCESSOR_REQUESTS` | 4개 | 0보다 큰 정수 |

변수가 없으면 기본값을 사용합니다. 빈 문자열, 숫자가 아닌 값, 0·음수, NaN·무한대는 거부합니다. 접수 한도의 소수 값도 거부합니다. 잘못된 값이 있으면 변수 이름을 포함한 `ValueError`로 앱 초기화가 실패하며, 임의로 기본값으로 바꾸지 않습니다.

PowerShell에서 대기 제한을 10초, 접수 한도를 2개로 설정하는 예입니다.

```powershell
$env:BLURFING_PROCESSOR_TIMEOUT_SECONDS = "10"
$env:BLURFING_MAX_PENDING_PROCESSOR_REQUESTS = "2"
uvicorn main:app --reload
```

Mock을 사용할 때는 마지막 명령을 `uvicorn mock_main:app --reload`로 바꿉니다. 설정을 바꾼 뒤에는 서버를 종료하고 같은 환경 변수를 지정한 터미널에서 다시 실행해야 합니다. 실행 중 자동 변경이나 `.env` 파일 자동 로딩은 구현하지 않았습니다. 기본값으로 돌아가려면 서버 종료 후 변수를 제거하고 다시 실행합니다.

```powershell
Remove-Item Env:BLURFING_PROCESSOR_TIMEOUT_SECONDS -ErrorAction SilentlyContinue
Remove-Item Env:BLURFING_MAX_PENDING_PROCESSOR_REQUESTS -ErrorAction SilentlyContinue
uvicorn main:app --reload
```

이 설정은 AI 처리 결과 대기와 실행·대기 작업 총 접수 한도만 바꿉니다. 스레드 풀의 스레드 수나 업로드 제한은 바꾸지 않습니다.

## 처리 모듈 자동 연결 설정

`main.py`를 처음 불러올 때 `BLURFING_PROCESSOR`를 읽습니다. 값은 `모듈명:호출대상명` 형식이며, Python import 경로에서 찾을 수 있는 모듈과 그 모듈의 동기 함수 또는 이미 생성된 호출 가능한 인스턴스를 지정합니다. 클래스 자체와 비동기 처리기는 거부합니다. 객체를 자동 생성하거나 비동기 함수를 await하지 않습니다.

백엔드 폴더에서 기존 Mock을 자동 연결하는 예입니다. 실제 AI 보호 처리는 하지 않습니다.

```powershell
$env:BLURFING_PROCESSOR = "mock_processor:mock_processor"
uvicorn main:app --reload
```

연결되면 `GET /ready`는 `200 ready`를 반환하고, 정상적인 영역 포함 요청은 기존 API를 통해 처리기를 호출합니다. 이 예에서는 `result_kind: mock`과 `MOCK_NO_PROTECTION` 경고를 유지하며 지연 없는 PNG 반환만 수행합니다. 실제 AI 모듈을 받으면 설정값을 AI 담당자가 제공한 모듈·호출 대상 이름으로 바꿉니다. 입력은 `(image_bytes, method, strength, regions)`, 반환값은 입력과 같은 크기의 완성된 PNG 바이트여야 합니다. 이 설정 기능은 실제 AI 연동 완료나 보호 성능 검증을 뜻하지 않습니다.

미설정·빈 값·공백뿐인 값이면 연결하지 않습니다. 잘못된 형식, import 중 예외, 없는 호출 대상, 호출 불가능한 대상, 클래스 또는 비동기 대상이면 연결하지 않고 서버 로그에 `BLURFING_PROCESSOR 연결 실패`와 예외 종류를 남깁니다. 4개 위치 인자를 받을 수 없거나 함수 시그니처를 확인할 수 없는 경우에도 연결하지 않습니다. 서버는 유지되며 `GET /`는 200, `GET /ready` 및 검증을 통과한 영역 포함 보호 요청은 `503 PROCESSOR_UNAVAILABLE`을 반환합니다. 오류 응답에 import 예외 내용을 노출하지 않습니다.

자동 연결은 `inspect.signature(processor).bind(...)`로 `(image_bytes, method, strength, regions)`의 위치 인자 4개를 전달할 수 있는지 검사합니다. 매개변수 이름이 같을 필요는 없습니다. 선택적인 추가 인자와 `*args`는 허용하지만 인자 수 부족, 추가 필수 인자, 위치 인자로 전달할 수 없는 필수 키워드 인자는 거부합니다. 시그니처를 확인할 수 없는 처리기는 호환되는 Python 함수로 감싸야 합니다. 검사 중 처리 함수는 호출하지 않습니다.

설정은 요청 입력이 아닌 서버 운영자가 관리하는 환경 변수입니다. 모듈을 불러오면 그 모듈의 초기화 코드가 실행됩니다. 인자 호환성 검사는 자동 연결 경로에만 적용하며, 함수 내부 동작·인자의 타입·실제 이미지 처리 성공·보호 효과를 검증하지 않습니다. import 시간 제한·자동 재시도·자동 모듈 검색·설정의 실시간 변경은 없습니다. 값을 바꾼 뒤 서버를 종료하고 같은 터미널에서 다시 실행합니다. 미연결 기본 상태로 돌아가려면 서버 종료 후 다음과 같이 실행합니다.

```powershell
Remove-Item Env:BLURFING_PROCESSOR -ErrorAction SilentlyContinue
uvicorn main:app --reload
```

`mock_main:app`은 이 설정으로 불러온 처리기를 개발용 Mock으로 덮어씁니다. 실제 AI 연결에는 `main:app`을 사용합니다. 기본 실행에서 환경 변수 없이 Mock을 자동 선택하지는 않습니다.

## 작업 접수 한도와 과부하 응답

한 프로세스에서 처리 함수에 제출할 수 있는 실행·대기 작업의 합계는 기본 4개입니다. `BLURFING_MAX_PENDING_PROCESSOR_REQUESTS` 환경 변수의 값이 `main.py`의 `MAX_PENDING_PROCESSOR_REQUESTS`에 반영됩니다. 코드를 수정하지 않고 환경 변수를 지정한 뒤 서버를 재시작해 조정할 수 있습니다.

영역이 있는 요청이 입력 검사와 처리기 연결 검사를 통과한 뒤 접수 한도를 검사합니다. 이미 등록된 ID는 한도가 차 있어도 `409 REQUEST_IN_PROGRESS`를 우선 반환합니다. 새 ID이며 한도가 차 있으면 작업을 제출하거나 ID를 등록하지 않고 다음 응답을 반환합니다.

```json
{
  "request_id": "요청한 ID",
  "code": "SERVER_BUSY",
  "message": "서버가 처리 중인 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
  "retryable": true
}
```

HTTP 상태는 503입니다. Retry-After 헤더나 자동 재시도는 구현하지 않았습니다. 실제 처리 함수가 성공·실패로 종료되면 ID와 접수 자리가 함께 반환됩니다. 시간 초과 응답·요청 코루틴 취소만으로는 자리를 반환하지 않습니다. 제출 실패 시에는 즉시 반환합니다. 거부된 ID도 자리가 생긴 뒤 다시 요청할 수 있습니다.

한도가 차 있어도 `GET /`와 `GET /ready`의 기존 동작은 유지됩니다. `/ready`는 접수 여유를 검사하지 않습니다. 잘못된 입력은 기존 입력 오류를, 빈 영역은 `no_regions`를 반환하며 이 요청들은 접수 자리를 사용하지 않습니다. 이 제한은 실제 AI 작업의 과부하 대응을 위한 기반이며 전체 서버의 메모리·CPU 사용량을 보장하는 기능은 아닙니다.

## main.py 전체 기능

### 서버와 설정

- `app`: 이름이 `BlurFing Backend`인 FastAPI 앱입니다. 모듈 초기화 마지막에 처리기 연결 설정을 적용하며, 미설정·연결 실패 시 `app.state.protection_processor`는 `None`입니다.
- `MAX_IMAGE_SIZE_BYTES`: 파일 크기 제한은 `15 * 1024 * 1024`바이트(15MiB)입니다.
- `MAX_IMAGE_PIXELS`: 이미지 해상도 제한은 가로×세로 2,000만 화소입니다.
- `PROCESSOR_TIMEOUT_SECONDS`: 환경 변수로 설정하는 AI 함수의 응답 대기 제한이며 기본값은 30초입니다.
- `MAX_PENDING_PROCESSOR_REQUESTS`: 환경 변수로 설정하는 실제 작업이 끝나지 않은 접수 ID 수의 프로세스당 한도이며 기본값은 4개입니다. 스레드 풀에서 실행 중인 작업과 대기 중인 작업을 합친 수입니다.
- `SUPPORTED_IMAGE_TYPES`: 업로드 MIME 타입은 `image/jpeg`, `image/png`를 허용합니다.
- `SUPPORTED_METHODS`: 보호 방식은 `gaussian_blur`를 허용합니다.
- `IN_FLIGHT_REQUEST_IDS`, `IN_FLIGHT_REQUEST_IDS_LOCK`: 처리 중인 요청 ID를 집합으로 관리하고 `threading.Lock`으로 등록·해제를 보호합니다.
- `PROCESSOR_EXECUTOR`: AI 함수를 실행하는 서버 프로세스 공용 스레드 풀입니다. 대기 중인 작업도 ID를 유지합니다.
- 스레드 수는 ThreadPoolExecutor의 기본값이며 코드에서 직접 지정하지 않습니다. API가 제출하는 실행·대기 작업 합계는 접수 한도로 제한합니다. 실행 수와 대기 수를 각각 별도 한도로 관리하지는 않습니다.
- FastAPI 기본 문서는 `/docs`, OpenAPI 명세는 `/openapi.json`에서 확인할 수 있습니다.

### API와 함수

| 함수 / API | 기능 |
|---|---|
| `read_positive_float_env` | 환경 변수의 실수 변환 및 유한한 양수 검사; 미설정 시 기본값, 잘못된 값은 변수 이름을 포함한 ValueError |
| `read_positive_int_env` | 환경 변수의 정수 변환 및 양수 검사; 미설정 시 기본값, 잘못된 값은 변수 이름을 포함한 ValueError |
| `load_protection_processor` | 환경 변수의 모듈·호출 대상을 불러와 동기 호출 가능 여부와 4개 위치 인자 호환성을 검사한 객체 반환; 미설정·연결 실패 시 None, 실패 이유의 예외 종류는 서버 로그에 기록 |
| `health_check` / `GET /` | AI 미연결 상태에서도 `200`과 `{"message":"BlurFing backend is running"}` 반환 |
| `readiness_check` / `GET /ready` | 처리 함수가 호출 가능한지 확인; 연결 시 `200 ready`, 미연결·호출 불가 시 `503 PROCESSOR_UNAVAILABLE` |
| `error_response` | 지정된 HTTP 상태와 `request_id`, `code`, `message`, `retryable`을 담은 `JSONResponse` 생성; 재시도 기본값은 false |
| `error_request_id` | 요청 상태에 저장한 문자열 ID의 공백을 제거해 반환; 확인된 ID가 없으면 빈 문자열이며 본문을 다시 읽지 않음 |
| `http_error_handler` | HTTP 예외의 상태를 유지해 공통 JSON 반환; 400 INVALID_REQUEST·404 NOT_FOUND·405 METHOD_NOT_ALLOWED, 나머지는 HTTP_ERROR; Allow 등 의미 있는 헤더 보존, 교체된 본문과 맞지 않는 헤더 제외; 400 미만은 기본 처리 유지 |
| `internal_error_handler` | 별도 처리되지 않은 일반 예외를 500 INTERNAL_SERVER_ERROR와 retryable true로 반환; 확인된 요청 ID만 유지하고 내부 예외 문구 비노출 |
| `validation_error_handler` | RequestValidationError를 422 VALIDATION_ERROR로 반환; 본문에서 문자열 요청 ID만 추출·공백 제거, 없거나 문자열이 아니면 빈 ID; 나머지 입력값·검증 상세 비노출 |
| `parse_strength` | 문자열을 실수로 변환하고 0.1~1.0 범위(양 끝값 포함) 및 유한한 숫자인지 검사 |
| `parse_regions` | 영역 JSON 배열과 좌표 조건을 검사하고 좌표를 실수로 변환; 생략 시 `None` 반환 |
| `claim_request_id` | 같은 잠금 안에서 중복 → 접수 한도 순서로 검사하고 허용된 ID 등록; accepted·duplicate·busy 반환 |
| `release_request_id` | 잠금 안에서 ID 제거; ID가 없어도 오류 없이 처리 |
| `protect_image` / `POST /v1/protect` | 정규화한 요청 ID를 요청 상태에 저장, 요청 검사, 업로드 읽기 및 finally에서 닫기, 영역 없음 처리, AI 연결·중복·접수 한도 검사, AI 호출·결과 검사, 정상·오류 응답 및 ID 정리 |

`/ready` 오류에는 빈 `request_id`와 `retryable: true`가 들어갑니다. 이 API는 실제 AI 처리를 실행하지 않습니다.

### 보호 요청 검사 순서

`POST /v1/protect`는 `multipart/form-data`로 전달된 값을 다음 순서로 검사합니다. 앞 단계에서 실패하면 뒤 단계와 AI 실행으로 넘어가지 않습니다.

1. `request_id` 앞뒤 공백 제거: 누락 또는 공백뿐이면 `400 INVALID_REQUEST_ID`.
2. `image`, `method`, `strength` 누락 검사: 누락 필드 이름을 포함한 `400 INVALID_REQUEST`.
3. 보호 방식 검사: `gaussian_blur` 외에는 `400 UNSUPPORTED_METHOD`.
4. 강도와 영역 검사: 숫자로 변환할 수 없는 강도, 0.1~1.0 범위 밖 값(0·0.05 포함), NaN·무한대, 잘못된 영역은 `400 INVALID_REQUEST`. 강도 오류 메시지는 `strength는 0.1에서 1.0 사이의 숫자여야 합니다.`이며 AI를 호출하지 않습니다.
5. 업로드 MIME 타입 검사: PNG·JPEG 외에는 파일을 닫고 `415 UNSUPPORTED_IMAGE_TYPE`.
6. 파일을 최대 제한 크기 + 1바이트까지 읽고 닫기: 빈 파일은 `400 EMPTY_IMAGE`, 15MiB 초과는 `413 IMAGE_TOO_LARGE`.
7. Pillow로 실제 형식·크기·내용 검사: 실제 형식도 PNG·JPEG여야 합니다. 2,000만 화소 초과는 `413 IMAGE_TOO_LARGE`; 식별·읽기·디코딩 실패와 Pillow의 압축 폭탄 오류는 `400 INVALID_IMAGE`.

15MiB 제한은 핸들러에서 업로드 파일을 읽은 뒤 적용하는 파일 제한입니다. HTTP 본문 전체나 multipart 파싱 전에 적용하는 제한은 아닙니다. MIME 타입과 실제 형식은 각각 허용 목록에 속하는지 검사하며 서로 일치하는지는 비교하지 않습니다. EXIF 방향 보정은 없습니다.

영역은 이미지 전체를 0~1로 나타내는 정규화 좌표입니다. `parse_regions`의 검사 조건은 다음과 같습니다.

- 최상위 값은 JSON 배열이어야 합니다.
- 각 항목은 `x`, `y`, `width`, `height` 네 키만 가진 객체여야 합니다. 누락·추가 키는 허용하지 않습니다.
- 좌표는 유한한 숫자여야 하며 문자열·불리언·NaN·무한대는 허용하지 않습니다.
- `x`, `y`는 0 이상이고 `width`, `height`는 0보다 커야 합니다.
- `x + width`, `y + height`는 각각 1 이하여야 합니다.

### AI 호출과 결과 처리 순서

1. 이미지 검증 뒤 영역이 생략됐거나 빈 배열이면 AI를 호출하지 않고 `200 no_regions` 반환.
2. 영역이 있으면 AI 함수의 호출 가능 여부 검사; 미연결·호출 불가 시 `503 PROCESSOR_UNAVAILABLE`.
3. 같은 잠금 안에서 요청 ID 중복 여부와 접수 한도를 검사합니다. 중복이면 `409 REQUEST_IN_PROGRESS`, 다른 ID이면서 한도가 차 있으면 `503 SERVER_BUSY`를 반환합니다. 허용된 ID만 등록하고 작업을 제출합니다.
4. 동기 AI 함수를 `PROCESSOR_EXECUTOR.submit`으로 제출하고 완료 콜백을 등록합니다. `asyncio.wrap_future`로 결과를 기다리며 `asyncio.shield`로 시간 초과·요청 취소가 작업에 전파되지 않게 하고 `asyncio.wait_for`로 설정된 제한 시간(기본 30초)까지 대기합니다. 이 제한에는 스레드 풀 대기 시간도 포함됩니다.
5. 대기 제한 초과 또는 처리 함수의 TimeoutError는 `504 PROCESSING_TIMEOUT`; 그 밖의 이 블록에서 잡힌 예외는 `500 PROCESSING_FAILED`로 처리합니다. 작업 제출 실패도 500에 포함됩니다.
6. AI 결과가 디코딩 가능한 PNG이고 입력과 가로·세로 크기가 같은지 검사. 실패하면 `500 PROCESSING_FAILED` 반환.
7. 검증한 PNG를 Base64로 변환하고 `200 succeeded` 반환. 내부 예외 내용은 오류 응답에 노출하지 않습니다.
8. 실제 작업 완료 콜백에서 요청 ID 해제. 응답 대기 시간 초과·요청 취소·요청 이벤트 루프 종료 후에도 작업 완료 시 해제됩니다. 제출 자체가 실패한 경우에만 `finally`에서 즉시 해제합니다. 결과 검증은 작업 완료 후 수행하므로 완료된 AI 결과를 검사하는 동안에는 ID가 이미 해제될 수 있습니다.

결과 대기 Future에는 예외를 읽는 콜백도 등록합니다. 요청 이벤트 루프가 살아 있는 동안 시간 초과 후 늦게 발생한 예외를 회수합니다. ID 해제는 이 콜백과 별개로 실제 스레드 작업의 완료 콜백에서 수행합니다.

AI 함수에 전달하는 값은 `(원본 이미지 바이트, 방식 문자열, 실수 강도, 검증된 영역 목록)`입니다. 영역 추출이나 블러 알고리즘은 이 파일에서 실행·구현하지 않습니다.

### 응답 모델과 OpenAPI

`RegionResponse`는 `x`, `y`, `width`, `height` 실수 좌표를 정의합니다. `ProtectionResponse`는 보호 API의 정상 응답 모델입니다.

| 정상 응답 필드 | 의미 |
|---|---|
| `request_id` | 앞뒤 공백을 제거한 요청 ID |
| `status` | `succeeded` 또는 `no_regions` |
| `result_kind` | MockProcessor 인스턴스이면 `mock`, 그 외 `real`; 실제 AI 여부·보호 효과를 인증하지 않으며 AI 미연결의 no_regions 응답도 real |
| `image_base64` | 처리된 PNG의 Base64 문자열; 영역 없으면 null |
| `mime_type` | 항상 `image/png` |
| `applied_regions` | 검증된 전달 영역 목록; 실제 보호 적용 여부를 검사한 결과가 아니며 영역 없으면 빈 목록 |
| `processing_ms` | 핸들러 시작부터 응답 생성까지의 경과 시간을 반올림한 밀리초 |
| `warnings` | 일반 정상 처리 시 빈 목록; 영역 없으면 `NO_REGIONS`; Mock 연결 시 `MOCK_NO_PROTECTION` 추가 |

`ErrorResponse`는 `request_id`, `code`, `message`, `retryable`을 정의합니다. 다음 표는 직접 반환하거나 404·405 및 요청 검증 예외 처리기로 변환하는 공통 오류입니다.

| HTTP | 오류 코드 | 원인 | retryable |
|---|---|---|---|
| 400 | `INVALID_REQUEST_ID` | ID 누락 또는 공백 | false |
| 400 | `INVALID_REQUEST` | 필수 값 누락, 강도·영역 오류 또는 multipart 파싱 등 HTTP 400 예외 | false |
| 400 | `UNSUPPORTED_METHOD` | 지원하지 않는 보호 방식 | false |
| 400 | `EMPTY_IMAGE` | 빈 이미지 파일 | false |
| 400 | `INVALID_IMAGE` | 실제 형식 오류 또는 이미지 읽기 실패 | false |
| 404 | `NOT_FOUND` | 요청한 API 주소가 없음 | false |
| 405 | `METHOD_NOT_ALLOWED` | 해당 API에서 지원하지 않는 HTTP 메서드; Allow 헤더로 허용 메서드 표시 | false |
| 409 | `REQUEST_IN_PROGRESS` | 같은 ID의 요청이 이미 처리 중 | true |
| 413 | `IMAGE_TOO_LARGE` | 파일 크기 또는 화소 제한 초과 | false |
| 415 | `UNSUPPORTED_IMAGE_TYPE` | 지원하지 않는 MIME 타입 | false |
| 422 | `VALIDATION_ERROR` | 파일 대신 일반 문자열을 보낸 경우 등 프레임워크 요청 입력 형식 검증 실패 | false |
| 500 | `PROCESSING_FAILED` | 작업 제출·실행 또는 결과 검증 블록에서 잡힌 일반 예외 | true |
| 500 | `INTERNAL_SERVER_ERROR` | 업로드 읽기·닫기, 입력 검사·Base64 변환 등에서 별도 처리되지 않은 일반 예외 | true |
| 503 | `PROCESSOR_UNAVAILABLE` | AI 함수 미연결 또는 호출 불가 | true |
| 503 | `SERVER_BUSY` | 실행·대기 작업의 총 접수 한도 초과 | true |
| 504 | `PROCESSING_TIMEOUT` | 처리 결과 대기 제한 초과 또는 처리 함수의 TimeoutError | true |
| 기타 4xx·5xx | `HTTP_ERROR` | 400·404·405 이외의 HTTPException; 원래 상태 유지, 상세 문구 비공개 | 429·5xx는 true, 나머지는 false |

`PROTECT_ERROR_RESPONSES`는 400·409·413·415·422·500·503·504의 설명과 `ErrorResponse` 모델을 OpenAPI에 등록합니다. 정상 200 응답에는 `ProtectionResponse` 모델을 사용합니다. 422도 FastAPI 기본 검증 오류 모델 대신 공통 오류 모델로 문서화합니다.

공통 오류 형식은 코드가 `error_response`로 직접 반환하는 응답과 HTTP 예외, `RequestValidationError`, 별도 처리되지 않은 일반 예외에 적용됩니다. multipart 파싱 실패가 HTTP 400 예외로 전달되면 `INVALID_REQUEST`를 반환합니다. 업로드 읽기·닫기 실패와 처리 블록 밖의 예상치 못한 예외는 `500 INTERNAL_SERVER_ERROR`로 반환합니다. 업로드 읽기는 `try/finally`로 감싸 읽기 실패 시에도 파일 닫기를 시도합니다. 기존 처리 블록의 `PROCESSING_FAILED`·`PROCESSING_TIMEOUT`은 유지합니다. retryable은 재요청 가능 표시이며 자동 재시도나 다음 요청의 성공을 보장하지 않습니다.

보호 핸들러 진입 후 확인한 요청 ID는 요청 상태에 저장해 HTTP·일반 예외 응답에 사용합니다. multipart 파싱 실패나 라우팅 오류처럼 ID를 확인하기 전에 실패하면 빈 문자열입니다. 예외 처리 중 본문을 다시 파싱하지 않습니다. HTTP 예외의 `Allow`, `Retry-After`, `WWW-Authenticate` 등은 보존하지만 원래 본문용 `Content-Length`, `Content-Type`, `Content-Encoding`, `Transfer-Encoding`은 새 JSON에 재사용하지 않습니다. 이는 예외에 이미 있는 헤더를 유지하는 기능이며 인증·요청 빈도 제한을 새로 구현한 것은 아닙니다. 304 등 오류가 아닌 HTTP 예외는 기본 처리로 넘겨 본문 없는 응답을 유지합니다.

공통 500 처리기는 응답 시작 전 ASGI 앱에 전달된 일반 예외를 대상으로 합니다. 이미 응답 전송이 시작된 뒤의 실패, 종료된 연결, 프로세스 종료, 서버 앞단의 프록시 오류는 같은 JSON의 전달을 보장하지 않습니다. `CancelledError` 등 취소·종료 신호를 일반 서버 오류로 바꾸거나 AI 작업을 강제로 중단하지 않습니다. 내부 예외 문구 비노출은 API 응답 기준이며 서버 로그의 별도 보관 정책을 구현한 것은 아닙니다.

없는 API 주소는 `404 NOT_FOUND`, 지원하지 않는 HTTP 메서드는 `405 METHOD_NOT_ALLOWED`를 반환합니다. 라우팅 단계에서는 폼의 요청 ID를 검사하지 않으므로 `request_id`는 빈 문자열이며 `retryable`은 false입니다. 405의 `Allow`로 허용 메서드를 확인할 수 있습니다. 두 상태는 라우팅 단계 응답이므로 보호 API의 개별 OpenAPI 응답 목록에는 등록하지 않습니다.

프레임워크 요청 검증 오류는 HTTP 422를 유지하고 `VALIDATION_ERROR`, `요청 입력 형식이 올바르지 않습니다.`, `retryable: false`를 반환합니다. 이미 파싱된 본문에서 문자열 `request_id`를 읽을 수 있으면 앞뒤 공백을 제거해 반환합니다. 본문이 매핑 형태가 아니거나 ID가 없거나 문자열이 아니면 빈 문자열로 반환합니다. ID 외의 입력값·검증 오류 상세·내부 예외 문구를 응답에 포함하지 않습니다. 기존 핸들러가 직접 처리하는 필수 값 누락·잘못된 강도 등은 계속 400을 반환합니다.

## test_main.py 전체 기능

### 테스트 준비 도구

- `client = TestClient(app)`: 별도 서버 실행 없이 FastAPI API를 호출합니다. 실제 연결 종료 검사는 이 클라이언트 대신 로컬 Uvicorn·TCP 소켓·httpx를 사용합니다.
- `load_settings_in_new_process()`: 처리기 경로와 두 서버 설정 변수를 정리한 별도 Python 프로세스에서 `main`을 불러와 기본값·지정값·초기화 실패를 검사합니다. 선택한 검사 스크립트를 실행해 처리기 연결과 API 동작도 확인합니다. 부모 프로세스의 앱이나 스레드 풀을 다시 만들지 않습니다.
- `synthetic_image()`: 흰 배경에 빨강·파랑 패턴이 있는 40×40 PNG를 메모리에서 생성합니다. 개인 사진·실제 지문은 사용하지 않습니다.
- `protect_request()`: 합성 PNG, 기본 요청 ID, `gaussian_blur`, 강도 0.5, 정규화 영역으로 요청을 만듭니다. 이미지와 폼 값을 덮어써 오류 조건을 재현하고 `request_client`로 다른 TestClient를 지정할 수 있습니다. 공통 500 응답 검사는 `raise_server_exceptions=False`로 프레임워크의 테스트용 예외 재전파 대신 HTTP 응답을 확인합니다.
- 테스트용 AI 함수를 연결한 테스트는 사용 후 함수를 해제합니다. `monkeypatch`로 변경한 제한 시간은 테스트 종료 시 복원됩니다.
- 중복 요청은 `ThreadPoolExecutor`와 `Event`로 첫 처리를 대기시키고 후속 요청을 보내 재현합니다.
- `request_released` fixture는 실제 ID 해제를 이벤트로 관찰합니다. 시간 초과·취소 테스트는 작업 종료 전 차단과 종료 후 재시도를 구분해서 확인합니다.

### 전체 테스트 목록

테스트 함수 50개이며, 매개변수별 사례를 포함하면 총 114개입니다.

| 테스트 함수 | 확인 내용 | 사례 수 |
|---|---|---|
| `test_startup_reads_server_settings` | 새 프로세스에서 미설정 기본값 30초·4개와 지정값 0.2초·2개 반영 | 2 |
| `test_startup_rejects_invalid_server_settings` | 각 변수의 빈 값·0·음수·NaN·문자열, 시간의 무한대·한도의 소수 거부; 초기화 실패와 오류 변수 이름 확인 | 12 |
| `test_startup_connects_configured_processor_or_stays_unavailable` | 새 프로세스의 미설정·빈 설정·Mock 연결·형식 오류·없는 모듈/대상·비호출 대상·비동기 함수·클래스·인자 비호환 함수 검사; health·ready·보호 API·Mock PNG 및 연결 실패 로그 확인 | 10 |
| `test_processor_signature_is_checked_without_running_it` | 4개 위치 인자·선택적 추가 인자·가변 인자는 허용, 인자 부족·추가 필수 인자·필수 키워드 인자·시그니처 확인 불가는 거부; 검사 시 미실행, 로그 및 API 정상/503 확인 | 7 |
| `test_mock_returns_png_with_original_pixels` | PNG·JPEG 입력 각각의 크기와 디코딩된 픽셀 유지, PNG 출력, mock 표시와 경고 | 2 |
| `test_mock_without_regions_is_marked_as_mock` | 빈 영역 응답에서도 mock 표시와 두 경고 유지 | 1 |
| `test_mock_entrypoint_connects_processor` | 환경 변수의 지연 0·0.01초 설정 반영, ready 응답 및 Mock API 호출 | 2 |
| `test_delayed_mock_waits_and_returns_image` | 고정밀 시계로 지정한 0.05초 이상 대기 확인 후 정상 Mock 응답 | 1 |
| `test_mock_rejects_invalid_delay` | 음수·NaN·양수 및 음수 무한대 지연 설정 거부 | 4 |
| `test_timeout_keeps_id_until_worker_finishes` | 시간 초과 후 동일 ID는 409·다른 ID는 SERVER_BUSY 유지, 늦은 성공·실패 각각의 실제 종료 후 200 재시도 | 2 |
| `test_cancellation_keeps_id_until_worker_finishes` | 코루틴 취소·이벤트 루프 종료 후 동일 ID는 409·다른 ID는 SERVER_BUSY 유지, 실제 작업 종료 후 200 재시도 | 1 |
| `test_live_http_disconnect_keeps_capacity_until_worker_finishes` | 실제 로컬 Uvicorn에 완전한 multipart 요청 전송 후 응답 전 TCP 연결 종료; 작업 중 동일 ID 409·새 ID 503, 성공·실패 각각의 작업 종료 후 두 ID 200 재시도; 서버 자동 종료 | 2 |
| `test_capacity_counts_running_and_queued_jobs` | 실행 1개·대기 1개로 한도 2개를 채워 503 전체 오류 필드·중복 우선 409·AI 미호출·상태 API·입력 검사·영역 없음 확인, 종료 후 거부됐던 ID 접수 | 1 |
| `test_processing_failure_releases_capacity` | 처리 함수 예외·잘못된 결과 각각의 실제 종료 후 새 ID 접수 가능 | 2 |
| `test_submission_failure_releases_capacity` | 작업 제출 실패 후 자리 해제와 새 ID 접수 | 1 |
| `test_root_reports_server_running_without_processor` | AI 미연결 상태의 서버 실행 응답 | 1 |
| `test_ready_reports_unavailable_without_processor` | AI 미연결 시 503과 오류 전체 필드 | 1 |
| `test_ready_reports_connected_processor` | AI 연결 시 200 ready | 1 |
| `test_ready_changes_to_available_after_processor_connection` | 연결 전 503에서 연결 후 200으로 전환 | 1 |
| `test_ready_changes_to_unavailable_after_processor_disconnection` | 연결 해제 후 200에서 503으로 전환 | 1 |
| `test_forwards_request_to_processor_and_returns_result` | 이미지·방식·실수 강도·영역 전달, 정상 응답 필드, Base64 결과의 크기와 처리된 픽셀 | 1 |
| `test_unconnected_processor_is_unavailable` | 영역이 있는 요청의 AI 미연결 오류 | 1 |
| `test_rejects_invalid_processor_output` | 이미지가 아닌 AI 결과 거부 | 1 |
| `test_rejects_processor_output_with_different_dimensions` | 입력과 크기가 다른 PNG 거부 및 오류 전체 필드 | 1 |
| `test_processor_failure_returns_server_error` | AI 예외 처리와 내부 예외 문구 비노출 | 1 |
| `test_processor_timeout_returns_retryable_gateway_timeout` | 시간 초과 504와 재시도 가능한 오류 전체 필드 | 1 |
| `test_duplicate_request_id_is_rejected_while_first_request_is_processing` | 동시 중복 요청 409 및 첫 요청 정상 완료 | 1 |
| `test_request_id_is_reusable_after_processing_finishes` | 성공·실패·시간 초과 사례 각각 실제 작업 종료·ID 해제 후 정상 재시도 | 3 |
| `test_empty_regions_do_not_claim_success` | 빈 영역은 no_regions, 결과 이미지는 null | 1 |
| `test_invalid_image_is_rejected` | 읽을 수 없는 입력 이미지 거부 | 1 |
| `test_rejects_strength_outside_supported_range` | 음수·0·0.05·0.099·1.1·NaN·무한대·문자열 거부, 오류 전체 필드와 AI 미호출 확인 | 8 |
| `test_accepts_strength_boundaries_and_forwards_to_processor` | 강도 0.1·1.0 각각 정상 응답 및 변환된 실수의 AI 전달 확인 | 2 |
| `test_rejects_region_outside_image_bounds` | x + width가 1을 초과하는 영역 거부 | 1 |
| `test_rejects_invalid_region_values` | 잘못된 JSON, 음수 x, 너비 0, NaN 높이; 오류 ID·코드·retryable 확인 | 4 |
| `test_rejects_image_over_15mb_before_processing` | 용량 초과 413 및 AI 함수 미호출 | 1 |
| `test_rejects_unsupported_method` | 알 수 없는 처리 방식 거부 | 1 |
| `test_rejects_unsupported_image_type` | GIF MIME 타입 거부 | 1 |
| `test_missing_required_input_uses_common_error_response` | image·method·strength 각각 누락, 필드 이름과 오류 전체 필드 | 3 |
| `test_missing_request_id_uses_common_error_response` | ID 누락 시 빈 ID와 오류 전체 필드 | 1 |
| `test_routing_errors_use_common_response_and_keep_allow_header` | 없는 주소 GET·POST의 404, 보호 API GET·상태 API POST의 405; 공통 오류 전체 필드·JSON 타입·Allow 헤더·처리기 미호출 | 5 |
| `test_framework_validation_error_uses_common_response` | 실제 요청의 422 공통 필드·JSON 타입·ID 유지/공백 제거/누락/공백뿐인 값, 입력값 비노출·처리기 미호출 | 4 |
| `test_validation_error_without_string_request_id_is_safe` | 본문 없음·비문자열 ID·파싱되지 않은 바이트 본문의 안전한 빈 ID 및 고정 오류 응답 | 3 |
| `test_multipart_parsing_errors_use_common_response` | boundary 누락·파트 name 누락의 실제 multipart 요청에서 400 공통 필드·빈 ID·내부 상세 비노출·AI 미호출 | 2 |
| `test_other_http_errors_keep_status_id_and_protocol_headers` | 테스트 전용 앱에서 401·429·503 HTTP 예외의 상태·확인된 ID·WWW-Authenticate/Retry-After 유지와 고정 오류 응답 | 3 |
| `test_http_error_replaces_stale_body_headers` | 새 JSON의 길이·타입 유지, 기존 Content-Encoding·Transfer-Encoding 제외, Allow 보존 | 1 |
| `test_non_error_http_exception_keeps_bodyless_response` | 304의 빈 본문과 ETag 유지 | 1 |
| `test_upload_io_error_is_safe_and_attempts_close` | 업로드 read·close 예외 각각 공통 500·정규화 ID·내부 상세 비노출·닫기 시도·AI 미호출·접수 ID 미등록 | 2 |
| `test_error_outside_processing_block_uses_common_response` | 입력 디코딩·결과 Base64 변환의 예상치 못한 예외에서 공통 500·ID·내부 상세 비노출·처리 ID 정리 | 2 |
| `test_unexpected_error_without_request_id_uses_safe_empty_id` | 테스트 전용 앱의 일반 예외에서 빈 ID와 공통 500·내부 상세 비노출 | 1 |
| `test_openapi_defines_protection_success_and_error_responses` | 정상 200과 여덟 오류 상태 등록, 422를 포함한 공통 응답 모델 참조 | 1 |

### 검증 범위

이 테스트는 합성 이미지와 테스트용 AI 함수로 백엔드 동작을 확인합니다. 실제 AI 보호 성능, 자동 영역 추출, Android 기기와 실제 서버 간 통신은 검증하지 않습니다.

2026-10-06 재실행 결과는 `44 passed, 2 warnings`입니다. Windows의 기존 테스트 의존성 경로와 Python 런타임에서 `pytest -q -p no:cacheprovider`로 실행했습니다. 경고는 Starlette TestClient의 httpx 사용 및 AnyIO 별칭에 관한 사용 중단 경고입니다. 이번 작업에서 새 환경에 의존성을 재설치하거나 Android 테스트를 실행한 것은 아닙니다.

2026-10-07 과부하 처리 추가 후 같은 환경·명령으로 실행한 결과는 `48 passed, 2 warnings`입니다. 실행·대기 작업 합계 제한, 오류 응답, 작업 종료 후 자리 반환을 합성 이미지·테스트용 처리 함수로 확인했습니다. 이날 실제 HTTP 서버·Android·실제 AI 성능 확인은 실행하지 않았습니다.

2026-10-08 서버 환경 변수 설정 추가 후 같은 환경·명령으로 실행한 결과는 `62 passed, 2 warnings`입니다. 새 Python 프로세스에서 기본값·지정값 적용과 잘못된 설정의 초기화 실패를 확인하고 기존 백엔드 테스트도 재실행했습니다. 경고는 위와 같은 의존성 사용 중단 경고입니다. 이날 실제 HTTP 서버·Android·실제 AI 성능 확인은 실행하지 않았습니다.

2026-10-09 BF-43 강도 범위를 0.1~1.0으로 맞춘 뒤 같은 환경·명령으로 실행한 최종 결과는 `71 passed, 2 warnings`입니다. 0·0.05와 그 밖의 잘못된 강도의 거부, AI 미호출, 0.1·1.0의 정상 전달을 확인했습니다. 최초 두 실행은 기존 Mock 지연 테스트에서 각각 `70 passed, 1 failed, 2 warnings`였습니다. 이 환경의 `time.monotonic` 해상도는 0.015625초로, 실제 약 0.05초 대기를 약 0.047초로 측정하는 것을 확인했습니다. 해당 테스트의 측정 시계만 `time.perf_counter`로 변경한 뒤 전체 테스트가 통과했습니다. Mock·서버의 대기 동작은 변경하지 않았으며, 실제 HTTP 서버·Android·실제 AI 성능 확인은 실행하지 않았습니다.

2026-10-10 처리 모듈 자동 연결 설정 추가 후 같은 환경·명령으로 실행한 결과는 `80 passed, 2 warnings`입니다. 새 Python 프로세스에서 미설정·빈 설정·정상 Mock 연결과 연결 실패 6종을 검사하고, 서버 실행·ready·보호 API 응답과 합성 PNG 반환을 확인했습니다. 실제 HTTP 서버·Android 기기·실제 AI 보호 성능 검증은 실행하지 않았습니다.

2026-10-11 처리기 인자 호환성 검사 추가 후 같은 환경·명령으로 실행한 결과는 `88 passed, 2 warnings`입니다. 정상 4개 위치 인자·선택적 추가 인자·가변 인자의 연결 유지, 비호환 인자와 확인 불가능한 시그니처의 연결 거부, 검사 단계의 처리기 미실행을 확인했습니다. 새 프로세스에서도 비호환 함수의 연결 실패와 health 200·ready/보호 API 503을 확인했습니다. 실제 HTTP 서버·Android 기기·실제 AI 보호 성능 검증은 실행하지 않았습니다.

2026-10-12 404·405 오류 응답 형식 통일 후 같은 환경·명령으로 실행한 결과는 `94 passed, 2 warnings`입니다. 없는 주소의 GET·POST와 정상 API의 잘못된 메서드에서 공통 오류 전체 필드, JSON 타입, Allow 헤더, 처리기 미호출을 확인했습니다. 프레임워크 422의 기존 detail 형식과 기존 백엔드 테스트도 통과했습니다. 실제 HTTP 서버·Android 기기·실제 AI 보호 성능 검증은 실행하지 않았습니다.

2026-10-13 요청 검증 오류의 공통 응답 처리 추가 후 같은 환경·명령으로 실행한 결과는 `100 passed, 2 warnings`입니다. 422 VALIDATION_ERROR의 전체 필드, 요청 ID 유지·공백 제거·빈 ID 처리, 입력값·오류 상세 비노출과 처리기 미호출을 확인했습니다. OpenAPI의 422 응답도 ErrorResponse를 참조하며 기존 400·404·405 및 정상 동작 테스트가 통과했습니다. 실제 HTTP 서버·Android 기기·실제 AI 보호 성능 검증은 실행하지 않았습니다.

2026-10-15 BF-52의 남은 오류 공통화를 실제 구현하고 같은 환경·명령으로 실행한 결과는 `112 passed, 2 warnings`입니다. multipart 파싱 실패, 업로드 읽기·닫기 실패, 처리 블록 밖 예외의 공통 응답과 내부 상세 비노출을 확인했습니다. HTTP 예외의 상태·헤더 보존, 새 JSON 본문의 헤더 정합성, 304의 빈 본문도 검사했으며 기존 취소·접수 한도·정상 처리 테스트가 통과했습니다. 이 날짜는 커밋 메타데이터와 별개인 실제 구현·테스트 실행일입니다. 검증은 TestClient·합성 이미지·오류 주입 기준이며 실제 HTTP 서버·Android 기기·실제 AI 보호 성능 검증은 실행하지 않았습니다. 두 경고는 기존 의존성 사용 중단 경고입니다.

2026-10-15 BF-49 실제 HTTP 연결 종료 테스트를 추가했습니다. 새 검사만 실행한 결과는 `2 passed, 112 deselected, 2 warnings`, 전체 재실행 결과는 `114 passed, 2 warnings`입니다. Windows 로컬 Uvicorn에 합성 multipart 요청을 전송하고 처리 시작 후 TCP 연결을 닫아, 작업 중 409·503과 Mock 작업의 성공·실패 후 ID·접수 자리 반환 및 200 재시도를 확인했습니다. 서버는 각 테스트에서 자동 종료했습니다. 기존 서버 구현이 이 조건에서 정상 동작해 `main.py`는 수정하지 않았습니다. 실제 Android 앱·실제 AI·HTTPS 배포 환경은 검증하지 않았고, 별도 `check_mock_http.py`의 PNG·JPEG 검사도 이번 작업에서 재실행하지 않았습니다. 경고 두 개는 위와 같은 기존 의존성 사용 중단 경고입니다.

코드에 구현됐지만 현재 전용 테스트가 없는 항목에는 공백 ID, 빈 이미지, 화소 제한 초과, 영역 생략, 영역 키·타입·y 경계 검사, 비PNG AI 결과, 설정 경로가 아닌 런타임에서 직접 등록된 호출 불가능한 처리기 등이 있습니다. 실행 1개·대기 1개의 동시 접수는 위 테스트로 확인하지만 실제 AI 작업 여러 개를 병렬 실행하는 부하 시험은 하지 않았습니다. 구현된 기능과 테스트로 확인한 범위는 구분해야 합니다.

### 실제 HTTP 연결 종료 검증 (BF-49)

`test_live_http_disconnect_keeps_capacity_until_worker_finishes`는 TestClient가 아닌 실제 로컬 Uvicorn 서버에 합성 PNG의 multipart 요청을 보냅니다. OS가 배정한 포트의 소켓을 서버에 직접 전달하고, 테스트가 서버 시작·종료를 관리합니다. 별도로 서버를 켜거나 고정 포트를 확보할 필요가 없습니다. 개발 의존성을 설치한 뒤 `backend` 폴더에서 다음 명령으로 두 사례를 실행합니다.

```bash
pytest -q -k live_http_disconnect
```

테스트 전용 `ControlledMock`은 기존 MockProcessor를 상속하고 첫 작업을 이벤트로 대기시킵니다. 작업 시작을 확인한 뒤 응답을 읽지 않고 클라이언트 TCP 연결을 닫습니다. 서버의 접수 한도를 1개로 설정해 다음을 확인합니다.

1. 작업이 끝나기 전 같은 ID는 `409 REQUEST_IN_PROGRESS`, 다른 ID는 `503 SERVER_BUSY`와 공통 오류 필드를 반환합니다.
2. 이벤트를 해제해 작업을 정상 완료하거나 테스트용 예외로 실패시키면 실제 완료 콜백이 ID와 접수 자리를 반환합니다.
3. 이전 ID와 접수 거절됐던 새 ID 모두 다시 요청해 `200 succeeded`, Mock 표시와 경고를 확인합니다.

이미지 파일은 저장하지 않으며 테스트용 서버·처리기 설정은 종료 후 정리·복원합니다. 운영 API나 작업 강제 중단 기능을 새로 추가하지 않았습니다. 검증 대상은 완전한 업로드 뒤 응답 대기 중 TCP 연결 종료입니다. 업로드 중단, 실제 Android 앱 취소, HTTPS·프록시·다중 프로세스 환경과 실제 AI 작업은 별도 확인이 필요합니다. 연결 종료가 모든 환경에서 서버 코루틴 취소로 전달된다는 뜻도 아닙니다.

## 이미지 반환 Mock 사용 방법

`mock_processor.py`의 `MockProcessor(delay_seconds=0)`는 호출 가능한 개발용 처리기입니다. 기본 인스턴스 `mock_processor(image_bytes, method, strength, regions)`는 AI 함수와 같은 입력을 받습니다. 설정된 시간만큼 대기한 뒤 Pillow로 이미지를 읽고 PNG로 저장한 바이트를 반환합니다. 크기 변경이나 픽셀 편집 코드는 없으며 합성 RGB PNG·JPEG의 크기·픽셀 유지는 테스트로 확인했습니다. 처리 방식·강도·영역은 적용하지 않으며 블러, 영역 추출, 성능 측정은 수행하지 않습니다. Mock 자체는 파일을 저장하지 않고 메모리에서 변환합니다.

모든 색상 모드를 PNG 저장 가능 모드로 변환하는 코드는 없습니다. PNG로 저장할 수 없는 입력 색상 모드는 변환에 실패해 API에서 500을 반환할 수 있습니다. EXIF 방향·메타데이터·다중 프레임 보존은 검사하지 않으며 원본 파일 바이트가 그대로 반환되는 것도 아닙니다.

`mock_main.py`는 공통 API 앱에 이 함수를 연결하는 개발용 진입점입니다. `backend` 폴더에서 다음 명령으로 실행합니다.

```bash
uvicorn mock_main:app --reload
```

지연 시간은 개발 서버 시작 전 `BLURFING_MOCK_DELAY_SECONDS` 환경 변수로 설정합니다. 기본값은 0초이며 음수·NaN·무한대 또는 숫자가 아닌 값은 서버 시작 단계에서 거부합니다. PowerShell에서 35초 지연으로 30초 시간 제한을 재현하려면 다음과 같이 실행합니다.

```powershell
$env:BLURFING_MOCK_DELAY_SECONDS = "35"
$env:BLURFING_PROCESSOR_TIMEOUT_SECONDS = "30"
uvicorn mock_main:app --reload
```

영역이 있는 요청을 보내면 약 30초 뒤 `504 PROCESSING_TIMEOUT`을 받습니다. 실제 Mock 작업이 끝나기 전 같은 ID로 다시 요청하면 `409 REQUEST_IN_PROGRESS`를 받습니다. 종료 후 같은 ID는 다시 접수되지만 35초 설정을 유지하면 새 요청도 504가 됩니다. 정상 200 응답을 확인하려면 서버를 종료한 뒤 아래 명령으로 지연을 없애고 다시 실행합니다.

```powershell
Remove-Item Env:BLURFING_MOCK_DELAY_SECONDS -ErrorAction SilentlyContinue
uvicorn mock_main:app --reload
```

서버 재시작은 메모리의 ID 상태를 초기화하므로, 재시작 전 동일 서버에서 409 차단을 먼저 확인합니다.

`http://127.0.0.1:8000/docs`에서 `POST /v1/protect`의 Try it out을 선택하고 합성 PNG 또는 JPEG를 업로드합니다. `request_id`는 `mock-001`, `method`는 `gaussian_blur`, `strength`는 `0.5`, `regions`는 `[{"x":0,"y":0,"width":1,"height":1}]`로 입력하면 이미지 반환 흐름을 확인할 수 있습니다. 영역을 생략하면 기존과 같이 이미지를 반환하지 않는 `no_regions` 응답입니다.

영역이 있는 정상 Mock 응답은 `200`, `status: succeeded`, `result_kind: mock`, `warnings: ["MOCK_NO_PROTECTION"]`이며 `image_base64`에 PNG가 들어갑니다. 여기서 succeeded는 입출력 처리가 완료됐다는 뜻이며 이미지가 보호됐다는 뜻이 아닙니다. `/ready`는 Mock도 호출 가능한 함수이므로 ready를 반환합니다.

실제 모듈 연동을 준비할 때는 개발 서버를 종료하고 `BLURFING_PROCESSOR`에 실제 처리기 경로를 설정한 뒤 `uvicorn main:app --reload`로 실행합니다. Mock은 명시적으로 설정한 경우에만 기본 서버에 자동 연결됩니다. 기존 입력 검증·시간 제한·중복 요청 차단·결과 검증은 Mock 실행에도 동일하게 적용됩니다.

## 실제 HTTP 이미지 입출력 확인

`check_mock_http.py`는 `TestClient` 대신 실제로 실행 중인 서버에 HTTP 요청을 보냅니다. pytest 114개와 별도로 실행하는 확인 도구이며, 합성 이미지와 반환 PNG는 메모리에서만 처리하고 파일로 저장하지 않습니다. 위 BF-49 연결 종료 검사와는 별도로 정상 PNG·JPEG 입출력을 확인합니다.

`backend` 폴더의 첫 번째 터미널에서 개발 의존성을 설치하고 지연 없는 Mock 서버를 실행합니다.

```powershell
pip install -r requirements-dev.txt
$env:BLURFING_MOCK_DELAY_SECONDS = "0"
$env:BLURFING_PROCESSOR_TIMEOUT_SECONDS = "30"
$env:BLURFING_MAX_PENDING_PROCESSOR_REQUESTS = "4"
uvicorn mock_main:app --host 127.0.0.1 --port 8765
```

두 번째 터미널에서 같은 `backend` 폴더로 이동해 실행합니다.

```powershell
python check_mock_http.py --base-url http://127.0.0.1:8765
```

주소를 생략하면 `http://127.0.0.1:8000`을 사용합니다. httpx의 연결·읽기·쓰기·풀 대기 제한을 각각 5초로 설정하며 요청 전체의 5초 마감 시간을 구현한 것은 아닙니다. 지연 Mock의 30초 대기 제한 확인에는 이 스크립트를 사용하지 않습니다. `trust_env=False`로 환경 변수의 프록시 설정을 사용하지 않습니다. 완료 후 첫 번째 터미널에서 `Ctrl+C`로 서버를 종료합니다.

스크립트의 확인 항목은 다음 네 가지입니다.

1. `GET /`: HTTP 200과 서버 실행 메시지 확인.
2. `GET /ready`: HTTP 200과 ready 상태 확인.
3. 합성 PNG 업로드: HTTP 200, 요청 ID·영역·Mock 표시·경고·출력 MIME 타입을 확인하고 Base64를 디코딩해 PNG 형식·48×32 크기·색상 모드·전체 픽셀 비교.
4. 합성 JPEG 업로드: 같은 항목을 확인하고 JPEG를 디코딩한 픽셀과 반환 PNG의 픽셀 비교. JPEG 저장 전 픽셀이 아니라 실제 업로드 파일의 디코딩 결과를 기준으로 합니다.

성공 시 `PASS: 4 live HTTP checks completed; no image files saved`와 종료 코드 0을 반환합니다. 연결 실패, HTTP 오류 또는 검증 불일치 시 `FAIL`과 종료 코드 1을 반환합니다. 실제 AI 함수가 연결된 서버의 응답은 `result_kind: mock` 검사를 통과하지 못합니다.

2026-10-05 확인 결과: Windows 로컬 Uvicorn Mock 서버(`127.0.0.1:8765`, 지연 0초)에 실제 HTTP 요청을 보내 네 항목 모두 통과했습니다. PNG·JPEG 모두 반환 PNG의 크기와 디코딩된 픽셀이 일치했고 확인 후 서버를 종료했습니다. 이 결과는 로컬 Mock 통신 확인이며 Android 기기 통신이나 실제 AI 보호 성능 검증은 포함하지 않습니다.

같은 날 서버 종료 후에는 연결 실패를 FAIL과 종료 코드 1로 보고하는 것도 확인했습니다. 이 HTTP 기록은 10월 5일 실행 결과이며 10월 6일에는 HTTP 서버 확인을 다시 실행하지 않았습니다.

### HTTP 확인 스크립트의 함수

| 함수 | 역할 |
|---|---|
| `require` | 조건이 틀리면 RuntimeError 발생 |
| `synthetic_image` | 48×32 RGB 패턴을 PNG·JPEG 바이트로 생성 |
| `check_image` | 업로드, 응답 필드 확인, Base64 유효성 검사와 이미지 비교 |
| `main` | 주소 인자 해석, 네 확인 항목 실행, 출력과 종료 코드 반환 |

## 현재 구현의 제한

- 설정한 처리기를 자동 연결할 수 있지만 이 백엔드의 검증 기록은 Mock·테스트용 처리기 기준이며 실제 AI 연동 완료의 근거는 아닙니다. 블러 처리·자동 영역 추출·지문 평가 점수 생성은 이 폴더에 없습니다.
- 접수 한도는 AI 호출 전 입력 검사 이후에 적용합니다. 전체 HTTP 접속 수·업로드·입력 디코딩 동시 수·요청 빈도를 제한하지는 않습니다. 기본 4개는 개발용 초기 설정이며 실제 AI 환경의 안전한 처리량을 측정해 정한 값은 아닙니다.
- ID 차단은 프로세스 메모리 안에서만 동작하며 재시작 시 초기화됩니다. 다중 프로세스·서버 공유 차단은 없습니다.
- 시간 초과나 코루틴 취소는 작업 자체를 중단하지 않습니다. 영구 정지한 처리 함수의 ID를 강제로 해제하는 기능도 없습니다. 로컬 Uvicorn에서 완전한 업로드 후 HTTP 연결을 끊었을 때의 작업 유지·완료 후 자리 반환은 Mock의 성공·실패 두 사례로 확인합니다. 연결 종료가 항상 코루틴 취소로 전달되는지, 실제 앱·배포 환경에서도 같은지는 별도 확인 대상입니다.
- ID는 처리 함수 종료 때 해제되므로 결과 검증·응답 전송 완료까지 동일 ID를 차단하지 않습니다. 영역 없음 응답은 ID 등록·중복 검사 전에 반환합니다.
- 출력은 PNG 여부·크기·디코딩 가능 여부를 검사합니다. 출력 파일 바이트 크기, 실제 블러 적용, 지정 영역만 변경됐는지, 보호 효과는 검사하지 않습니다.
- 입력 디코딩·결과 검사·Base64 변환은 핸들러에서 동기 수행합니다. 별도 스레드 실행과 설정된 제한 시간(기본 30초)은 처리 함수 결과 대기에 적용됩니다.
- 별도 결과 저장·캐시·자동 재시도·작업 상태 조회·취소 API·사용자 인증·CORS 설정·DB 연동·평가 API는 없습니다.
- Mock과 HTTP 확인 스크립트는 메모리에서 이미지를 처리하지만 업로드는 FastAPI/Starlette의 UploadFile을 사용합니다. 프레임워크가 큰 multipart 업로드를 임시 파일로 처리할 수 있으므로 서버 전체가 디스크를 전혀 사용하지 않는다고 보장하지 않습니다.
