# 자동 V23 개발 서버 실행

Android에서 **자동 지문 보호 · V23 실험**을 열고 서버를 설정한다.
`자동 지문 합성 (V23 · 검증 중)` 모드는 사진을 선택하면 자동으로 전송한다.
확인하지 못한 영역은 미적용으로 표시한다. 원본을 덮어쓰지 않는다.

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
