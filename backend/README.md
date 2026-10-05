# BlurFing Backend

주담당: 한윤섭

## 역할

백엔드는 보호 요청을 검사하고 AI 담당자의 처리 모듈에 전달한 뒤, 결과를 확인해 앱에 반환합니다. 블러 알고리즘 자체는 AI 파트에서 구현합니다.

## 지금까지 구현한 것

- FastAPI 서버의 실행 확인용 `GET /`와 AI 모듈 연결 확인용 `GET /ready`
- `POST /v1/protect` 요청 검증: 이미지 형식·크기, 처리 방식·강도, 영역 좌표
- AI 처리 모듈을 호출할 연결 지점과 결과 이미지 형식·해상도 검사
- 성공·오류 응답 모델과 OpenAPI 응답 정의
- AI 처리 함수를 별도 스레드에서 실행하고 30초 처리 제한 적용
- 처리 중인 `request_id`의 중복 실행 차단
- 오류 응답과 영역이 없을 때의 `no_regions` 응답
- 필수 입력값 누락을 포함한 오류 응답 형식 통일
- 이미지 크기·픽셀을 유지해 PNG로 반환하는 개발용 Mock과 별도 실행 진입점
- 합성 이미지 기반 백엔드 테스트 44개 (지연 Mock, 시간 초과·취소 후 중복 차단, PNG·JPEG 반환, 용량 초과, 잘못된 영역, AI 결과 크기 오류 포함)

## 현재 상태

기본 `main:app` 실행 시 AI 모듈은 연결되지 않습니다. 영역이 있는 보호 요청은 연결 전 `503 PROCESSOR_UNAVAILABLE`을 반환합니다. 개발용 `mock_main:app` 실행 시에는 Mock이 연결됩니다. 영역이 없으면 연결 여부와 관계없이 `200 no_regions`를 반환합니다. 자동 영역 추출과 실제 AI 보호 성능은 아직 검증하지 않았습니다.

## 다음 할 일

1. AI 담당자의 보호 처리 모듈을 연결하고 결과를 검증하기
2. 요청 취소·처리 오류·용량 제한을 점검하기
3. Android 앱과 합성 이미지로 실제 통신 테스트하기

## 실행 및 테스트

`backend` 폴더에서 실행합니다.

```bash
pip install -r requirements-dev.txt
uvicorn main:app --reload
pytest -q
```

AI 모듈 연결 지점은 `app.state.protection_processor`입니다. 연결할 함수는 `(image_bytes, method, strength, regions)`를 받아 입력과 같은 크기의 완성된 PNG 바이트를 반환해야 합니다. 이미지 보호 방식과 강도 해석은 AI 담당자가 결정합니다.

서버 실행 후 `GET /`는 서버가 실행 중이면 `200`을 반환합니다. `GET /ready`는 처리 함수가 연결되어 있으면 `200`과 `{"status":"ready"}`를, 연결되지 않았으면 `503`과 `PROCESSOR_UNAVAILABLE` 오류를 반환합니다. 예를 들어 `curl http://127.0.0.1:8000/ready`로 확인할 수 있습니다. 이 응답은 함수 연결 여부만 확인하며 실제 이미지 처리 성공이나 AI 보호 성능을 검증하지 않습니다.

AI 처리 응답은 최대 30초까지 기다립니다. 제한을 넘으면 `504 PROCESSING_TIMEOUT`과 `retryable: true`를 반환합니다. 동기 처리 함수는 별도 스레드에서 실행되므로 시간 초과 응답 뒤에도 해당 함수가 끝날 때까지 내부 실행이 이어질 수 있습니다. AI 모듈 자체를 즉시 중단하려면 해당 모듈의 취소 지원이나 별도 프로세스 격리가 추가로 필요합니다.

