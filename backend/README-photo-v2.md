# 실험용 PHOTO V2 서버

`experimental_photo_main:app`은 실제 AI child CLI를 호출하는 별도 선택 진입점이다. 기존 `main:app`, `/v1/protect`, `gaussian_blur` 동작은 변경하지 않는다. V2는 자동 PHOTO만 지원하며 수동 사각형·scanner·gaussian으로 대체 실행하지 않는다. 실험용 출력은 보호 성능 승인이나 모든 지문을 검출했다는 뜻이 아니다.

## 실행

서버 Python에는 `requirements-photo-v2.txt`를 설치한다. AI Python과 COLFISPOOF/MediaPipe 등 엔진별 런타임은 [AI 안내](../ai/README.md)에 따라 별도로 구성한다. 패키지 설치나 원격 배포는 서버 시작 과정에서 자동 실행하지 않는다.

PowerShell에서 실제 비공개 경로를 지정한다. 환경변수는 현재 프로세스와 child에만 적용한다.

```powershell
$env:BLURFING_PHOTO_PYTHON = '<AI Python 절대 경로>'
$env:BLURFING_PHOTO_BRIDGE = '<저장소>\ai\scripts\export_photo_permissions_v1.py'
$env:BLURFING_PHOTO_CONSUMED_REGISTRY = '<비공개 consumed registry JSON 절대 경로>'
$env:BLURFING_PHOTO_MODEL = '<V6 model 디렉터리 절대 경로>'
$env:BLURFING_PHOTO_ENGINES = 'native_v12'
$env:BLURFING_PHOTO_TIMEOUT_SECONDS = '600'
$env:BLURFING_PHOTO_DEVELOPMENT_REPLAY = 'false'
Set-Location '<저장소>\backend'
& '<서버 Python 절대 경로>' -m uvicorn experimental_photo_main:app --host 127.0.0.1 --port 8001 --workers 1 --timeout-graceful-shutdown 10
```

`BLURFING_PHOTO_ENGINES`는 `native_v12,distal_v13,pose_v14` 중 명시적으로 허용한 엔진만 쉼표로 나열한다. 기본은 `native_v12`이며 `final_config.private.json`과 `final_context_whole_pad.pt`가 들어 있는 모델 디렉터리 경로가 필수다. geometry 엔진은 V6 pad model을 사용하지 않지만 COLFISPOOF 등 별도 모델/런타임이 필요하다. geometry 경계는 검토가 필요하고, distal 방식은 기존 GT에서 경계 정확도가 후퇴한 실험이다. 이를 native 기본값이나 요청별 자동 fallback으로 사용하지 않는다.

registry가 없거나 경로/옵션이 잘못되면 `/ready`와 처리 요청은 503이다. `/ready`는 명시 경로의 존재와 설정만 확인하며 실제 모델 추론이나 독립 성능 검증을 실행하지 않는다. `BLURFING_PHOTO_TEMP_ROOT`를 지정한다면 이미 존재하는 비공개 디렉터리여야 한다. 기본은 OS 임시 폴더다.

기존 평가에 소비된 원본은 기본적으로 거절된다. `BLURFING_PHOTO_DEVELOPMENT_REPLAY=true`는 허가된 개발 재현에만 사용하고 새 독립 평가로 보고하지 않는다. 모델·registry·실제 사진·출력 JSON을 공개 Git에 넣지 않는다.

## 요청 및 응답

`POST /v2/photo/protect`의 multipart 필드는 정확히 다음 5개다. 누락·추가·중복·수동 영역은 오류다. `photo_engine` 요청 필드는 없고 `method`가 엔진을 1:1로 결정한다.

| 필드 | 값 |
|---|---|
| `request_id` | 1~200자, 첫 글자는 영문/숫자, 이후 영문/숫자/`_ . : -` |
| `image` | `image/png`, 클라이언트가 sRGB로 정규화한 opaque RGB 8-bit PNG, 방향 메타데이터 없음 또는 최소 EXIF 1만 포함 |
| `method` | `photo_native_v12_experimental`, `photo_distal_v13_geometry_experimental`, `photo_pose_v14_geometry_experimental` |
| `scope` | `automatic_photo` |
| `strength` | 유한 숫자 `0.5`만 지원 |

입력 PNG는 15MiB·2,000만 화소 이하로 제한한다. IHDR은 bitdepth 8·colorType 2·interlace 0이어야 한다. RGBA/L/팔레트 PNG·tRNS 투명성·JPEG·EXIF 2~8·APNG·16bit RGB·interlaced PNG는 거절하고 서버에서 임의 회전·축소·JPEG 변환하지 않는다. 전체 multipart envelope는 실제 ASGI 수신 byte 기준 15MiB+64KiB 이하, 파일 1개·텍스트 필드 4개·각 텍스트 1KiB 이하로 제한한다. `Content-Length`가 없거나 거짓이어도 실제 수신량을 센다.

정식 V2 PNG는 `IHDR` → 선택적인 최소 `eXIf` → 연속된 `IDAT` → `IEND`만 허용한다. `eXIf`는 orientation=1 한 항목만 가진 최소 TIFF이며 카메라 정보·추가 IFD·붙임 데이터는 허용하지 않는다. 입력·반환 RGB·A/R mask 모두 같은 allowlist를 적용한다. `iCCP`, `sRGB`, `gAMA`, `cHRM` 등 색상 chunk와 `tEXt`, `pHYs` 등 다른 ancillary chunk는 거절한다. 서버는 이를 조용히 삭제하거나 색공간을 변환하지 않는다.

