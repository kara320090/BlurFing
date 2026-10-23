# Windows 센서 버튼과 같은 학교 서버 연결 — 2026-10-21

Android 앱이 사용하는 학교 Ubuntu·HTTPS 주소를 Windows 프로그램도 사용할 수 있다. Android APK/AAB를 다시 올릴 필요는 없다. 센서 서비스(8002)와 HTTPS 경로를 추가한다. 사진 V23 API로 센서 지문을 보내지 않는다.

| 용도 | 같은 HTTPS 호스트의 경로 |
|---|---|
| 기존 Android 사진 | `/v2/photo/protect` |
| 센서 준비 확인 | `/scanner/ready` |
| 센서 처리·SourceAFIS 매칭 | `/scanner/v1/scanner/compare` |

Windows 기본 주소는 `https://현재-Android-호스트/scanner/`다. SSH 포트 전달 시 `http://127.0.0.1:8002/`도 지원한다. 2026-10-21 서버 담당자의 설치 후 센서 준비 경로는 HTTP 200(`configured=true`, `inference_checked=false`), 지문 없는 처리 요청은 HTTP 422를 확인했다. 준비 응답만으로 실제 센서 추론·매칭 성공을 뜻하지 않는다.

## Windows 사용 — 0.3.1

0.3.1은 큰 숫자에 `100 × s / (s + 40)` 환산 유사도 지수를 표시하고 원시 점수를 함께 보존한다. 0.9 원시점은 2.2/100, 298 원시점은 88.2/100이다. `40`은 표시 곡선의 기준이며 인증 판정 기준을 적용한 것이 아니다. 확률·인식률이 아니다. 서버 재배포나 Android 업데이트가 필요 없다. [표시·저장 기준](SCANNER_COMPARISON.md#화면과-저장)을 따른다.

0.3.0은 검증된 0.2.4 취득·서버 연결 흐름을 유지하면서 화면을 정리한 버전이다. 원본·처리본·점수를 카드로 나란히 표시하며 DPI·수동 파일 입력·취득기 위치 설정은 **추가 도구 보기**에 있다. [화면·검증 기록](../docs/worklogs/2026-10-21-이봉헌-shared-ui-design.md)을 참조한다. 아래 실물 3회 성공 기록은 0.2.4 기준이며 새 디자인의 실물 재검증으로 계산하지 않는다.

1. `BlurFing.ScannerComparison.exe` 또는 바탕화면 **BlurFing 센서 (최신)**을 연다. 다른 센서 앱이 장치를 사용 중이면 닫는다.
2. 비교 서버 주소를 확인하고 **선택한 서버로 연구용 지문 영상 전송**만 체크한다. `기존 FFV 창의 새 취득 자동 처리`는 비워 둔다. 앱 재실행·주소 변경 후 다시 체크한다.
3. **지문 취득 후 자동 비교**를 누르고 맨손 손가락을 센서 중앙에 넓게 올린다. 새 원본 → 서버 처리 → 원본·처리본·점수가 자동 표시된다.
4. 취득기 위치가 없으면 설치된 공식 SDK의 `Bin/Win64_x64/BlurFingBioMiniRaw20261021R1.exe`를 선택한다. 원본 직접 취득에서는 FFV 등록이나 모듈 선택을 하지 않는다. 센서 1개를 연결한다.
5. **3열 비교 자료 저장**으로 원본·처리본·점수 JSON·`hstack.png`를 개인 폴더에 저장한다. 원본 영상은 공개 Git에 넣지 않는다.

전달본 `scanner-connection.json`은 서버 주소와 취득기 위치만 제공한다. 정상적인 개인 설정이 우선하며 잘못된 취득기 경로는 전달 설정의 정상 원본 취득기로 복구한다. 다른 PC에서는 그 PC의 전체 공식 SDK 위치를 선택한다. SDK·드라이버·종속 DLL은 전달 ZIP에 포함하지 않는다.

### 취득 실패 시 확인

- 비교 프로그램 자체를 취득기로 선택하면 안 된다. 0.2.4는 직접 취득 코드의 메타데이터와 전체 SDK·BioMini 모듈을 검사한다. EXE만 복사한 파일이나 기존 FFV 등록 취득기는 거절한다.
- 장치 관리자에는 센서가 `Authentication Scanner (0x0408)`로 표시될 수 있다. 실제 PC에서는 Xperix 3.0.3.0 드라이버와 정상 상태를 확인했다.
- 이전 버전에는 취득기 경로 오선택, 동기 pipe의 읽기/쓰기 교착, FFV `GetBitmap()`의 **150×200 컬러 결과를 원본 회색조로 쓰려던 문제**가 있었다. 최신 버전은 설치된 `UFScanner.dll`의 `UFS_StartCapturing` 콜백에서 **300×400·500ppi 회색조 원본**을 직접 받는다. 밝기·해상도를 바꾸거나 컬러 등록 결과를 임의 회색조 원본으로 만들지 않는다.
- 최근 시도는 `%LOCALAPPDATA%/BlurFing/FFVOneShot/last-attempt.log`에서 확인한다. 단계·SDK 코드·프레임 수·오류 종류만 기록한다. 지문 영상·특징점·비밀번호·오류 전문은 기록하지 않는다.

점수는 **SourceAFIS 원시 유사도**이며 백분율·신원 확률이 아니다. 특징점 부족은 측정 불가, 매칭 환경 실패는 미측정이다. 원본과 처리본의 직접 비교이며 독립 참조에 대한 보호 효과 입증과 구분한다. 원본 취득기는 콜백의 500ppi를 확인한다. 서버 요청 DPI도 기본 500을 사용한다. 파일 입력의 DPI는 설정값이다.

## 취득·취소·자료

버튼마다 별도 helper와 같은 사용자만 접근 가능한 임의 named pipe를 만든다. 취득부터 서버 비교까지 구형 미리보기 수신을 무시한다. 새 취득·취소는 이전 처리본·점수를 무효화한다.

직접 취득에서는 FFV 등록 DB를 만들거나 기존 DB를 열지 않는다. 프레임은 메모리에서 취급하며 사용자 내보내기 전에는 영상 파일로 자동 저장하지 않는다. 센서의 `FingerOn` 프레임이 연속 3개이고 균일한 빈 프레임이 아닐 때 최신 프레임을 선택한다. 이 조건은 등록 성공·생체 판정·지문 품질 점수의 근거가 아니다. 생체 감지 설정을 변경하지 않는다.

장치 프레임 대기는 20초, helper 전체 대기는 90초다. 취소 시 pipe를 닫고 이번 취득기가 캡처를 중단하게 한다. `UFS_AbortCapturing`·이전 timeout 복원·`UFS_Uninit` 정리를 확인한 뒤 영상을 전달한다. 정리 실패는 전송하지 않는다. 5초 안에 종료되지 않는 이번 helper만 종료하며 다른 앱·전역 서비스는 종료하지 않는다.

2026-10-21 실제 원본 → 학교 서버 처리 → SourceAFIS 점수 표시를 확인했다. 제공된 화면의 서버 처리 시간은 **1,891ms**, 원시 점수는 **81.96**이었다. 사용자가 0.2.4의 원클릭 자동 비교 **연속 3회 성공**을 확인했다. 전체 처리 시간 반복 계측이나 독립 보호 성능 검증으로 확대하지 않는다. [원인·실제 기록](../docs/worklogs/2026-10-21-이봉헌-scanner-native-capture.md)을 따른다.

## 학교 서버 적용

서버 담당자가 Android를 실행한 **같은 호스트·저장소**에서 실행한다. 대문자 값은 실제 환경으로 채운다. 원본·가중치·비밀 설정은 공개 Git 밖에 둔다.

```bash
cd /actual/path/BlurFing
SCANNER_API_PYTHON=/actual/path/scanner-api-venv/bin/python
SCANNER_RUNTIME=/actual/path/runtime.private.json
SCANNER_GATEWAY=$(sudo docker inspect blurfing-nginx-1 --format '{{(index .NetworkSettings.Networks "blurfing_tunnel").Gateway}}')

# demo runtime의 scanner 항목에 실제 Linux 경로 지정:
# api_python, ai_python, nbis_config, sourceafis_config, sourceafis_home
"$SCANNER_API_PYTHON" -B demo/runtime.py preflight --config "$SCANNER_RUNTIME" --service scanner --probe

# 이 터미널에서 실행 상태를 유지한다. 사진 서비스·터널은 종료하지 않는다.
"$SCANNER_API_PYTHON" -B sensor/server/serve_gateway.py --config "$SCANNER_RUNTIME" --gateway "$SCANNER_GATEWAY"
```

API 환경은 `sensor/server/requirements.txt`를 따른다. AI 환경은 기존 scanner 처리기·NumPy/Pillow/OpenCV/SciPy/scikit-image·NBIS·SourceAFIS Java 고정 runtime이 필요하다. 사진 서버 Python이 이 의존성을 갖추면 같은 환경을 지정할 수 있다. 사진 가중치만으로 센서 매칭 환경이 준비되지는 않는다. preflight 실패 항목을 해결한 뒤 진행한다.

다른 터미널에서 아래를 실행한다. `--apply` 전까지 검사만 한다.

```bash
cd /actual/path/BlurFing
SCANNER_GATEWAY=$(sudo docker inspect blurfing-nginx-1 --format '{{(index .NetworkSettings.Networks "blurfing_tunnel").Gateway}}')
python3 -B sensor/server/connect_nginx.py --sudo --gateway "$SCANNER_GATEWAY" --backup /actual/private/path/nginx-before-scanner.conf
python3 -B sensor/server/connect_nginx.py --sudo --gateway "$SCANNER_GATEWAY" --backup /actual/private/path/nginx-before-scanner.conf --apply
curl --fail --silent --show-error https://CURRENT-ANDROID-HOST/scanner/ready
```

적용 도구는 실제 Docker gateway·Nginx bind mount를 확인하고 백업 후 경로 두 개만 추가한다. `nginx -t`·reload·센서 계약 확인 실패 시 원복한다. 기존 V1 info·V23 준비 계약과 터널 유지도 검사한다. Docker·터널 재생성이나 공용 8002 포트 개방은 하지 않는다. 이미 다른 센서 경로가 있으면 덮어쓰지 않는다.

상시 실행은 `sensor/server/blurfing-scanner.service.example`의 모든 `@TOKEN@`을 채운 사본을 검토하고 `systemd-analyze verify <작성한 서비스 파일>`로 검사한 뒤 적용한다. 사진 서비스는 수정하지 않는다.

## 실제 완료 조건

실제 **BioMini 새 취득 → 학교 서버 scanner 처리·유효한 SourceAFIS 점수 → 3열 저장**을 연속 3회 확인하고 시간·거절/측정 불가·버전을 기록한다. 합성 통신 시험과 준비 API의 200만으로 장치 취득·AI 처리·매칭 성공을 주장하지 않는다. Linux 네이티브 모듈·외부 HTTPS/터널 제한·동시 실행 성능은 실제 장비에서 확인해야 한다.
