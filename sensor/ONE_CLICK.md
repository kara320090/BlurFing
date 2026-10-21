# Windows 센서 버튼과 같은 학교 서버 연결 — 2026-10-21

Android 앱이 사용하는 학교 Ubuntu·HTTPS 주소를 Windows 프로그램도 사용할 수 있다. Android APK/AAB를 다시 올릴 필요는 없다. 센서 서비스(8002)와 HTTPS 경로를 추가한다. 사진 V23 API로 센서 지문을 보내지 않는다.

| 용도 | 같은 HTTPS 호스트의 경로 |
|---|---|
| 기존 Android 사진 | `/v2/photo/protect` |
| 센서 준비 확인 | `/scanner/ready` |
| 센서 처리·SourceAFIS 매칭 | `/scanner/v1/scanner/compare` |

Windows 기본 주소는 `https://현재-Android-호스트/scanner/`다. SSH 포트 전달 시 `http://127.0.0.1:8002/`도 지원한다. 2026-10-21 서버 담당자의 설치 후 센서 준비 경로는 HTTP 200(`configured=true`, `inference_checked=false`), 지문 없는 처리 요청은 HTTP 422를 확인했다. 준비 응답만으로 실제 센서 추론·매칭 성공을 뜻하지 않는다.

## Windows 사용

1. `BlurFing.ScannerComparison.exe`를 연다. 전체 FFV SDK·USB 드라이버는 기존 설치를 사용한다. 기존 FFV 앱이 센서를 점유 중이면 닫는다.
2. 비교 서버 주소를 확인하고 **`선택한 서버로 연구용 지문 영상 전송`만 체크한다.** 원클릭 취득에서는 `기존 FFV 창의 새 취득 자동 처리`는 비워 둔다. 앱 재실행·주소 변경 시 전송 선택을 다시 확인한다.
3. **지문 취득 후 자동 비교**를 누르고 손가락을 올린다. 새 영상 → 서버 처리 → 원본·처리본·점수를 자동 표시한다. 처리 버튼을 따로 누를 필요가 없다.
4. 최초 1회 위치가 없으면 `FFV 위치 설정`에서 공식 SDK의 `Bin/Win64_x64/BlurFingFfvOneClick20261021.exe`를 선택한다. 스캐너 모듈 선택도 기억한다. 모듈을 바꿀 때는 `%LOCALAPPDATA%/BlurFing/FFVOneShot/scanner-modules.txt`만 삭제해 재선택한다.
5. `3열 비교 자료 저장`으로 원본·처리본·점수 JSON·`hstack.png`를 새 개인 폴더에 저장한다. 지문 자동 저장·공개 Git 업로드는 하지 않는다.

전달본 `scanner-connection.json`은 서버 주소와 기존 SDK 취득기 위치만 제공한다. 정상적인 사용자 설정이 우선하며 0.2.1부터 잘못된 취득기 경로는 전달 설정의 정상 경로로 복구한다. 다른 PC에서는 해당 PC의 전체 SDK 위치를 다시 선택한다. SDK·드라이버·종속 DLL은 전달 ZIP에 포함하지 않는다.

### 취득 창이 안 뜨고 기다리기만 하는 경우

`FFV 위치 설정`에서 **비교 프로그램 자체(`BlurFing.ScannerComparison.exe`)를 선택하면 안 된다.** 취득기는 전체 공식 SDK의 `Bin/Win64_x64/BlurFingFfvOneClick20261021.exe`다. 0.2.1은 실행 파일을 실행하지 않고 원클릭 취득 코드의 메타데이터와 같은 위치의 공식 SDK 종속 파일·`FScanners` 폴더를 확인한다. 전달 폴더에 EXE만 복사한 파일이나 구형 FFV 확장은 선택을 거절한다.

기존 잘못된 설정을 수정한 뒤에는 이전 창을 닫고 0.2.2를 다시 연다. 전송 체크는 다시 해야 한다. 처음 뜨는 스캐너 모듈 선택에서 설치된 `SupremaBioMini`를 선택한다(모듈 폴더 이름은 `NdmSupremaBioMini`). 장치 관리자에서는 센서가 `Authentication Scanner (0x0408)`로 표시될 수도 있으므로 이름에 BioMini가 없다는 이유만으로 USB 연결 실패로 판단하지 않는다.

**센서 불빛은 켜지는데 영상이 오지 않고 90초 후 시간 초과:** 0.2.2 비교 프로그램과 `BlurFingFfvOneClickV2_20261021.exe` 취득기를 함께 사용한다. 이전 취득기는 동기 Windows pipe의 취소 대기 읽기가 결과 쓰기를 막을 수 있었다. 0.2.2 helper는 양방향 overlapped I/O로 수정했다. 기존 모듈 선택은 그대로 사용한다. 이 PC의 설정도 새 helper로 교체했으며 다른 PC에서는 전체 공식 SDK 안의 새 helper를 직접 선택한다.

취득 실패는 센서 없음·20초 취득 제한·품질 검사 실패로 구분한다. `%LOCALAPPDATA%/BlurFing/FFVOneShot/last-attempt.log`에는 최근 시도의 고정 단계·SDK 결과 상태·오류 종류만 남긴다. 원본 영상·특징점·DB 비밀번호·오류 전문은 기록하지 않는다. 지문을 내보낼 때만 기존 개인 저장 기능을 사용한다.

점수는 **SourceAFIS 원시 유사도**이며 0~100%·본인 확률로 바꾸지 않는다. 특징점 부족은 측정 불가, 매칭 환경 실패는 미측정이다. 현재 원본과 그 처리본의 직접 비교로, 독립 취득 참조에 대한 보호 효과 입증과 구분한다. DPI 500은 앱 설정값이며 장치에서 조회한 값은 아니다.

## 취득·취소·자료

버튼마다 별도 helper 프로세스와 같은 Windows 사용자만 접근 가능한 임의 named pipe를 만든다. 기존 FFV 미리보기·등록 자료 선택을 새 취득 결과로 쓰지 않는다. 취득부터 서버 비교까지 구형 미리보기 수신을 무시한다. 새 취득·취소는 이전 처리본·점수를 무효화한다.

설치된 FFV 공개 API에는 원시 Capture가 없고 `Enroll(20000)`·`GetBitmap()`이 있다. 요청마다 `%LOCALAPPDATA%/BlurFing/FFVOneShot/<새 GUID>/`에 임시 등록 DB를 만들고 성공 영상만 얻는다. 임시 자료 정리를 확인한 뒤 전송하며 정리 실패 시 전송을 거절한다. 기존 FFV 등록 DB는 열거나 지우지 않는다. 비정상 강제 종료·전원 차단 시 남은 새 GUID 폴더는 취득기가 실행 중이지 않을 때 수동 정리한다. 보안 삭제 보장은 아니다.

최초 모듈 선택 포함 대기는 90초다. 취소 시 pipe를 닫아 SDK Cancel을 요청하고 5초 후에도 멈추지 않는 이번 helper만 종료한다. 다른 FFV 앱·전역 SDK 서비스는 종료하지 않는다. 품질 기준을 낮추거나 실패 영상을 성공으로 바꾸지 않는다.

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
