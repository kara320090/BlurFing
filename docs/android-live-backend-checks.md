# Android와 팀 백엔드 직접 연결 검증

Android 에뮬레이터의 실제 OkHttp 요청을 로컬 `backend/main.py`에 연결한다. MockWebServer로 대체하는 테스트와 다르며, AI 보호 성능 시험은 아니다. 사진은 작은 단색 합성 PNG만 사용한다.

```powershell
# 저장소 루트, 필요한 경우 전용 Python 가상환경을 먼저 만든다.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
$env:JAVA_HOME = 'C:\Program Files\BlueJ\jdk'
$env:ANDROID_HOME = 'C:\Users\soma\AppData\Local\Android\Sdk'
.\.venv\Scripts\python.exe android/integration/run_device_integration.py --serial emulator-5556
```

연결된 기기 식별자는 `adb devices`로 확인해 바꾼다. 스크립트는 빌드·설치 후 백엔드 2개를 127.0.0.1의 빈 포트에 실행하고 해당 기기에만 `adb reverse`를 설정한다. 기존 포트 전달은 덮어쓰지 않는다. 종료 시 자신이 만든 서버·포트 전달만 정리한다. 이 스크립트가 실행되는 동안 같은 기기에서 다른 UI 테스트·앱 설치를 병행하지 않는다.

| 검증 | 실제 경로와 기준 |
|---|---|
| AI 미연결 | 수정하지 않은 팀 백엔드의 503 → 앱 오류 안내 → 사진·수정 영역 보존 → 사용자가 직접 Mock으로 전환 |
| 영역 없음 | 실제 `no_regions` 응답 → 보호 성공으로 표시하지 않음 |
| 필수 입력 누락 | 팀원 변경 `e5057bd`의 HTTP 400, 요청 ID·INVALID_REQUEST·retryable 오류 계약 확인 |
| 정상 이미지 전송 | 같은 백엔드에 테스트 전용 단색 출력 함수를 주입 → 원본과 다른 픽셀·동일 해상도가 Android 비교 화면에 도착, 평가값 미측정 |

정상 이미지 전송의 주입 함수는 `android/integration/synthetic_backend.py`에 격리했다. 실제 알고리즘이 아니며 서버 보호 효과·지문 점수·성공률을 입증하지 않는다. 기본 `backend/main.py`와 팀원의 구현은 수정하지 않았다. 독립 배포된 팀 서버·실제 AI 모듈·실물 센서 통합은 각각 준비 후 추가 검증해야 한다.

로그: `android/build/live-backend/device-result.txt`, 같은 폴더의 서버 로그. 기본 테스트 실행에서는 서버 주소가 없으므로 `LiveBackendDeviceTest`가 건너뛰어질 수 있다. 직접 연결 검증의 완료 기준은 위 스크립트에서 **4개 모두 통과**하는 것이며 건너뜀을 통과로 세지 않는다.