같은 `request_id`가 처리 중이면 후속 요청은 `409 REQUEST_IN_PROGRESS`와 `retryable: true`를 반환합니다. 실제 AI 함수가 종료되면 성공·실패와 관계없이 ID를 정리해 재시도할 수 있습니다. 시간 초과 응답을 반환했거나 요청이 취소됐어도 AI 실행이 남아 있다면 같은 ID를 계속 차단합니다. 이 중복 차단 상태는 서버 프로세스 안에서 관리되므로 여러 서버 프로세스를 함께 실행할 때는 공유 저장소를 이용한 중복 차단이 추가로 필요합니다.

시간 초과나 요청 취소는 AI 스레드를 강제로 중단하지 않습니다. AI 함수가 끝날 때까지 ID를 유지하므로 같은 ID의 이전 실행과 재시도가 겹치지 않습니다. 함수가 영구적으로 멈추면 해당 ID도 계속 차단되며 작업 자체의 취소·복구 기능은 별도 구현이 필요합니다. 완료된 결과를 저장하거나 같은 ID의 결과를 캐시하는 기능은 없습니다.

## main.py 전체 기능

### 서버와 설정

- `app`: 이름이 `BlurFing Backend`인 FastAPI 앱입니다. `app.state.protection_processor`의 초기값은 `None`입니다.
- `MAX_IMAGE_SIZE_BYTES`: 파일 크기 제한은 `15 * 1024 * 1024`바이트(15MiB)입니다.
- `MAX_IMAGE_PIXELS`: 이미지 해상도 제한은 가로×세로 2,000만 화소입니다.
- `PROCESSOR_TIMEOUT_SECONDS`: AI 함수의 응답 대기 제한은 30초입니다.
- `SUPPORTED_IMAGE_TYPES`: 업로드 MIME 타입은 `image/jpeg`, `image/png`를 허용합니다.
- `SUPPORTED_METHODS`: 보호 방식은 `gaussian_blur`를 허용합니다.
- `IN_FLIGHT_REQUEST_IDS`, `IN_FLIGHT_REQUEST_IDS_LOCK`: 처리 중인 요청 ID를 집합으로 관리하고 `threading.Lock`으로 등록·해제를 보호합니다.
- `PROCESSOR_EXECUTOR`: AI 함수를 실행하는 서버 프로세스 공용 스레드 풀입니다. 대기 중인 작업도 ID를 유지합니다.
- FastAPI 기본 문서는 `/docs`, OpenAPI 명세는 `/openapi.json`에서 확인할 수 있습니다.

### API와 함수

| 함수 / API | 기능 |
|---|---|
| `health_check` / `GET /` | AI 미연결 상태에서도 `200`과 `{"message":"BlurFing backend is running"}` 반환 |
| `readiness_check` / `GET /ready` | 처리 함수가 호출 가능한지 확인; 연결 시 `200 ready`, 미연결·호출 불가 시 `503 PROCESSOR_UNAVAILABLE` |
| `error_response` | 지정된 HTTP 상태와 `request_id`, `code`, `message`, `retryable`을 담은 `JSONResponse` 생성; 재시도 기본값은 false |
| `parse_strength` | 문자열을 실수로 변환하고 0~1 범위 및 유한한 숫자인지 검사 |
| `parse_regions` | 영역 JSON 배열과 좌표 조건을 검사하고 좌표를 실수로 변환; 생략 시 `None` 반환 |
| `claim_request_id` | 잠금 안에서 중복 여부 검사와 ID 등록; 이미 등록돼 있으면 false 반환 |
| `release_request_id` | 잠금 안에서 ID 제거; ID가 없어도 오류 없이 처리 |
| `protect_image` / `POST /v1/protect` | 요청 검사, 영역 없음 처리, AI 연결·중복 검사, AI 호출·결과 검사, 정상·오류 응답 및 ID 정리 |

`/ready` 오류에는 빈 `request_id`와 `retryable: true`가 들어갑니다. 이 API는 실제 AI 처리를 실행하지 않습니다.

### 보호 요청 검사 순서

`POST /v1/protect`는 `multipart/form-data`로 전달된 값을 다음 순서로 검사합니다. 앞 단계에서 실패하면 뒤 단계와 AI 실행으로 넘어가지 않습니다.

