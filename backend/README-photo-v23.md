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

## 기존 Nginx·터널에 Linux V23 연결 (수동 전환 도구)

`serve_photo_gateway.py`는 인수 설정의 Python 환경·모델과 V23 앱을 재사용해
하나의 AI 프로세스를 loopback 및 명시한 Docker bridge 주소의 8001번에서 실행한다.
공인/LAN 전체 주소 `0.0.0.0`에는 열지 않는다. 먼저 Docker inspect로 Nginx가
참여한 `blurfing_tunnel` 네트워크의 Gateway를 확인한다. 이 주소는 재생성 시 바뀔 수 있다.
기존 수동 AI 서버만 정상 종료한 뒤 **API 가상환경 Python**으로 실행한다.

```bash
<api-venv>/bin/python <repo>/backend/serve_photo_gateway.py --repo <repo> --config <private-runtime.json> --gateway <Docker-Gateway>
```

다른 SSH 창에서 `connect_photo_nginx.py --sudo --gateway <Docker-Gateway> --backup <new-backup.conf>`를
실행하면 검사만 한다. `--apply`를 추가하면 실제 bind mount된 Nginx 설정을 백업하고
V2 upstream만 바꿔 `nginx -t` 및 reload를 수행한다. 컨테이너에서 V23 준비 응답이
확인되지 않으면 변경하지 않는다. 변경 후 V2 준비 상태·V1 info 유지·터널 ID/시작 시각을
검사하며 실패하면 원본 설정을 복원하고 reload한다. 백업은 덮어쓰지 않는다.
V1 Mock 경로·요청 제한·타임아웃 설정과 cloudflared는 변경하지 않는다.
Nginx reload 방식: https://nginx.org/en/docs/control.html

이것은 **기존 배포에 대한 수동 연결 단계**다. 터미널에서 직접 실행했다면 창을 계속 열어 둔다.
systemd 상시 실행 전환은 아래 별도 절차를 따른다. 기존 배포 도구의
`update`/`rollback`으로 Nginx 원본이 바뀌면 연결 상태를 재확인하고 필요 시 다시 적용한다.
Docker의 다른 컨테이너도 bridge 주소에 접근할 수 있으므로 신뢰하지 않는 컨테이너를
같은 호스트에 두지 않는다. 방화벽·호스트 관리자 보안은 별도 운영 범위다.

외부에서 `<기존 HTTPS 주소>/v2/ready`가 실제 experimental V23인지 별도 확인해야 한다.
일반 `/ready`는 V1 상태이며 실제 AI 검증을 대신하지 않는다.
사진 처리, CPU 처리 시간, Cloudflare 제한 이내 응답, Android 기기 시험은 별도다.
`production_approved: false`를 유지하며 접근 통제 없는 공개 실험 주소에 민감한
사진을 올리거나 일반 보호 성능을 보장하지 않는다.

합성 단위 검사(실제 Docker/AI 검증 아님):
`python -m unittest discover -s backend -p test_photo_gateway.py`.

## 학교 Linux 상시 실행 (systemd)

`systemd/blurfing-photo-v23.service.example`은 **그대로 설치할 수 없는 템플릿**이다.
서버별 계정·경로·IP는 Git에 고정하지 않는다. 기존 학교 서버에 설치된 서비스는
별도 파일이며 이 템플릿 정리·Git push만으로 변경되지 않는다.
다음 명령은 저장소 루트에서 실행하며, 생성한 복사본은 Git에서 제외되는 `.deploy/` 안에 둔다.

```bash
mkdir -p backend/.deploy
cp -n backend/systemd/blurfing-photo-v23.service.example backend/.deploy/blurfing-photo-v23.service
```

복사본을 편집해 아래 토큰을 모두 실제 값으로 교체한다. 기존 복사본은 덮어쓰지 않는다.
경로는 공백·`%`·`$` 등 특수문자가 없는 절대 경로를 사용한다.

| 토큰 | 설정할 값 |
|---|---|
| `@SERVICE_USER@` | 모델·환경을 읽을 권한이 있는 비-root Linux 계정 |
| `@SERVICE_GROUP@` | 해당 계정의 그룹 |
| `@WORKING_DIRECTORY@` | AI 실행 작업 디렉터리 |
| `@API_PYTHON@` | API 가상환경의 `bin/python` 경로. 시스템 Python으로 치환하지 않음 |
| `@REPO_ROOT@` | `backend/`, `ai/`, `demo/`를 포함한 저장소 경로 |
| `@RUNTIME_CONFIG@` | 사전 검사에 통과한 비공개 실행 설정 JSON |
| `@DOCKER_GATEWAY@` | 실행 중인 Nginx의 `blurfing_tunnel` Gateway. `--gateway`와 동일한 값 |

