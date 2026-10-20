# BlurFing 실제 시연 준비

기준: 2026-10-20 공개 main의 자동 V23. Android 사진 처리가 주 시연이고 FFV 센서 비교가 보조 시연이다.
자료 제출·버전 동결은 **10월 23일**, 발표는 **10월 30일**이다.
사진 한 장의 앱 처리·저장·재읽기는 **120초 이내**를 목표로 실제 휴대폰에서 연속 3회 확인한다.

## 현재 막힌 부분

공개 main·Git LFS·GitHub 릴리스에는 V6 가중치·대응 설정·사용 자료 레지스트리·외부 모델이 없다. 소스만 받아 실제 추론 완료로 표시하지 않는다.
2026-10-20 사용자가 비공개 인수 묶음을 전달해 현재 PC에서는 2,251개 파일 복원·해시 검증과 기준 재현을 완료했다.
고정 시드 RGB·마스크가 인수 결과와 일치했고 에뮬레이터의 실제 서버 AI·저장 재읽기도 통과했다. 앱 경로는 약 177초로 120초 목표 미달이다.
학교 서버 연결과 실물 Android·센서 시험은 **10월 21일부터**, 새 촬영 독립 평가는 자료를 확보한 뒤 진행한다. [실측과 한계](../docs/worklogs/2026-10-20-이봉헌-private-handoff-replay.md)를 따른다.

필요한 인수 자료:

- V6 `final_context_whole_pad.pt`와 그 가중치에 대응하는 `final_config.private.json`.
- 비어 있지 않은 기존 `consumed_registry.private.json` 전체 이력. 새 빈 파일로 만들지 않는다.
- COLFISPOOF 소스·모델, MediaPipe 모델, 각 환경의 Python 버전·패키지 목록·`pip check` 결과.
- 모델·설정·레지스트리·외부 모델 SHA256, 기준 개발 입력과 예상 적용/거절 마스크·결과·시드.
- 센서용 NBIS와 SourceAFIS의 기존 검증 runtime·설정·해시.

실제 사진·지문·라벨·가중치·개인 환경 설정은 공개 Git에 추가하지 않는다. [인수 자료 구분](../ai/PUBLIC_PRIVATE_DATA_KO.md)을 따른다.
개인 설정·출력은 이 폴더의 `private/`에 보관한다. 공개 예시는 실행 가능한 실제 경로·정답 자료가 아니다.

## 1. 자산 검사와 Ubuntu 실행

`runtime.example.json`을 `private/runtime.private.json`으로 복사하여 **서버의 실제 경로**와 인수받은 해시를 채운다.
Windows에서도 같은 형식을 사용하며 경로는 JSON의 `C:/...` 표기로 쓸 수 있다.
Python/API/AI/COLFISPOOF/MediaPipe 환경을 혼합하거나 문서에 관측된 버전을 무작정 최신 버전으로 교체하지 않는다.
기존 Python 환경을 만들고 검증된 패키지를 준비하는 작업은 이 검사기가 수행하지 않는다.

```bash
python demo/runtime.py preflight --config demo/private/runtime.private.json --probe --output demo/private/preflight.private.json
# 두 터미널에서 각각 실행. 둘 모두 loopback 전용, 1 worker.
python demo/runtime.py serve --config demo/private/runtime.private.json --service photo
python demo/runtime.py serve --config demo/private/runtime.private.json --service scanner
```

검사 실패는 종료 코드 2다. 출력 파일은 덮어쓰지 않는다. 파일 해시·기존 레지스트리 이력과 V6의 개발 전용 플래그를 확인한다.
`--probe`는 환경별 패키지 목록·`pip check`, 기존 V6의 protocol/소스/encoder 검사까지 수행한다.
이 검사가 통과해도 **추론·센서 취득·보호 효과가 검증된 것은 아니다**. 서버 기동 뒤 실제 입력으로 다음 단계를 확인한다.
이미 사용한 개발 사진을 재실행할 때만 `development_replay: true`를 명시하고, 독립 평가로 기록하지 않는다.
설정과 가중치의 승인 플래그·소스 해시를 바꿔 통과시키지 않는다.

## 2. Windows 노트북·USB 휴대폰 연결

기존 SSH 로그인·호스트 키 확인은 사용자가 먼저 끝낸다. 비밀번호·키를 인수 JSON에 넣지 않는다.
실물 기기는 USB 디버깅을 허용하고 `adb devices -l`에서 일련번호를 확인한다.

