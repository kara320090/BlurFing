# BlurFing 센서 영상 수집 도구

주담당: **최승빈**(센서 취득·품질·측정). 이번 사전 준비: **이봉헌**(사용자 요청에 따른 Windows 수집 도구·SDK 어댑터·설치 및 통합 기반). 최승빈의 실장비 검증·측정 업무를 완료한 것으로 기록하지 않는다.

BioMini Slim 2용 Windows 준비 프로그램이다. **프로그램 실행·합성 영상 저장은 검증했으며, 실제 SDK·센서 취득은 아직 검증하지 않았다.** SDK와 하드웨어가 없을 때 실제 영상이나 일치 점수를 생성하지 않는다.

## 공식 다운로드와 설치

2026-09-22 제조사 자료 확인:

| 항목 | 공식 링크 | 확인 내용 |
|---|---|---|
| 센서 사양 | [BioMini Slim 2](https://www.xperix.com/products/biomini-slim-2) | 500 ppi, 300×400, 8비트 회색조, RAW/BMP 등 지원. 제조사 사양이며 실측값 아님 |
| USB 드라이버 | [Windows 드라이버 안내](https://tech.xperix.com/en/support/solutions/articles/69000857511--device-driver-biomini-windows), [공식 첨부 설치 파일](https://tech.xperix.com/helpdesk/attachments/69121545640) | 공개 다운로드. 센서 연결용 드라이버이며 개발 SDK는 포함하지 않음 |
| 개발 SDK | [BioMini SDK 안내](https://www.xperix.com/products/developer/sdks) | Windows C#/C++ 지원. **Purchase required**로 안내됨. 센서 판매자가 SDK를 포함하는지 별도 확인 필요 |
| 지원 경로 | [제조사 기술 지원](https://tech.xperix.com/), [문의처](https://www.xperix.com/company/contact-us) | 구매처 또는 제조사에 Windows SDK 설치 파일·라이선스·x64/x86 재배포 파일 요청 |
| API 근거 | [제조사 DLL 호출 예제](https://tech.xperix.com/en/support/solutions/articles/69000867655-sample-python-code-for-biomini) | 초기화, 장치 수·핸들 조회, 한 장 취득, BMP 저장, 종료의 6개 UFS 함수 |
| 아키텍처 | [SDK 비트 수 안내](https://tech.xperix.com/en/support/solutions/articles/69000457451--guide-tip-biomini-sdk-net-wrapper-and-windows-architecture) | 앱과 SDK DLL의 x64/x86를 맞춰야 함 |

SDK는 공개 다운로드 파일을 찾지 못했으며 현재 설치되어 있지 않다. 임의 사이트의 DLL로 대체하지 않는다. 제조사 공식 샘플에 나온 함수로 어댑터를 작성했으나, 수령한 SDK의 헤더·라이선스·지원 버전 확인과 실제 센서 시험을 거쳐야 한다. SDK 라이선스를 우회하거나 유료 SDK 구매를 대신 진행하지 않았다.

이 작업 PC에는 공식 `Fingerprint_Driver.exe` 설치를 완료했다. 설치 파일 버전은 **2.2.1.2**, 실제 등록된 드라이버는 **3.0.3.0 (2022-10-26)**이다. 설치 완료 화면과 `pnputil /enum-drivers`의 Xperix `sfr.inf` 등록을 확인했다. 센서가 연결되어 정상 인식되었다는 뜻은 아니다.

설치 파일 SHA-256:

```text
62A863123450BCCDE63DA7501C3102B9D4E63F01639260E3FDFA2436E0B0FC5D
```

설치 EXE 자체의 Authenticode 서명은 없었으며, 설치된 드라이버 카탈로그 `sfr500.cat`은 유효한 서명으로 확인했다. Windows 등록 서명자는 Microsoft Windows Hardware Compatibility Publisher다. 설치 파일·SDK·라이선스는 Git에 포함하지 않는다.

## 실행 순서

1. 배포된 `win-x64/BlurFing.SensorCapture.exe`를 실행한다. 자체 포함 배포이므로 실행 PC에 .NET을 별도 설치할 필요가 없다. x86 SDK만 받은 경우 `win-x86` 프로그램을 사용한다.
2. SDK가 없으면 **합성 패턴 테스트** → **BMP · PNG · 기록 저장**으로 화면·저장을 확인할 수 있다. 합성 영상은 지문이 아닌 그라데이션·체커보드다.
3. SDK를 정식으로 수령해 설치한다. 제조사 재배포 폴더의 종속 DLL과 디렉터리 구조를 유지한다. SDK의 VC++ 런타임 등 요구사항은 해당 버전의 설치 안내를 따른다.
4. 센서를 USB에 연결하고 **SDK DLL 선택**에서 같은 비트 수의 `UFScanner.dll`을 고른다. **장치 확인**을 누른다. 여러 장치가 있으면 0부터 시작하는 장치 번호를 지정한다.
5. 참여 동의가 확보된 경우 화면의 동의 확인란을 선택하고 **지문 1장 취득**을 누른 후 손가락을 센서에 올린다. 기본 제한 시간은 20초다. 취소 버튼으로 중단할 수 있다.
6. 미리보기를 확인하고 익명 ID(예: `sample01`)를 입력해 저장한다. **저장 폴더 열기**로 결과를 확인한다.

기본 저장 경로는 `%LOCALAPPDATA%\BlurFing\Captures`이며 저장소 밖이다. 자동 업로드는 하지 않는다. 이름·학번을 ID로 사용하지 말고, 실제 지문 영상은 공개 GitHub에 올리지 않는다. ID 형식 검사는 영문·숫자·밑줄·하이픈만 허용하지만 숫자로 된 학번을 자동 식별하지는 못한다. 보관 기간과 삭제는 팀의 참여 동의 범위에 따라 관리한다.

## 출력과 처리 경계

- 각 저장은 `SENSOR_...` 또는 `SYNTHETIC_...`의 새 폴더를 만든다. 기존 영상을 덮어쓰지 않는다.
- `capture.bmp`: SDK가 저장한 원본 바이트를 보존한다. 합성 모드에서는 합성 BMP다.
- `capture.png`: 미리보기에서 변환한 무손실 PNG 사본이다. BMP와 픽셀은 같지만 BMP의 메타데이터·팔레트 표현까지 동일하지는 않다.
- `metadata.json`: 익명 ID, 출처, 합성 여부, UTC 취득 시각, 크기, 장치 번호, BMP SHA-256. 센서 모델명은 사용자가 선택한 대상 모델로만 기록하며 실제 조회했다고 주장하지 않는다. 실제 DPI·품질·매칭 점수·확률을 만들지 않는다.
- 실장비 취득 시작 시 이전 이미지를 지운다. 실패·취소·시간 초과에서 이전 합성 영상이나 취득 영상을 새 결과처럼 보여주지 않는다.
- 네이티브 SDK 호출은 별도 자식 프로세스에서 수행한다. 취소·시간 초과에서는 해당 프로세스를 종료하고 그 작업의 임시 폴더를 정리한다. 임의의 SDK 취소 함수를 가정하지 않는다. 강제 종료 후 실제 센서의 재취득 가능 여부는 실장비 시험 대상이다.
- SDK가 이미지를 만들 때 잠시 `%TEMP%\BlurFing\<작업 ID>`에 저장하며 정상 완료·오류·취소 시 정리한다. OS나 앱의 비정상 강제 종료 시 남을 가능성은 있다. 영구 저장은 사용자가 저장 버튼을 누를 때만 수행한다.

이 도구는 센서의 **참조 영상 취득**을 준비한다. 보호 알고리즘, 지문 매칭, 생체 감지, 위조 지문 제작 또는 안드로이드 USB 직접 연결은 구현하지 않았다.

## 빌드와 자동 검증

Windows와 .NET 10 SDK가 필요하다. 저장소 루트에서:

```powershell
dotnet run --project sensor/BlurFing.SensorCapture.Checks -c Release
dotnet publish sensor/BlurFing.SensorCapture -c Release -r win-x64 --self-contained true -o artifacts/sensor/win-x64 -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false
dotnet publish sensor/BlurFing.SensorCapture -c Release -r win-x86 --self-contained true -o artifacts/sensor/win-x86 -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false
```

검사 프로그램은 16개 시나리오를 실행하고 하나라도 실패하면 종료 코드 1을 반환한다. 합성 표기, 원본 BMP 보존, PNG 전체 픽셀, 출처·해시, 중복 저장, 잘못된 ID·저장 경로·영상·DLL, 프로세스 시간 초과·취소, 자식 프로세스의 DLL 오류 전달과 임시 폴더 정리를 검증한다. SDK와 하드웨어의 실제 취득 검사는 포함하지 않는다. 상세 실행 결과는 [작업 기록](../docs/worklogs/2026-09-22-이봉헌-sensor.md)에 구분해 남긴다.

## SDK·센서 수령 후 최승빈과 공동 확인

1. 제조사 제공 샘플에서 원본 BMP 저장이 되는지 확인한다.
2. 받은 SDK의 함수 시그니처·호출 규약이 `NativeBioMini.cs`와 같은지 확인한다.
3. 무장치, 장치 연결, 정상 취득, 취소, 시간 초과, USB 분리, 재연결 후 재시도를 확인한다.
4. BMP 헤더의 실제 크기·비트 수·해상도와 원본 손실 여부를 확인한다. 화면에 보이는 300×400 합성 패턴을 센서 성공으로 집계하지 않는다.
5. 동의된 실제 참조 영상과 사진의 비교는 별도 평가 엔진 및 실험 계획에 연결한다. 품질 기준과 일치 점수 의미는 실측 후 정한다.