AI는 지정한 비-root 계정으로 실행하며 기존 가상환경·실행 설정·비공개 모델을 재사용한다.
`grep -n '@[A-Z_]*@' backend/.deploy/blurfing-photo-v23.service`의 주석 외 결과가 없어야 한다.
`sudo systemd-analyze verify backend/.deploy/blurfing-photo-v23.service`의 종료 코드가 0인지 확인한다.
`systemctl cat blurfing-photo-v23.service`로 기존 서비스가 있는지 확인한다.
기존 서비스가 있으면 이 신규 설치 절차를 반복하지 말고 실제 설정을 먼저 비교·백업한다.
새 서비스 설치 시에만 다음 절차를 진행한다.

```bash
sudo install -m 0644 backend/.deploy/blurfing-photo-v23.service /etc/systemd/system/blurfing-photo-v23.service
sudo systemctl daemon-reload
```

수동 AI 프로세스만 정상 종료해 8001 포트를 비운 다음 등록한다. Nginx·터널은 종료하지 않는다.

```bash
sudo systemctl enable --now blurfing-photo-v23.service
```

- 로그인·SSH·TeamViewer 세션과 독립된 system service이며 부팅 시 시작하도록 설정한다.
- Docker/network 시작 뒤 실행한다. bridge가 아직 없거나 시작에 실패하면 15초 후 재시도한다.
- 시작 후 loopback `/ready`가 HTTP 200이 될 때까지 제한된 시간 동안 확인한다.
  `active`만 보지 말고 외부 `/v2/ready`의 V23 계약도 확인한다.
- 프로세스 비정상 종료 시 재시작한다. 실행 중 응답 불능을 주기적으로 감지하는
  watchdog은 없으며, 초기화 이후 AI worker만 실패하고 API가 살아 있는 경우 자동 복구를 보장하지 않는다.
- 정지 시 Uvicorn의 정상 종료를 기다리며, 제한 시간 뒤 남은 자식 프로세스도 정리한다.
- `PrivateTmp`로 작업 임시 파일을 격리하며 업로드·개인 사진을 로그에 남기지 않는다.
  현재 로그는 `sudo journalctl -u blurfing-photo-v23.service -n 50 --no-pager`로 확인한다.

상태: `systemctl status blurfing-photo-v23.service --no-pager -l`.
부팅 등록: `systemctl is-enabled blurfing-photo-v23.service`.
수동 정지/재시작은 `sudo systemctl stop/restart blurfing-photo-v23.service`로 수행한다.
unit·로컬 테스트 추가만으로 학교 서버 설치·재부팅 시험 완료를 의미하지 않는다.
운영 설치 후 기존 수동 AI를 중복 실행하지 않는다.

기존 Nginx·터널 컨테이너는 이 unit이 변경하거나 재시작하지 않는다.
단, Linux 재부팅으로 Quick Tunnel 컨테이너가 다시 시작하면 임시 HTTPS 주소가
달라질 수 있다. AI 자동 시작 설정이 도메인 고정이나 사진 처리·보호 성능 검증을 대신하지 않는다.
systemd 동작 근거: https://www.freedesktop.org/software/systemd/man/systemd.service.html

## 2026-10-21 검증 기록

- Windows Python 3.12.14의 별도 가상환경에 `requirements-deploy.txt`와
  `requirements-dev.txt`를 설치하고 `pip check` 통과를 확인했다.
- `python -B -m pytest backend -q -ra --disable-warnings`: **328개 통과, 5개 건너뜀**.
  건너뛴 항목은 실제 심볼릭 링크 생성 권한이 필요한 1개와 선택 의존성 OpenCV가 필요한 4개다.
  Python 경로 보존의 절대·상대 경로 회귀 검사 2개 및 연결/템플릿 검사 23개는 통과했다.
- 학교 Linux에서 구체 값을 채운 unit의 검증 종료 코드 0, 서비스 `enabled` 및
  `active (running)`, 시작 시 준비 검사 성공을 운영 로그로 확인했다.
  외부 HTTPS `/v2/ready`에서도 `synthetic_v23`, `production_approved: false`, HTTP 200을 확인했다.
- 실제 사진 처리·처리 시간·Android 전체 흐름·GPU 실행·실제 재부팅 후 복구 시험은
  이번 검증에 포함하지 않았다. 이 Git 변경은 실행 중인 학교 서비스 설정을 바꾸지 않는다.
