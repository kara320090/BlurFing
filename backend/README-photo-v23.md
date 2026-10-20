# 자동 V23 개발 서버 실행

Android에서 **자동 지문 보호 · V23 실험**을 열고 서버를 설정한다.
`자동 지문 합성 (V23 · 검증 중)` 모드는 사진을 선택하면 자동으로 전송한다.
확인하지 못한 영역은 미적용으로 표시한다. 원본을 덮어쓰지 않는다.

2026-10-20 선택 정책 변경: 기본 `surface_v26`은 모델·손 자세·경계가 확인된 손끝을 지문선이 흐려도 합성한다. 원본 지문선 관측은 별도 기록하며 `TRANSFORMED_PRECAUTIONARY_SURFACE` 사유와 `PRECAUTIONARY_SURFACE_WITHOUT_RIDGE_CONFIRMATION` 경고로 구분한다. 서버와 APK를 함께 업데이트하고 서버를 재시작한다. `-ReuseRunning`은 이미 로드된 구버전 서버를 업그레이드하지 않는다. [정책·실행 범위](../ai/docs/PHOTO_SURFACE_POLICY_V26_20261020.md)를 따른다.

PowerShell:

```powershell
& "<repository>\backend\Start-Photo-V23.ps1" `
  -ServerPython "<backend environment>\Scripts\python.exe" `
  -AiPython "<AI environment>\Scripts\python.exe" `
  -ModelPath "<private V6 training directory>" `
  -RegistryPath "<private consumed_registry.private.json>"
```

AI 프로세스의 기존 `BLURFING_COLFISPOOF_PYTHON/SOURCE/MODEL`과
`BLURFING_HAND_PYTHON/MODEL` 환경변수 및 검증된 모델 파일이 필요하다.
이 실행기는 패키지나 시스템 설정을 설치·변경하지 않는다.
학습/개발에 사용한 기존 입력을 재실행하려면 `-DevelopmentReplay`를 명시한다.
그 실행을 독립 평가로 기록하지 않는다.

이미 실행 중인 같은 저장소의 V23 서버를 재사용하려면 `-ReuseRunning`을 지정한다.
실제 포트 소유 프로세스와 `/ready` 응답을 함께 확인하고, 다른 프로그램이나
준비되지 않은 서버를 자동 종료하지 않는다. 재사용 시 기존 서버의 설정을 유지하며
새로 전달한 모델/환경 설정을 적용하지 않는다. 설정을 바꾸려면 해당 서버를 정상 종료한 후
다시 실행하거나 다른 `-Port`를 사용한다.

실행기는 서버 콘솔이며 별도의 사진 선택 창을 열지 않는다.
사진은 Android 앱에서 선택한다. PC의 `http://127.0.0.1:8001/ready`는
JSON 상태 확인 주소다. 새 서버를 시작한 콘솔은 앱을 사용하는 동안 열어 둔다.
이미 실행 중인 서버를 재사용했다는 안내 창은 닫아도 기존 서버를 중단하지 않는다.

에뮬레이터의 서버 주소는 `http://10.0.2.2:8001`.
USB 디버깅이 허용된 실물 기기는 `adb reverse tcp:8001 tcp:8001` 후
debug 앱에서 `http://127.0.0.1:8001`을 사용한다.
서버는 PC loopback에만 열린다. 외부 배포는 인증·HTTPS·보관 정책이 구성된
별도 서버가 필요하며 이 실행기만으로 외부 배포 완료를 의미하지 않는다.

기존 V2 입력/출력·취소·timeout·임시 디렉터리 정리 계약을 재사용한다.
실행 중 최대 1건과 대기 1건 제한이며 timeout은 600초다.
`/ready`는 구성 상태를 보여 주며 보호 성능을 보증하지 않는다.
스캐너/모호한 입력은 이 엔진에서 미적용으로 반환한다.

실행 및 성능 한계: [AI 통합 검증 기록](../ai/docs/PHOTO_AUTOMATIC_V23_20261020.md).

2026-10-20 실행 비용 최적화: 동일 개발 사진의 AI 평균 90.47초→78.85초,
고정 시드 반환 RGB·마스크 동일. 경계 계산은 요청별 최대 4개 프로세스를 사용한다.
아직 실시간 처리는 아니다. [측정 범위와 회귀 검증](../ai/docs/PHOTO_V23_PERFORMANCE_20261020.md).

## 시연 인수 연결

학교 Ubuntu의 기존 V23/센서 API 실행, 비공개 자산 검사와 USB·SSH 연결은 [시연 인수 안내](../demo/README.md)를 따릅니다. 위 Windows 실행기를 학교 서버 배포 완료로 간주하지 않습니다.
