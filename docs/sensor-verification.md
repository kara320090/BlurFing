# BioMini Slim 2 센서 연동 및 지문 저장 검증

BioMini Slim 2 실물 장치를 Windows 환경에서 Neurotechnology FFV 3.1 SDK와 연결하고, 공식 C# 샘플의 지문 등록·인증 및 BlurFing 확장 프로그램의 이미지 저장을 1차 확인했다.

1. **장치 연결** → BioMini Slim 2를 USB로 연결하고 FFV 공식 `CSharpSample.exe`에서 Suprema 계열 스캐너 모듈을 선택해 장치를 사용했다.
2. **등록·인증 확인** → `Enroll`로 지문을 등록하고 `Verify`로 등록 지문 인증을 수행했다. 두 기능 모두 정상 작동했다.
3. **확장 프로그램 빌드** → `sensor/ffv-extension/build-capture.ps1`을 실행했다. 최초에는 SDK 경로를 찾지 못했으나 `-SdkRoot` 옵션으로 실제 SDK 경로를 지정한 뒤 빌드에 성공했다.
4. **이미지 저장 확인** → 생성된 `BlurFingFfvCapture.exe`를 이용해 지문 이미지를 BMP/PNG 형식으로 저장하는 기능이 1차 정상 동작함을 확인했다.

확장 프로그램 빌드는 `sensor/ffv-extension` 폴더에서 아래 명령어로 재현한다. SDK 경로는 설치 환경에 맞게 지정한다.

```powershell
.\build-capture.ps1 -SdkRoot 'C:\실제\FreeFingerprintVerification_3_1_SDK'
```

빌드된 실행파일은 FFV SDK의 `Bin\Win64_x64\BlurFingFfvCapture.exe`에 생성된다. 공식 `CSharpSample.exe`를 종료한 후, 이 실행파일을 **SDK 폴더 내에서 그대로 실행**하고 스캐너 선택 → `Enroll` → 새 이미지 확인 → `Save BMP / PNG` 순서로 테스트한다.

최초 빌드 실패 메시지는 `Required file not found: ...\FreeFingerprintVerification_3_1_SDK\Bin\Win64_x64\CSharpSample.exe`였다. 기본 탐색 위치와 실제 SDK 설치 위치가 달랐던 것이 원인이며, `-SdkRoot` 지정으로 해결했다.

현재까지는 **실제 장치 연결, 지문 등록·인증, 이미지 저장의 1차 성공**만 확인했다. 저장 이미지의 세부 규격과 RAW 동일성, 반복 취득 안정성, USB 재연결 및 취득 실패 후 상태 복구는 검증하지 않았다. 특히 이전에 표시된 이미지가 새 취득 결과로 잘못 저장되지 않는지 확인할 필요가 있다.

다음 단계에서는 같은 손가락을 여러 번 취득해 파일을 재확인하고, 유재윤(AI·성능 검증)과 SourceAFIS/NBIS 등 평가 엔진 및 점수 해석 기준을 협의한다. 센서 참조 지문과 사진 속 지문은 취득 방식이 달라, 보호 전 사진부터 유효하게 매칭되는지를 우선 검증해야 한다. 보호 전후 매칭 성능은 아직 측정하지 않았다.

GitHub에는 **소스코드·빌드 스크립트·검증 문서만 반영**한다. FFV SDK 전체, 외부 DLL, 생성된 EXE, 등록 DB(`fingerprints.dat`, `users.dat`), 실제 지문 BMP/PNG와 개인 식별 정보는 커밋하지 않는다. 지문 원본은 접근이 제한된 환경에 보관한다.

작성: 최승빈 · 2026-10-12 · 센서·측정 도구 담당