1. `request_id` 앞뒤 공백 제거: 누락 또는 공백뿐이면 `400 INVALID_REQUEST_ID`.
2. `image`, `method`, `strength` 누락 검사: 누락 필드 이름을 포함한 `400 INVALID_REQUEST`.
3. 보호 방식 검사: `gaussian_blur` 외에는 `400 UNSUPPORTED_METHOD`.
4. 강도와 영역 검사: 숫자로 변환할 수 없는 강도, 0~1 범위 밖 값, NaN·무한대, 잘못된 영역은 `400 INVALID_REQUEST`.
5. 업로드 MIME 타입 검사: PNG·JPEG 외에는 파일을 닫고 `415 UNSUPPORTED_IMAGE_TYPE`.
6. 파일을 최대 제한 크기 + 1바이트까지 읽고 닫기: 빈 파일은 `400 EMPTY_IMAGE`, 15MiB 초과는 `413 IMAGE_TOO_LARGE`.
7. Pillow로 실제 형식·크기·내용 검사: 실제 형식도 PNG·JPEG여야 합니다. 2,000만 화소 초과는 `413 IMAGE_TOO_LARGE`; 식별·읽기·디코딩 실패와 Pillow의 압축 폭탄 오류는 `400 INVALID_IMAGE`.

영역은 이미지 전체를 0~1로 나타내는 정규화 좌표입니다. `parse_regions`의 검사 조건은 다음과 같습니다.

- 최상위 값은 JSON 배열이어야 합니다.
- 각 항목은 `x`, `y`, `width`, `height` 네 키만 가진 객체여야 합니다. 누락·추가 키는 허용하지 않습니다.
- 좌표는 유한한 숫자여야 하며 문자열·불리언·NaN·무한대는 허용하지 않습니다.
- `x`, `y`는 0 이상이고 `width`, `height`는 0보다 커야 합니다.
- `x + width`, `y + height`는 각각 1 이하여야 합니다.

### AI 호출과 결과 처리 순서

1. 이미지 검증 뒤 영역이 생략됐거나 빈 배열이면 AI를 호출하지 않고 `200 no_regions` 반환.
2. 영역이 있으면 AI 함수의 호출 가능 여부 검사; 미연결·호출 불가 시 `503 PROCESSOR_UNAVAILABLE`.
3. 요청 ID 등록; 이미 처리 중이면 `409 REQUEST_IN_PROGRESS` 반환.
4. 동기 AI 함수를 `PROCESSOR_EXECUTOR.submit`으로 제출하고 완료 콜백을 등록합니다. `asyncio.wrap_future`로 결과를 기다리며 `asyncio.shield`로 시간 초과·요청 취소가 작업에 전파되지 않게 하고 `asyncio.wait_for`로 최대 30초 대기합니다. 이 제한에는 스레드 풀 대기 시간도 포함됩니다.
5. 제한 시간 초과는 `504 PROCESSING_TIMEOUT`; AI 실행 예외는 `500 PROCESSING_FAILED`로 처리.
6. AI 결과가 디코딩 가능한 PNG이고 입력과 가로·세로 크기가 같은지 검사. 실패하면 `500 PROCESSING_FAILED` 반환.
7. 검증한 PNG를 Base64로 변환하고 `200 succeeded` 반환. 내부 예외 내용은 오류 응답에 노출하지 않습니다.
8. 실제 작업 완료 콜백에서 요청 ID 해제. 응답 대기 시간 초과·요청 취소·요청 이벤트 루프 종료 후에도 작업 완료 시 해제됩니다. 제출 자체가 실패한 경우에만 `finally`에서 즉시 해제합니다. 결과 검증은 작업 완료 후 수행하므로 완료된 AI 결과를 검사하는 동안에는 ID가 이미 해제될 수 있습니다.