```powershell
py -3.11 demo/connect.py --ssh-target <기존-SSH-별칭> --adb <adb.exe-경로> --serial <USB-일련번호> --dry-run
py -3.11 demo/connect.py --ssh-target <기존-SSH-별칭> --adb <adb.exe-경로> --serial <USB-일련번호>
```

Windows의 8001/8002를 SSH로 학교 Ubuntu의 loopback 포트에 연결한 뒤 휴대폰의 8001을 USB로 전달한다.
포트나 기존 USB 매핑이 사용 중이면 덮어쓰거나 기존 프로세스를 종료하지 않는다. 터미널을 유지하고 Ctrl+C로 종료한다.
시연 연결은 에뮬레이터를 실물 휴대폰으로 허용하지 않는다. `/ready`는 양쪽 계약의 **설정 확인**이다.

- Android 최신 **debug APK**: 자동 V23 선택, 서버 `http://127.0.0.1:8001`.
- Windows 비교 프로그램: 서버 `http://127.0.0.1:8002`.
- 학교 서버 구간은 SSH로 전달한다. 이 USB 개발 구성을 일반 사용자용 HTTPS 배포 완료로 표시하지 않는다.
- 기존 V1 Mock·Quick Tunnel 주소가 실제 V23·센서 서비스를 대신하지 않는다. 다른 엔진·Mock으로 자동 전환하지 않는다.

## 3. 실제 HTTP와 저장 자료 재현

API 도구를 실행하는 환경에는 backend 요구 패키지와 httpx가 필요하다.
입력은 **sRGB·EXIF 방향을 정규화한 RGB8 PNG**여야 한다. JPEG에서 색상 프로필을 그냥 지우지 않는다.
같은 개발 입력으로 재현할 경우 원본 입력 bytes와 고정 시드 검증 경로를 구분한다. HTTP API는 시드를 받지 않는다.

```bash
python demo/rehearse_photo.py --input demo/private/source.png --base-url http://127.0.0.1:8001 --output demo/private/rehearsal-01 --acknowledge-private-upload
```

새 출력 폴더에 모든 3회 시도, 요청 ID·시간·실패 유형, 검증 응답, 반환 PNG, 적용·거절 마스크를 남긴다.
응답의 원본 결합·마스크·픽셀 보존은 기존 V2 검증기를 재사용하고 저장 PNG를 다시 읽는다.
실패한 시도도 기록한다. 부분 적용은 후보 처리 결과일 뿐 전체 보호 성공이 아니다.
HTTP·디스크 검증 통과를 Android·실물 기기·실제 모델 검증으로 승격하지 않는다.

휴대폰에서는 같은 시연 사진을 **연속 3회** 직접 선택·자동 처리·저장한다.
최신 화면의 버전·요청 ID·결과 검증 시간·저장 재읽기 시간을 각 회차 증빙에 남긴다.
앱 시간은 단조 시계이며 사진 불러오기부터 측정한다. 수동 재실행은 별도 시작으로 표시한다.
저장 위치 선택·사용자 대기 시간도 포함하고, 프로세스 복원 후 과거 시간을 재사용하지 않는다.
평균으로 초과 회차를 숨기지 않고 최초 실행·반복 실행과 최대 시간을 함께 기록한다.

## 4. 새 자료 평가와 센서 비교

동의된 새 촬영은 최소 두 그룹·그룹당 6장으로 시작한다. 개발용과 평가용 사람·촬영 회차를 먼저 분리한다.
개발용만 오류 수정에 사용하고 평가용은 버전 고정 후 실행한다. 이 최소 수량은 통계적 충분성을 보장하지 않는다.
원본 좌표의 L 모드 0/255 마스크로 **미검출을 포함한 모든 손끝**을 표시하고 visible/not_observed/uncertain을 사람이 판단한다.
검출 누락, 경계 침범, 가시성 판단, 합성 거절, 질감 문제를 별도로 기록한다.

```bash
python demo/evaluate_photo.py --manifest demo/private/evaluation.private.json --output demo/private/evaluation-report.private.json
```

