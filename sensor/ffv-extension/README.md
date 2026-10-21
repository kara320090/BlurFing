# FFV 이미지 저장 확장 소스

**2026-10-21 최신 경로:** `--capture-once`는 `BlurFingRawOneShot`에서 설치된 BioMini 모듈의 원본 회색조 콜백을 사용한다. FFV 등록·`GetBitmap()` 결과를 사용하지 않으며 기존 등록 DB를 만들거나 열지 않는다. 300×400·500ppi 원본과 실제 학교 서버 처리, 사용자 원클릭 연속 3회 성공을 확인했다. [최신 실행·취급 안내](../ONE_CLICK.md)를 따른다. 아래 FFV 샘플 창과 임시 등록 모드는 이전 기록이다.

2026-10-21: `--capture-once <요청별 pipe>` 모드를 추가했다. 비교 앱 버튼으로 새 FFV 취득을 시작하고 임시 등록 자료를 정리한 뒤 정확한 SDK PNG를 전달한다. [버튼 연결과 자료 취급](../ONE_CLICK.md)을 따른다. 기존 샘플 창 모드는 그대로 지원한다. 실제 센서 취득은 장비 검증이 남아 있다.

이봉헌이 로컬에서 준비한 `BlurFingFfvCapture.cs`를 GitHub에 옮긴 실험용 소스다. 기존 빌드 스크립트에는 외부 SDK 경로 지정과 필수 파일 확인을 추가했다. 실제 장치 취득·저장은 아직 검증하지 않았다. 조사와 담당 범위는 [인수인계 문서](../../docs/sensor-handoff.md)를 확인한다.

Neurotechnology 공식 FFV C# 샘플의 화면을 사용하고 BMP/PNG 저장 버튼을 추가한다. SDK·샘플 실행파일·종속 DLL은 포함하지 않는다. 소스의 저작권 표시는 유지한다.

## 준비