AI 함수에 전달하는 값은 `(원본 이미지 바이트, 방식 문자열, 실수 강도, 검증된 영역 목록)`입니다. 영역 추출이나 블러 알고리즘은 이 파일에서 실행·구현하지 않습니다.

### 응답 모델과 OpenAPI

`RegionResponse`는 `x`, `y`, `width`, `height` 실수 좌표를 정의합니다. `ProtectionResponse`는 보호 API의 정상 응답 모델입니다.

| 정상 응답 필드 | 의미 |
|---|---|
| `request_id` | 앞뒤 공백을 제거한 요청 ID |
| `status` | `succeeded` 또는 `no_regions` |
| `result_kind` | Mock 연결 시 `mock`, 그 외 `real`; 이 값 자체는 AI 보호 성능의 검증 결과가 아님 |
| `image_base64` | 처리된 PNG의 Base64 문자열; 영역 없으면 null |
| `mime_type` | 항상 `image/png` |
| `applied_regions` | 검증된 전달 영역 목록; 영역 없으면 빈 목록 |
| `processing_ms` | 핸들러 시작부터 응답 생성까지의 경과 시간을 반올림한 밀리초 |
| `warnings` | 일반 정상 처리 시 빈 목록; 영역 없으면 `NO_REGIONS`; Mock 연결 시 `MOCK_NO_PROTECTION` 추가 |

`ErrorResponse`는 `request_id`, `code`, `message`, `retryable`을 정의합니다. 다음 표는 코드에서 직접 반환하는 공통 오류입니다.

| HTTP | 오류 코드 | 원인 | retryable |
|---|---|---|---|
| 400 | `INVALID_REQUEST_ID` | ID 누락 또는 공백 | false |
| 400 | `INVALID_REQUEST` | 필수 값 누락, 강도·영역 오류 | false |
| 400 | `UNSUPPORTED_METHOD` | 지원하지 않는 보호 방식 | false |
| 400 | `EMPTY_IMAGE` | 빈 이미지 파일 | false |
| 400 | `INVALID_IMAGE` | 실제 형식 오류 또는 이미지 읽기 실패 | false |
| 409 | `REQUEST_IN_PROGRESS` | 같은 ID의 요청이 이미 처리 중 | true |
| 413 | `IMAGE_TOO_LARGE` | 파일 크기 또는 화소 제한 초과 | false |
| 415 | `UNSUPPORTED_IMAGE_TYPE` | 지원하지 않는 MIME 타입 | false |
| 500 | `PROCESSING_FAILED` | AI 실행 예외 또는 결과 검증 실패 | true |
| 503 | `PROCESSOR_UNAVAILABLE` | AI 함수 미연결 또는 호출 불가 | true |
| 504 | `PROCESSING_TIMEOUT` | AI 응답 대기 제한 초과 | true |

`PROTECT_ERROR_RESPONSES`는 400·409·413·415·500·503·504의 설명과 `ErrorResponse` 모델을 OpenAPI에 등록합니다. 정상 200 응답에는 `ProtectionResponse` 모델을 사용합니다.

## test_main.py 전체 기능

### 테스트 준비 도구

- `client = TestClient(app)`: 별도 서버 실행 없이 FastAPI API를 호출합니다.
- `synthetic_image()`: 흰 배경에 빨강·파랑 패턴이 있는 40×40 PNG를 메모리에서 생성합니다. 개인 사진·실제 지문은 사용하지 않습니다.
- `protect_request()`: 합성 PNG, 기본 요청 ID, `gaussian_blur`, 강도 0.5, 정규화 영역으로 요청을 만듭니다. 이미지와 폼 값을 덮어써 오류 조건을 재현할 수 있습니다.
- 테스트용 AI 함수를 연결한 테스트는 사용 후 함수를 해제합니다. `monkeypatch`로 변경한 제한 시간은 테스트 종료 시 복원됩니다.
- 중복 요청은 `ThreadPoolExecutor`와 `Event`로 첫 처리를 대기시키고 후속 요청을 보내 재현합니다.
- `request_released` fixture는 실제 ID 해제를 이벤트로 관찰합니다. 시간 초과·취소 테스트는 작업 종료 전 차단과 종료 후 재시도를 구분해서 확인합니다.