`evaluation.example.json`에 실제 자료를 채운다. 같은 사진·같은 RGB·사람·촬영 그룹의 개발/평가 중복과 기존 사용 자료의 평가 재사용을 거절한다.
후보 A∪R과 실제 적용 A를 각각 사람 정답과 비교하여 IoU·recall·precision·침범 픽셀·손끝별 검출/적용 비율을 기록한다.
거절 사유를 가시성 정답으로 바꾸거나, 작은 표본의 통과를 일반화·보호 승인으로 바꾸지 않는다.
사진 전체 지문 잔존·압축 후 매칭·자연스러움은 별도 실제 평가가 필요하다.

센서는 [FFV 비교 안내](../sensor/SCANNER_COMPARISON.md)를 따라 **새 취득**→실제 서버 처리→원본/처리본/원시 점수→내보내기를 3회 확인한다.
파일을 연 경우 실시간 취득으로 기록하지 않는다. 내보낸 comparison.json의 `input_origin`도 확인한다.
독립 취득한 동일 손가락 참조와 비교하려면 검증된 scanner AI Python·SourceAFIS 환경에서 실행한다.

```bash
python demo/evaluate_scanner.py --reference private/reference.png --original private/original.png --processed private/processed.png --output private/reference-evaluation-01 --dpi 500 --same-finger-confirmed
```

원본↔참조 / 처리본↔참조 / 원본↔처리본을 같은 설정에서 기록한다. 원본과 같은 영상은 독립 참조로 받지 않는다.
원본↔참조가 비교 가능한지 먼저 확인한다. 점수는 확률·백분율이 아니고 새 본인 판정 임계값을 만들지 않는다.
특징점 없음·실행 실패는 null/측정 불가다. 0점을 보호 성공으로 계산하지 않는다. 설정 DPI와 실제 DPI를 구분한다.

## 5. 동결·시연·완료 확인

| 날짜 | 실행·증빙 |
|---|---|
| 10/21 | 자산·환경 인수, 기준 결과 재현, Ubuntu 실제 모델, 실물 USB 휴대폰·FFV |
| 10/22 | 개발 오류 수정, 미사용 그룹 평가, Android 3회 각 120초 이내·센서 3회 실제 검증 |
| 10/23 | 커밋·APK·EXE·서버·모델 식별 정보 고정, 실제 결과·실패 기록·발표 자료 제출 |
| 10/24~29 | 같은 버전 리허설, 시연을 막는 오류만 수정 후 관련 검증 반복 |
| 10/30 | 실제 시연·질의응답 |

완료를 표시하기 전에 확인한다:

- [ ] 실제 모델 전체 추론과 Windows/Ubuntu 검출·적용/거절 마스크 비교. 픽셀 동등성은 내부 고정 시드 경로에서 비교.
- [ ] 실물 휴대폰 자동 처리·저장·재읽기 연속 3회, 각 회차 120초 이내. 원본 파일 불변 확인.
- [ ] 사람이 주 시연 사진 전체 손끝을 대조. 부분 적용/적용 없음도 정확히 안내.
- [ ] 취소·시간 초과·서버 중단·재시도·늦은 응답·갤러리/카메라·회전/백그라운드·공유 확인.
- [ ] 실센서 FFV→Ubuntu→유효 점수→비교 저장 연속 3회와 독립 참조 측정.
- [ ] 최신 회귀 검사, 모델·패키지·커밋·APK/EXE SHA256, 원본 결합과 저장 readback 증빙.
- [ ] 같은 버전의 실제 녹화 예비본 준비. 녹화를 사용하면 녹화임을 표시.

발표 10분: 소개 1분 → Android 처리·구조 2분 → 결과 확인 1분 → 센서 2분 → 문제 해결·실제 소통 증빙 2분 → 한계·계획 2분.
발표자·Android·AI·센서 질의응답 역할을 미리 정하고, 실제 GitHub·카카오톡·대면 기록만 증빙에 사용한다.
장애나 120초 초과는 그대로 기록하고 실시간 범위를 조정한다. 저장 결과·수동 처리를 실시간 자동 처리로 바꾸어 소개하지 않는다.

## 공개 합성 회귀

```bash
python -m pytest demo/test_demo.py -q
```

테스트의 가중치·mask·매칭·HTTP 응답은 명시적 합성 fixture다. 실제 모델·지문·실물 장비 성능을 시험하지 않는다.
현재 구현·검증과 남은 작업은 [당일 기록](../docs/worklogs/2026-10-20-이봉헌-demo-handoff.md)을 따른다.