클라이언트는 원본의 ICC/광색역·EXIF 방향을 적용해 sRGB 픽셀로 정규화한 뒤 metadata 없는 무손실 RGB PNG를 인코딩해야 한다. ICC profile만 삭제해 원본의 Display P3 숫자값을 sRGB라고 취급하면 화면 색상과 지문 밖 픽셀이 달라질 수 있다. 서버의 source RGB hash와 C⊆A 검사는 이 canonical 업로드 픽셀을 기준으로 한다. 이전 ICC 포함 raw RGB 요청 기록은 계약 강화 전 진단이며 정식 Android canonical 입력의 동등성 검증으로 재사용하지 않는다.

계약은 [고정 V2 schema](../contracts/photo-experimental-v2.schema.json)와 [합성 응답 예제](../contracts/photo-experimental-v2.synthetic.json)를 따른다. 예제의 changed pixel과 component 수는 통신 테스트용이며 AI 성능 수치가 아니다.

응답 상태는 `success`, `partial_success`, `rejected`다. HTTP 200의 `rejected`도 정상적인 원본 반환 결과다. `candidate_components`는 해부학적 손가락 개수가 아니다. 반환 RGB의 변경 집합 C는 실제 통과한 permission A 안에만 존재하며, 거절 permission R과 A는 겹치지 않는다. 거절된 영역과 A 밖 RGB는 원본과 동일해야 한다. 미검출 영역의 보호를 보장하지 않는다.

`accepted_permission_mask`와 `rejected_permission_mask`는 반환 RGB와 같은 크기의 L/8-bit/0·255 PNG다. Boolean SHA는 row-major 0/1 byte 배열의 SHA256이다. `region_display_bounds`는 정규화된 표시용 bounds이며 내부 전체를 채운 보호 permission으로 해석하지 않는다. 실제 permission은 mask를 사용한다. 반환 RGB와 mask PNG 각각에도 15MiB 제한을 적용하며 JPEG나 downscale fallback은 없다.

서버는 매 요청마다 새 비공개 폴더에 `input.png`를 쓰고 다음 child를 1개만 실행한다.

```text
<AI Python> <bridge> --input <input.png> --output <존재하지 않는 fresh output 폴더> --photo-engine <선택 엔진> --consumed-registry <registry> --request-id <동일 ID> [--photo-model <model>] [--development-replay]
```

child의 `result.transport.json`은 64MiB 이하의 고정 응답 전체다. 서버가 같은 request ID·원본 bytes/RGB SHA·반환 RGB SHA·mask SHA·fullshape binary masks·C⊆A·A∩R=∅·counts/status·실험 flags·표시 bounds를 다시 검증한 뒤 `processing_ms`만 전체 HTTP 경과 시간으로 바꾼다. 원본 JSON의 비공개 경로·알고리즘 원시 로그·matcher 출력은 반환하지 않는다.

## 실행·실패 경계

반드시 Uvicorn worker 1개로 실행한다. 실행 1개와 대기 1개만 허용하며 초과는 HTTP 429 `PROCESSOR_BUSY`, 처리/대기 중 같은 request ID는 409다. 기본 600초는 업로드 파싱·작업 대기·child 실행을 포함하는 요청 deadline이다. 설정은 유한한 `(0, 3600]`초만 허용한다. 일반적인 30초 HTTP timeout으로는 실제 AI 처리가 끝나기 전에 연결이 끊길 수 있으므로 클라이언트는 서버 timeout 이상의 명시적 timeout을 사용해야 한다.

시간 초과는 504, child 실패·잘못된/이전 응답은 500, 미설정 엔진은 503이다. 모든 HTTP 오류는 `request_id`, `code`, `message`, `retryable`만 반환한다. client 연결 종료·취소·timeout은 실행 중 child process tree를 종료하고 임시 폴더를 정리한다. ID와 실행 slot은 종료/정리가 끝난 후 해제한다. process tree 종료를 확인하지 못하면 서버를 unavailable 상태로 두고 private 임시 폴더를 보존한다. 원인 확인 후 서버 재시작이 필요하다. 성공 응답·이전 파일 재사용으로 덮지 않는다.

서버는 응답 후 사진/결과를 보관하지 않는다. 에러 메시지에 경로나 processor stdout/stderr를 포함하지 않는다. 외부 공개·인증·원격 서비스 운영 설정은 이 로컬 실험 진입점의 검증 범위에 포함되지 않는다.

## 검증

```powershell
Set-Location '<저장소>\backend'
& '<서버 Python 절대 경로>' -m pytest test_main.py test_native_photo_result_contract_v1.py test_experimental_photo_v2.py -q
```

이 명령은 기존 V1 회귀, native component/최종 RGB 증거, V2 typed 계약, 실제 subprocess, 로컬 HTTP transport, 과부하·중복·timeout·연결 종료·chunked 상한·spool 정리를 합성 입력으로 검사한다.

2026-10-16에는 별도로 실제 canonical sRGB 개발 사진의 native V12 HTTP 부분 처리와 Android Repository→loopback HTTP→pose V14→MediaStore 저장/readback 1회를 확인했다. 거절 영역·A 밖 RGB 보존, Android 저장 PNG byte 일치, source 보존과 임시 폴더 정리를 검증했다. 같은 사진의 통합 동작 관측이며 독립 보호 성능·Linux 동등성·외부 서버 배포·실물 휴대폰 전반의 승인은 아니다. [실제 검증 범위](../ai/docs/PHOTO_DESKTOP_VALIDATION_20261016.md)를 따른다.