### 전체 테스트 목록

테스트 함수 31개이며, 매개변수별 사례를 포함하면 총 44개입니다.

| 테스트 함수 | 확인 내용 | 사례 수 |
|---|---|---|
| `test_mock_returns_png_with_original_pixels` | PNG·JPEG 입력 각각의 크기와 디코딩된 픽셀 유지, PNG 출력, mock 표시와 경고 | 2 |
| `test_mock_without_regions_is_marked_as_mock` | 빈 영역 응답에서도 mock 표시와 두 경고 유지 | 1 |
| `test_mock_entrypoint_connects_processor` | 환경 변수의 지연 0·0.01초 설정 반영, ready 응답 및 Mock API 호출 | 2 |
| `test_delayed_mock_waits_and_returns_image` | 지정한 0.05초 이상 대기 후 정상 Mock 응답 | 1 |
| `test_mock_rejects_invalid_delay` | 음수·NaN·양수 및 음수 무한대 지연 설정 거부 | 4 |
| `test_timeout_keeps_id_until_worker_finishes` | 시간 초과 후 409 유지, 늦은 성공·실패 각각의 실제 종료 후 200 재시도 | 2 |
| `test_cancellation_keeps_id_until_worker_finishes` | 요청 코루틴 취소와 이벤트 루프 종료 후 409 유지, 실제 작업 종료 후 200 재시도 | 1 |
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
| `test_rejects_strength_outside_supported_range` | 강도 1.1 거부 | 1 |
| `test_rejects_region_outside_image_bounds` | x + width가 1을 초과하는 영역 거부 | 1 |
| `test_rejects_invalid_region_values` | 잘못된 JSON, 음수 x, 너비 0, NaN 높이; 오류 ID·코드·retryable 확인 | 4 |
| `test_rejects_image_over_15mb_before_processing` | 용량 초과 413 및 AI 함수 미호출 | 1 |
| `test_rejects_unsupported_method` | 알 수 없는 처리 방식 거부 | 1 |
| `test_rejects_unsupported_image_type` | GIF MIME 타입 거부 | 1 |
| `test_missing_required_input_uses_common_error_response` | image·method·strength 각각 누락, 필드 이름과 오류 전체 필드 | 3 |
| `test_missing_request_id_uses_common_error_response` | ID 누락 시 빈 ID와 오류 전체 필드 | 1 |
| `test_openapi_defines_protection_success_and_error_responses` | 정상 200과 일곱 오류 상태 등록, 응답 모델 참조 | 1 |

### 검증 범위

이 테스트는 합성 이미지와 테스트용 AI 함수로 백엔드 동작을 확인합니다. 실제 AI 보호 성능, 자동 영역 추출, Android 기기와 실제 서버 간 통신은 검증하지 않습니다.

코드에 구현됐지만 현재 전용 테스트가 없는 항목에는 공백 ID, 빈 이미지, 화소 제한 초과, 영역 생략, 영역 키·타입·y 경계 검사, 비PNG AI 결과, 호출 불가능한 AI 함수, 서로 다른 ID의 동시 처리 등이 있습니다. 구현된 기능과 테스트로 확인한 범위는 구분해야 합니다.

## 이미지 반환 Mock 사용 방법

`mock_processor.py`의 `MockProcessor(delay_seconds=0)`는 호출 가능한 개발용 처리기입니다. 기본 인스턴스 `mock_processor(image_bytes, method, strength, regions)`는 AI 함수와 같은 입력을 받습니다. 설정된 시간만큼 대기한 뒤 PNG·JPEG 이미지를 읽어 가로·세로 크기와 디코딩된 픽셀을 유지한 PNG 바이트를 반환합니다. 처리 방식·강도·영역은 적용하지 않으며 블러, 영역 추출, 성능 측정은 수행하지 않습니다. 파일은 저장하지 않고 메모리에서 변환합니다.

