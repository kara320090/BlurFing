# Ubuntu 센서 비교 API — 내일 연결할 준비 소스

`scanner_api:app`은 기존 Android V1/PHOTO V2와 분리된 센서 전용 API다. 원본 지문 PNG → 기존 `protect_image` scanner 경로 → SourceAFIS 원본/처리본 직접 매칭 → 고정 JSON을 반환한다. PHOTO fallback, 신원 확률, 새로운 매칭 임계값, 모델 학습은 추가하지 않는다.

사용자가 실제 학교 서버 연결은 내일 진행하기로 했다. 기존 Docker·Nginx·Tunnel·학교 서버 설정은 이번 작업에서 변경하지 않았다.

## 실행 환경

- API Python 3.11 이상. 별도 가상환경에서 `python -m pip install -r sensor/server/requirements.txt`로 기존 backend의 PHOTO 파서 하한을 적용한다.
- AI Python은 기존 scanner 실험을 실행할 수 있는 검증된 환경을 지정한다. NumPy·Pillow·OpenCV·SciPy·scikit-image 등은 기존 [AI 안내](../../ai/README.md)와 고정 runtime을 따른다.
- scanner 구조 검사의 NBIS runtime과 SourceAFIS Java 3.18.1 runtime·해시 고정 jar가 필요하다. SDK·모델·바이너리를 이 폴더에 복사하지 않는다.

학교 서버에서 실제 경로를 지정한다.

```bash
export BLURFING_SCANNER_PYTHON=/absolute/path/to/validated-ai-venv/bin/python
export BLURFING_SCANNER_AI_ROOT=/home/user/BlurFing/ai
# 별도 runtime이 기본 경로 밖에 있는 경우에만 기존 변수 지정
export BLURFING_NBIS_LINUX_CONFIG=/absolute/path/to/verified-nbis-runtime.json
export BLURFING_SOURCEAFIS_CONFIG=/absolute/path/to/sourceafis_runtime.json
export BLURFING_SOURCEAFIS_HOME=/absolute/path/to/sourceafis

cd /home/user/BlurFing/sensor/server
/absolute/path/to/api-venv/bin/python -m uvicorn scanner_api:app \
  --host 127.0.0.1 --port 8002 --workers 1 --no-access-log --log-level warning
```

`/ready`의 200은 Python·AI 소스 경로 설정이 있다는 뜻이다. 추론·NBIS·Java·센서 동작의 성공 승인이 아니다. worker 1개를 사용한다. SourceAFIS만 미준비인 경우 유효한 처리 이미지는 반환하되 점수는 `unavailable`/null이다. 처리기 자체의 실패는 503이다.

## 내일 실제 연결 순서

1. 학교 Ubuntu에 이번 API/worker 소스와 기존 AI scanner runtime을 준비한다.
2. Ubuntu loopback에서 `/ready`와 동의된 입력 1건으로 실제 처리·매칭·취소·임시 자료 정리를 확인한다.
3. 기존 HTTPS 프록시/Tunnel에 **센서 서비스의 별도 경로**를 연결한다. `/scanner/`를 기본 주소로 정했다면 `/scanner/ready`와 `/scanner/v1/scanner/compare`를 센서 API의 `/ready`, `/v1/scanner/compare`로 매핑한다.
4. 기존 Nginx는 Docker 내부에 있으므로 호스트의 `127.0.0.1:8002`가 컨테이너의 localhost와 같다고 가정하지 않는다. 실제 네트워크와 upstream 연결을 확인한 뒤 적용하며 기존 Android V1/V2 경로를 유지한다.
5. Windows의 서버 주소에 확인한 HTTPS 기본 주소를 넣고 FFV 새 취득 → 서버 처리 → 두 이미지·점수 → 저장까지 확인한다.

기존 Quick Tunnel 주소에 V1 기본 주소를 넣는 것만으로 센서 API가 생성되지는 않는다. 실제 서버 설치·공개 경로·동의된 실제 영상 전송은 아직 실행하지 않았다.

## 계약

`POST /v1/scanner/compare`: multipart `image`(회색조 PNG), `request_id`(영문·숫자·밑줄·하이픈 1~80자), `dpi`(100~2000 정수)만 받는다. 파일 4MiB·400만 화소, 실제 envelope 4MiB+64KiB를 제한한다. 파일은 불투명 L/RGB/회색조 palette PNG만 허용하고 임의 resize·JPEG 손실 변환은 하지 않는다. 원본 해상도와 회색조 픽셀을 유지한 내부 L PNG로 worker에 전달한다.

반환은 `scanner-comparison-v1`, 현재 요청 ID, 업로드 byte SHA256·원본 회색조 pixel SHA256, 반환 PNG/base64/SHA256·크기, 처리 상태·변경 픽셀 수, SourceAFIS 점수·버전·DPI·특징점 수·UTC 시각이다. 부모 API와 Windows 앱이 반환의 원본 결합·해시·크기·변경 픽셀·점수 상태를 검사한다. worker의 추가 필드·템플릿·비공개 경로를 응답에 전달하지 않는다.

503 미설정/처리 실패, 429 다른 요청 처리 중, 504 처리 시간 초과, 413 파일/envelope 초과, 422 잘못된 입력, 502 잘못된 worker 결과다. 점수는 유사도 원시값이며 `%`가 아니다. 특징점이 없으면 null이고 보호 성공으로 세지 않는다. 처리 거절 시 원본이 반환되었다고 명시한다.

요청별 임시 폴더에 입력·처리·matcher 템플릿을 격리한다. AI child에 TMP/TEMP/TMPDIR를 같은 폴더로 설정하며 정상·실패·취소 뒤 정리한다. 실행 stdout/stderr·HTTP access log·원시 template를 응답하지 않는다. 클라이언트 연결 종료 또는 600초 timeout에는 하위 프로세스 트리를 종료한다. 사진·결과를 서버에 보관하는 기능은 추가하지 않았다.

```bash
cd /home/user/BlurFing/sensor/server
python -m pytest test_scanner_api.py -q
```

이 시험은 공개 합성 패턴·제어된 처리기/매칭 fixture만 사용한다. 실제 AI 모델·센서 성능과 Ubuntu 운영 검증을 대신하지 않는다.
