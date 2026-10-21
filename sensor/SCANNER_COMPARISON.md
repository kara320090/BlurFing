# 센서 원본 · 서버 처리본 · 매칭 점수 비교

**2026-10-21 최신 0.2.4:** [원클릭 안내](ONE_CLICK.md)대로 사용한다. BioMini의 `UFS_StartCapturing` 콜백에서 300×400·500ppi 원본을 직접 취득해 학교 서버에서 처리하며, 사용자 원클릭 연속 3회 성공을 확인했다. FFV의 150×200 컬러 등록 결과는 원본으로 사용하지 않는다. 서버 SourceAFIS 3.18.1의 실제 점수 표시도 확인했다. 아래 별도 FFV 창 사용은 이전 보조 경로의 기록이다.

2026-10-21: **지문 취득 후 자동 비교** 버튼과 같은 학교 서버의 `/scanner/` 연결 준비를 추가했다. 최신 실행·임시 등록 자료 취급·서버 적용은 [버튼 연결 안내](ONE_CLICK.md)를 따른다. 아래 별도 FFV 창 연동도 지원한다. 설정에는 서버·DPI와 FFV 취득기 경로만 저장하며 지문·전송 동의는 복원하지 않는다.

요청 범위: BioMini Slim 2를 사용하는 Windows FFV 취득 프로그램에서 새 영상을 받아 학교 Ubuntu 서버로 전송하고, 원본·처리본·두 영상의 매칭 점수를 3열로 표시한다. Windows·시스템 통합 구현: 이봉헌. 실제 센서 취득·평가 검증은 최승빈, AI 처리 검증은 유재윤, 학교 서버 연결은 한윤섭과 공동 확인한다.

## 실행

배포본의 `BlurFing.ScannerComparison.exe`를 실행한다. Windows x64 자체 포함 배포이며 .NET 별도 설치가 필요 없다. 기존 FFV SDK·USB 드라이버는 기존 설치를 사용하며 이 프로그램에 포함하지 않는다.

1. 기존 FFV 프로그램이 센서를 사용 중이면 닫는다.
2. 비교 프로그램과 FFV 확장을 연다. FFV 확장은 기존 공식 샘플의 센서 선택·취득 동작을 유지한다.
3. FFV 확장의 **Send to comparison**을 켠 뒤 새 지문을 취득한다. 이미 떠 있던 이전 영상은 자동 전송하지 않는다.
4. 비교 프로그램에 학교 서버의 **센서 전용 HTTPS 기본 주소**를 입력한다. [SSH 시연 구성](../demo/README.md)에서는 전달된 `http://127.0.0.1:8002`를 사용한다. V1 Mock/PHOTO V2 주소만으로는 센서 API가 준비되지 않는다.
5. `서버 확인`으로 설정을 확인한다. 이 검사는 실제 AI 추론·매칭 성공이나 센서 연결을 확인하지 않는다.
6. `선택한 서버로 연구용 지문 영상 전송`과 `FFV 새 취득 후 자동 처리`를 선택하면 이후 새 취득마다 처리한다. 수동으로 `서버 AI 처리 · 매칭`을 눌러도 된다. 서버 주소 변경 시 전송 선택을 해제한다.

자동 연동 없이 FFV에서 저장한 회색조 PNG/BMP를 열 수도 있다. 파일 입력은 실시간 센서 취득으로 표시하지 않는다. 설정 DPI 기본값 500은 설정값이며 현재 센서에서 조회한 실측 DPI가 아니다.

## 화면과 저장

| 칸 | 표시 |
|---|---|
| 1 | FFV 원본 회색조 영상, 크기·입력 출처 |
| 2 | 서버가 실제 반환한 처리본 또는 처리 거절 시 원본 반환 안내 |
| 3 | SourceAFIS 원시 유사도 점수, 엔진 버전·설정 DPI·두 영상 특징점 수 |

기존 scanner 실험 처리기를 호출한다. 새 신경망을 학습하거나 기존 PHOTO 엔진으로 센서 입력을 대체하지 않는다. 처리 거절은 보호 성공이 아니다. 매칭 미준비·실행 실패는 `미측정`, 특징점 0은 `측정 불가`이며 임의의 0점·일치율을 만들지 않는다.

SourceAFIS의 출력은 0~100% 확률이 아닌 비음수 유사도 점수다. 상한 100으로 자르거나 다른 엔진의 점수와 직접 비교하지 않는다. 임계값과 본인/타인 판정을 새로 정하지 않았다. 비교 대상은 **현재 센서 원본 대 그 영상의 AI 처리본**이며 독립 취득 참조나 신원 인증의 증거가 아니다. [공식 점수 설명](https://sourceafis.machinezoo.com/java)을 참고한다.

`3열 비교 자료 저장`은 사용자가 선택한 새 폴더에 다음을 저장한다. 원본 파일은 덮어쓰지 않는다.

- `original.png`: 픽셀을 유지해 회색조 PNG로 정규화한 업로드 원본. SDK BMP의 헤더·메타데이터까지 동일한 파일은 아니다.
- `processed.png`: 검증한 실제 서버 반환 PNG.
- `comparison.json`: 요청 ID·양쪽 해시·점수·버전·DPI·특징점 수·시각·처리 상태. 템플릿·서버 경로는 포함하지 않는다.
- `hstack.png`: 원본·처리본·점수 카드의 3열 이미지.

새 취득·취소 시 이전 처리본·점수를 지우고 요청 세대를 바꾼다. 이전 요청의 늦은 응답은 현재 화면에 적용하지 않는다. FFV 영상 전달은 같은 Windows 사용자만 접근할 수 있는 named pipe를 사용한다. 새 버튼의 SDK 임시 등록 자료 취급은 [연결 안내](ONE_CLICK.md#취득취소자료)를 따른다. 앱 종료 후 사진·결과를 복원하지 않는다. 서버 주소·설정 DPI·FFV 취득기 경로만 `%LOCALAPPDATA%/BlurFing/ScannerComparison/settings.json`에 보관한다.

## 서버

[Ubuntu 연결 준비](server/README.md)와 [같은 서버 경로 추가](ONE_CLICK.md#학교-서버-적용)를 따른다. 2026-10-21 사진 HTTPS 준비 응답은 확인했고 센서 경로는 404였다. 프로그램 전달과 학교 센서 API의 실제 배포·추론 확인은 구분한다.

## 빌드·검증

```powershell
dotnet run --project sensor/BlurFing.ScannerComparison.Checks -c Release
dotnet run --project sensor/BlurFing.SensorCapture.Checks -c Release
dotnet publish sensor/BlurFing.ScannerComparison -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None -p:DebugSymbols=false -o artifacts/scanner-comparison/win-x64-single

& sensor/ffv-extension/build-capture.ps1 -SdkRoot '<공식 FFV SDK 폴더>' -OutputName BlurFingFfvCompare.exe
# sensor/server/에서
python -m pytest test_scanner_api.py -q
```

합성 패턴 버튼은 화면 확인용이며 AI 처리본·실제 지문·실제 점수를 만들지 않는다. 검증 범위와 실행 결과는 [작업 기록](../docs/worklogs/2026-10-20-이봉헌-scanner-comparison.md)을 따른다.