- Windows 10/11 x64.
- [Xperix 공식 드라이버](https://tech.xperix.com/en/support/solutions/articles/69000857511--device-driver-biomini-windows).
- [공식 FFV 3.1 전체 ZIP](https://download.neurotechnology.com/FreeFingerprintVerification_3_1_SDK_2026-03-30.zip).
- [.NET Framework 4.8](https://dotnet.microsoft.com/en-us/download/dotnet-framework/net48). .NET 10과 별개의 환경이다.
- 공식 SDK에 포함된 라이선스 확인. [라이선스 안내](https://www.neurotechnology.com/licensing_ffv_sdk.html).

## 폴더 배치

전체 ZIP을 압축 해제한 후 아래 구조로 둔다. SDK 루트가 두 번 중첩되지 않도록 확인한다. SDK 폴더와 다운로드 ZIP은 `.gitignore`에서 제외한다. SDK를 저장소 밖에 놓고 아래 `-SdkRoot`로 지정해도 된다.

```text
ffv-extension/
  BlurFingFfvCapture.cs
  build-capture.ps1
  README.md
  FreeFingerprintVerification_3_1_SDK/
    Bin/
      Win64_x64/
        CSharpSample.exe
        Neurotec.Biometrics.Nffv.dll
        Nffv.dll
        NffvServer.exe
        FScanners/
        ... 나머지 공식 배포 파일
    ... 문서·라이선스·샘플
```

나열된 파일만 골라 복사하지 말고 전체 SDK 디렉터리를 보존한다. 시작에 필요한 파일이 여러 폴더에 나뉘어 있다.

## 빌드

`ffv-extension` 폴더에서 PowerShell을 열고 스크립트를 검토한 뒤 실행한다.

```powershell
.\build-capture.ps1
```

SDK를 다른 위치에 둔 경우:

```powershell
.\build-capture.ps1 -SdkRoot 'C:\SDKs\FreeFingerprintVerification_3_1_SDK'
```

`-SdkRoot`는 예시 경로 대신 실제 압축 해제한 SDK 루트를 지정한다. 컴파일된 실행파일은 해당 SDK의 `Bin\Win64_x64`에 생성된다. 빌드 스크립트는 SDK나 생성된 앱을 실행하지 않는다.

스크립트는 Windows의 다음 C# 컴파일러를 사용한다.

```text
%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
```

출력은 아래 두 파일이다.

```text
FreeFingerprintVerification_3_1_SDK\Bin\Win64_x64\BlurFingFfvCapture.exe
FreeFingerprintVerification_3_1_SDK\Bin\Win64_x64\BlurFingFfvCapture.exe.config
```

SDK 경로·컴파일러·참조 DLL이 없다는 오류가 나면 설치와 폴더 구조부터 확인한다. 학교 PC에서 스크립트 실행이 관리 정책으로 차단되면 해당 정책에 맞는 실행 방법을 확인한다.

## 실제 센서를 확보한 후

1. USB 연결과 드라이버 인식 상태를 확인한다.
2. 공식 `CSharpSample.exe`에서 먼저 실제 스캐너가 열리는지 확인하고 종료한다.
3. 같은 SDK 폴더에 생성된 `BlurFingFfvCapture.exe`를 실행한다. 실행파일 하나만 다른 곳으로 옮기지 않는다.
4. 스캐너 선택 창에서 `SupremaBioMini`와 실제 장치를 선택한다.
5. 동의를 확보한 참여자의 익명 ID로 `Enroll`을 수행한다.
6. 이번 등록이 성공하고 새 이미지가 표시된 경우 `Save BMP / PNG`를 누른다.
7. 저장한 파일과 취득 시각·ID를 대조한다. 실패 후 남은 이전 이미지를 새 취득으로 기록하지 않는다.

아직 실물로 취득·저장한 검증 결과는 없다. 지금까지 확인된 것은 빌드와 모듈 열거·선택 화면이다.

## 저장과 한계

- 이미지 저장은 공식 샘플의 `pbExtractedImage.Image`를 이용한다.
- 샘플은 등록 성공(`TemplateCreated`) 경로에서 `GetBitmap()`을 표시한다. 등록 실패 시 이미지가 없을 수 있다.
- 저장 시 화면 캡처나 리사이즈를 수행하지 않는다. 센서 RAW와 바이트 단위 동일성을 검증한 것은 아니다.
- 기본 DB·로그 위치: `%LOCALAPPDATA%\BlurFing\FFVCapture`.
- `fingerprints.dat`, `users.dat`에는 실제 등록 자료가 들어갈 수 있다. Git에 넣지 않는다.
- 일괄 저장·자동 CSV·품질 점수 기록·오류 후 상태 관리 등은 추가 검토할 개발 항목이다.
- 공식 샘플 화면의 컨트롤 이름이 바뀌면 시작 오류가 날 수 있다. 이 소스는 조사한 3.1 샘플 기준이다.
- 저장된 사진 파일의 보호 전후 비교는 별도 평가 엔진으로 설계한다.
## 서버 AI 비교 프로그램 연동

`BlurFingComparisonBridge.cs`는 공식 샘플의 새 미리보기 영상을 같은 Windows 사용자의 비교 프로그램으로 전달한다. `Send to comparison`은 기본 꺼짐이며 켠 이후의 새 취득만 보낸다. SDK 자체의 취득·등록·검증 동작은 변경하지 않는다. [3열 비교 안내](../SCANNER_COMPARISON.md)를 따른다.

`build-capture.ps1`은 두 C# 소스 파일을 함께 컴파일한다. 기존 실행 파일을 유지하려면 `-OutputName BlurFingFfvCompare.exe`로 별도 이름을 사용한다. 비교 확장은 기존 공식 FFV SDK의 `Bin/Win64_x64`에서 실행하며 SDK 바이너리를 비교 프로그램 배포 폴더로 복사하지 않는다.