`mock_main.py`는 공통 API 앱에 이 함수를 연결하는 개발용 진입점입니다. `backend` 폴더에서 다음 명령으로 실행합니다.

```bash
uvicorn mock_main:app --reload
```

지연 시간은 개발 서버 시작 전 `BLURFING_MOCK_DELAY_SECONDS` 환경 변수로 설정합니다. 기본값은 0초이며 음수·NaN·무한대 또는 숫자가 아닌 값은 서버 시작 단계에서 거부합니다. PowerShell에서 35초 지연으로 30초 시간 제한을 재현하려면 다음과 같이 실행합니다.

```powershell
$env:BLURFING_MOCK_DELAY_SECONDS = "35"
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

실제 모듈 연동을 준비할 때는 개발 서버를 종료하고 기존 `uvicorn main:app --reload`로 실행합니다. Mock은 기본 서버에 자동 연결되지 않습니다. 기존 입력 검증·시간 제한·중복 요청 차단·결과 검증은 Mock 실행에도 동일하게 적용됩니다.

## 실제 HTTP 이미지 입출력 확인

`check_mock_http.py`는 `TestClient` 대신 실제로 실행 중인 서버에 HTTP 요청을 보냅니다. 기존 pytest 44개와 별도로 실행하는 확인 도구이며, 합성 이미지와 반환 PNG는 메모리에서만 처리하고 파일로 저장하지 않습니다.

`backend` 폴더의 첫 번째 터미널에서 개발 의존성을 설치하고 지연 없는 Mock 서버를 실행합니다.

```powershell
pip install -r requirements-dev.txt
$env:BLURFING_MOCK_DELAY_SECONDS = "0"
uvicorn mock_main:app --host 127.0.0.1 --port 8765
```

두 번째 터미널에서 같은 `backend` 폴더로 이동해 실행합니다.

```powershell
python check_mock_http.py --base-url http://127.0.0.1:8765
```

주소를 생략하면 `http://127.0.0.1:8000`을 사용합니다. 요청마다 최대 5초까지 기다리므로 지연 Mock의 시간 초과 검증에는 이 스크립트를 사용하지 않습니다. 완료 후 첫 번째 터미널에서 `Ctrl+C`로 서버를 종료합니다.

스크립트의 확인 항목은 다음 네 가지입니다.

1. `GET /`: HTTP 200과 서버 실행 메시지 확인.
2. `GET /ready`: HTTP 200과 ready 상태 확인.
3. 합성 PNG 업로드: HTTP 200, 요청 ID·영역·Mock 표시·경고·출력 MIME 타입을 확인하고 Base64를 디코딩해 PNG 형식·48×32 크기·색상 모드·전체 픽셀 비교.
4. 합성 JPEG 업로드: 같은 항목을 확인하고 JPEG를 디코딩한 픽셀과 반환 PNG의 픽셀 비교. JPEG 저장 전 픽셀이 아니라 실제 업로드 파일의 디코딩 결과를 기준으로 합니다.

성공 시 `PASS: 4 live HTTP checks completed; no image files saved`와 종료 코드 0을 반환합니다. 연결 실패, HTTP 오류 또는 검증 불일치 시 `FAIL`과 종료 코드 1을 반환합니다. 실제 AI 함수가 연결된 서버의 응답은 `result_kind: mock` 검사를 통과하지 못합니다.

2026-10-05 확인 결과: Windows 로컬 Uvicorn Mock 서버(`127.0.0.1:8765`, 지연 0초)에 실제 HTTP 요청을 보내 네 항목 모두 통과했습니다. PNG·JPEG 모두 반환 PNG의 크기와 디코딩된 픽셀이 일치했고 확인 후 서버를 종료했습니다. 이 결과는 로컬 Mock 통신 확인이며 Android 기기 통신이나 실제 AI 보호 성능 검증은 포함하지 않습니다.
