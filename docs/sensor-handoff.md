# BlurFing 센서 파트 인수인계
기준일: 2026-09-28 · 전달: 이봉헌 → 최승빈

범위: GitHub 구현, 센서·SDK 조사, 준비된 로컬 프로그램, 설치 순서, 남은 실장비 검증

## 1. 먼저 알아야 할 내용

**최승빈 담당은 Windows에서 센서 지문 영상을 얻고, 취득 품질과 오류를 확인하며, AI 담당과 측정 도구를 연결하는 일이다.** 이봉헌은 Android와 시스템 통합을 담당하며, 이번에 센서 수집 프로그램과 SDK 조사까지 사전 준비했다.

현재 대화 기준 **센서는 아직 구매하지 않았다.** 실물 연결·지문 취득·BMP 저장·매칭 실험에 성공한 상태가 아니다. 예전 문의 메일의 “구매했다”는 문구는 실제 구매 상태와 달랐으므로 추가 문의에서는 미구매임을 정정한다.

우선 준비할 경로는 **공식 Xperix 드라이버 + Neurotechnology의 무료 FFV SDK + FFV 저장 확장 소스**다. FFV의 공식 지원 목록에 BioMini Slim 2가 있으나, 11번가 판매 제품의 정확한 하드웨어·펌웨어 조합에서 동작하는지는 확인이 필요하다. [FFV 지원 장치 목록](https://www.neurotechnology.com/cgi-bin/fingerprint-scanners-ffv.cgi)

**지원 장치에 맞는 드라이버·SDK·프로그램을 갖추면 정상적인 취득 동작을 기대할 근거가 있다.** 지금의 “미검증”은 실물을 아직 시험하지 않았다는 의미다. 11번가 제품이 별도로 잠겨 있거나 FFV에서 동작하지 않는다는 증거를 확인한 것은 아니다. 먼저 공식 샘플의 취득과 준비한 확장의 이미지 저장을 확인한다. FFV 경로가 필요한 기능을 충족하면 이미지 취득 목적으로 제조사 유료 SDK를 별도 구매할 필요는 없을 수 있다.

| 구분 | 현재 상태 | 다음 담당 작업 |
|---|---|---|
| 센서 구매 | 미구매 | 판매 제품의 정확한 모델과 FFV 호환 여부 확인 |
| GitHub 센서 프로그램 | 코드·합성 영상 테스트 준비 완료 | 정식 제조사 SDK 확보 시 실제 장치 연동 검증 |
| 공식 드라이버 | 봉헌 PC에는 설치·드라이버 등록 확인 | 승빈 PC에 설치하고 실물 연결 후 장치 인식 확인 |
| 무료 FFV 저장 확장 | 봉헌 PC에서 빌드·스캐너 선택 화면 확인, 준비 소스를 GitHub에 공유 | 공식 SDK 전체 다운로드 후 센서 취득·저장 검증 |
| 해외 BioMini SDK 설치파일 | 다운로드·정적 정보 및 백신 검사만 수행 | 실행 보류. 이 패키지에 포함하지 않음 |
| 원본/보호 후 지문 점수 비교 | 평가 엔진·실험 연결 미완료 | 유재윤과 비교 조건·엔진을 정하고 실제 측정 |

이 문서는 9월 22일에 작성된 GitHub 센서 README 이후의 조사도 반영한다. README의 “공개 SDK를 찾지 못했다”는 문구는 당시 확인 결과다. 이후 해외 공개 설치파일과 별도의 무료 FFV SDK를 찾았으나, 각각 안전성·라이선스·기능 범위를 구분해야 한다.

## 2. 무엇을 다운로드해야 하나

| 순서 | 다운로드 | 목적·설치 조건 |
|---|---|---|
| 1 | [Xperix 공식 Windows 드라이버 안내](https://tech.xperix.com/en/support/solutions/articles/69000857511--device-driver-biomini-windows) · [Fingerprint_Driver.exe 첨부](https://tech.xperix.com/helpdesk/attachments/69121545640) | 센서의 Windows 연결용. 이것만 설치한다고 이미지 저장 앱이나 개발 SDK가 생기지는 않는다. |
| 2 | [Neurotechnology 공식 다운로드 페이지](https://www.neurotechnology.com/download.html) · [FFV 3.1 SDK ZIP](https://download.neurotechnology.com/FreeFingerprintVerification_3_1_SDK_2026-03-30.zip) | 무료 FFV 경로에 필요. ZIP을 완전히 내려받고 전체 폴더를 압축 해제한다. |
| 3 | [sensor/ffv-extension](../sensor/ffv-extension/README.md) | 봉헌이 준비한 이미지 저장 확장 소스와 빌드 스크립트. 공식 SDK 파일은 따로 받는다. |
| 조건부 | [.NET Framework 4.8](https://dotnet.microsoft.com/en-us/download/dotnet-framework/net48) | FFV 확장 프로그램용. 이미 4.8/4.8.1 환경이면 중복 설치할 필요가 없다. |
| 개발 시 | [Git for Windows](https://git-scm.com/downloads) + [BlurFing 저장소](https://github.com/kara320090/BlurFing) | 팀 코드 받기·변경 기록. 저장소가 비공개이므로 팀원 계정의 접근 권한이 필요하다. |
| GitHub 센서 앱 빌드 시 | [.NET 10 SDK, Windows x64](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | GitHub의 `BlurFing.SensorCapture` 빌드용. FFV 확장과 서로 다른 .NET 환경이다. |
| SDK에서 요구할 때 | [Microsoft Visual C++ 재배포 패키지](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170) | 해당 SDK 문서·오류 메시지가 요구하는 버전과 비트 수로 설치한다. 임의 DLL 다운로드 사이트는 사용하지 않는다. |

**현재 봉헌 PC에 있는 FFV ZIP은 미완성 다운로드다.** 파일명은 `FreeFingerprintVerification_3_1_SDK_2026-03-30.zip`이지만 크기는 2,715,648바이트뿐이다. 조사 당시 전체 배포 파일은 370,771,627바이트(약 354 MiB)였다. 일부 필요한 파일만 별도로 확보해 로컬 확인을 진행했으므로, 그 ZIP을 그대로 전달하거나 정상 전체 SDK로 사용하면 안 된다. 공식 링크에서 전체 파일을 새로 받는다. 파일 크기는 누락 확인용이며 무결성 인증을 대신하지 않는다.

센서 Windows 확인만 진행할 때 Android Studio·클라우드 GPU·API 시연 서버는 필요하지 않다. 제조사 유료 SDK 구매도 FFV 가능성을 확인하기 전에 이미 필요하다고 확정하지 않는다.

## 3. 준비된 프로그램 두 개를 구분하기

| 항목 | BlurFing.SensorCapture | BlurFingFfvCapture |
|---|---|---|
| 기반 | Xperix BioMini SDK의 UFS API | Neurotechnology FFV의 Nffv API와 공식 C# 샘플 |
| 위치 | `sensor/BlurFing.SensorCapture/` | `sensor/ffv-extension/` |
| 실제 취득에 필요한 것 | 사용 권한이 확인된 제조사 SDK와 센서 | 공식 FFV SDK 전체, 드라이버, 호환 센서 |
| 개발 환경 | .NET 10 / Windows Forms | .NET Framework 4.8 / Windows Forms |
| 저장 | BMP·PNG·metadata.json | 공식 샘플이 제공한 Bitmap을 BMP 또는 PNG로 저장 |
| 장치 없이 확인한 범위 | 합성 영상, 저장·오류 처리, 빌드 | 빌드, 스캐너 모듈 열거·선택 화면 |
| 미확인 | 실제 SDK ABI와 실장비 취득 | 실제 장치 열기·등록·Bitmap 취득·저장 |
| 중요한 한계 | 제조사 SDK 없이 실제 센서 취득 불가 | 이미지 파일을 입력받아 보호 전후를 비교하는 평가 엔진으로 쓸 수 없음 |

FFV는 무료로 제공되는 별도 제품이며, 라이선스 조건을 따른다. 저장 템플릿 수는 10개이고, 스캐너 입력의 1:1 검증을 지원한다. 임의 이미지 파일 입력과 1:N 식별 기능은 제공하지 않는다. [기능 범위](https://www.neurotechnology.com/free-fingerprint-verification-sdk.html), [라이선스 안내](https://www.neurotechnology.com/licensing_ffv_sdk.html)

FFV 패키지 안의 `UFScanner.dll` 하나를 GitHub의 UFS 앱에 옮겨 넣어 같은 방식으로 사용할 수 있다고 가정하지 않는다. FFV 경로에서는 제공된 모듈·라이브러리 구조와 Nffv API를 유지한다.

## 4. 승빈 PC에서 먼저 할 일: FFV 경로

대상 환경은 Windows 10/11 x64다. 상세 폴더 구성과 명령은 [FFV 확장 README](../sensor/ffv-extension/README.md)에 있다.

1. 공식 드라이버를 받아 설치한다.
2. 공식 FFV 전체 ZIP을 받고 압축을 푼다. 동봉 확장 소스 옆에 SDK 루트 폴더를 놓는다.
3. `.NET Framework 4.8` 환경을 확인하고 `sensor/ffv-extension/build-capture.ps1`의 내용을 확인한 뒤 빌드한다. SDK를 저장소 밖에 두었다면 `-SdkRoot`로 실제 경로를 지정한다.
4. 실물 센서를 확보하면 USB로 연결하고 Windows 장치 관리자에서 모델·드라이버·오류 여부를 기록한다.
5. 먼저 SDK의 공식 `CSharpSample.exe`에서 장치가 열리는지 확인한다. 그다음 같은 폴더의 `BlurFingFfvCapture.exe`를 실행한다.
6. 스캐너 선택 화면에서 `SupremaBioMini` 모듈과 연결된 장치를 확인한다. 모듈 이름이 목록에 뜨는 것만으로 장치 연결 성공으로 판단하지 않는다.
7. 동의를 받은 참여자에게 익명 ID를 부여하고 `Enroll`을 진행한다. 이번 취득이 성공하여 새 이미지가 표시되었는지 확인한 뒤 `Save BMP / PNG`로 저장한다.
8. 파일이 다시 열리는지, 크기·비트 수·선명도·ID가 맞는지 확인한다. 같은 조건에서 반복 취득하고 실패·재시도도 기록한다.

현재 확장은 공식 샘플의 `TemplateCreated` 성공 경로에서 표시되는 `GetBitmap()` 결과를 저장한다. 화면 캡처나 미리보기 크기 변경을 해서 저장하는 방식은 아니지만, 하드웨어 RAW 바이트를 그대로 보존한다고 검증한 것도 아니다. 낮은 품질 등으로 등록이 실패하면 저장할 이미지가 제공되지 않을 수 있다. 실패 후 남아 있는 이전 미리보기를 새 취득으로 기록하지 않는다.

기본 데이터 폴더:

```text
%LOCALAPPDATA%\BlurFing\FFVCapture
  fingerprints.dat  — 등록 템플릿 DB
  users.dat         — 샘플 사용자 DB
  startup.log       — 시작 단계·오류 기록
```

이미지 저장 위치는 저장 대화상자에서 선택한다. 현재 확장에는 자동 측정 CSV·품질 기록·일괄 저장·UFS 앱과 동일한 metadata.json 기능이 없다. 저장소의 CSV 템플릿은 사람이 기록을 시작하기 위한 제안 양식이다.

## 5. GitHub에서 이미 준비된 작업

저장소: [kara320090/BlurFing](https://github.com/kara320090/BlurFing) · **비공개 / main**

인수인계 정리를 시작한 코드 기준은 `3588e3bf135182d9a27426a7d4b22bfe10e13b50`이다. 당시 로컬과 origin/main이 일치했고 미커밋 변경은 없었다. 아래 main 링크에는 이번 인수인계 추가와 이후 변경도 반영된다.

센서 준비 구현 커밋: [db9643a](https://github.com/kara320090/BlurFing/commit/db9643a)

| 확인할 위치 | 내용 |
|---|---|
| [sensor/README.md](https://github.com/kara320090/BlurFing/blob/main/sensor/README.md) | 제조사 SDK 경로, 빌드, 저장, 실장비 확인 절차 |
| [NativeBioMini.cs](https://github.com/kara320090/BlurFing/blob/main/sensor/BlurFing.SensorCapture/NativeBioMini.cs) | UFS 초기화·장치 조회·단일 취득·BMP 저장·종료 어댑터 |
| [MainForm.cs](https://github.com/kara320090/BlurFing/blob/main/sensor/BlurFing.SensorCapture/MainForm.cs) | 장치 확인, 동의 체크, 익명 ID, 취득·미리보기·저장 화면 |
| [CaptureWorker.cs](https://github.com/kara320090/BlurFing/blob/main/sensor/BlurFing.SensorCapture/CaptureWorker.cs) | SDK 호출 프로세스, 취소·시간 초과 처리 |
| [CaptureFrame.cs](https://github.com/kara320090/BlurFing/blob/main/sensor/BlurFing.SensorCapture/CaptureFrame.cs) | 이미지·출처·저장 결과 관리 |
| [검사 프로그램](https://github.com/kara320090/BlurFing/blob/main/sensor/BlurFing.SensorCapture.Checks/Program.cs) | 합성·오류 경로 검사 |
| [9월 22일 센서 작업 기록](https://github.com/kara320090/BlurFing/blob/main/docs/worklogs/2026-09-22-이봉헌-sensor.md) | 구현·검증·미검증 범위 |
| [evaluation/](https://github.com/kara320090/BlurFing/tree/main/evaluation) | 평가 도구를 연결할 위치. 현재 실행 가능한 평가 구현은 없음 |
| [요구사항](https://github.com/kara320090/BlurFing/blob/main/docs/requirements.md) · [구조](https://github.com/kara320090/BlurFing/blob/main/docs/architecture.md) · [API 계약](https://github.com/kara320090/BlurFing/blob/main/contracts/protection-api.md) | 프로젝트 목표와 각 파트 연결 기준 |

기존 작업 기록상 합성·오류 처리 검사 **16/16 통과**, x64/x86 게시 빌드, x64 UI의 합성 미리보기·저장을 확인했다. 이번 인수인계 문서 작성 중 다시 실행한 하드웨어 시험 결과는 아니다.

UFS 앱에 준비된 기능:

- 같은 비트 수의 `UFScanner.dll` 선택, 장치 수·장치 번호 확인.
- 단일 취득, 기본 20초 제한, 취소, SDK 자식 프로세스 분리.
- 새 취득·실패 시 이전 이미지를 새 결과처럼 재사용하지 않는 처리.
- `SENSOR_...` 또는 `SYNTHETIC_...` 새 폴더에 BMP·PNG·metadata.json 저장.
- 익명 ID, 출처, 합성 여부, UTC 시각, 이미지 크기, 장치 번호, BMP SHA-256 기록.
- 실제 DPI·품질·일치율·확률을 임의로 생성하지 않음.

기본 저장 위치는 `%LOCALAPPDATA%\BlurFing\Captures`다. 제조사 SDK를 확보하면 공식 샘플부터 동작시키고, 받은 SDK의 함수 시그니처·호출 규약·비트 수를 어댑터와 대조한다.

GitHub 센서 앱을 개발할 때 저장소 루트에서:

```powershell
dotnet run --project sensor/BlurFing.SensorCapture.Checks -c Release
dotnet publish sensor/BlurFing.SensorCapture -c Release -r win-x64 --self-contained true -o artifacts/sensor/win-x64 -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false
```

자체 포함으로 게시한 실행파일은 실행 PC에 .NET 10을 따로 설치하지 않아도 된다. 빌드에는 SDK가 필요하다. x86 제조사 SDK를 받은 경우 앱 게시 대상도 x86로 맞춘다.

**FFV 확장 소스는 이번 인수인계와 함께 `sensor/ffv-extension/`에 공유한다.** 기존 로컬 C# 소스를 옮기고 빌드 스크립트에 외부 SDK 경로 지정·필수 파일 확인을 추가했다. 제조사·Neurotechnology SDK나 실행파일은 저장소에 포함하지 않는다. 새 검증 결과는 [9월 28일 인수인계 작업 기록](worklogs/2026-09-28-이봉헌-sensor-handoff.md)에 구분한다.

## 6. 제조사·판매처 조사 및 연락 현황

### Xperix 답변

봉헌이 공유한 전동훈 수석의 회신 기준:

- 개발 용도 BioMini Slim 2 구매는 Xperix를 통해 진행하라고 안내했다.
- 다른 판매 사이트의 제품은 Suprema 출입통제 장비의 지문 등록용이라고 설명했다.
- 이미 구매했다면 제품 하단의 SN을 요청했다. 현재는 미구매이므로 제공할 SN이 없다.
- 원하는 SDK 기능은 지원하지만, 이미지 저장 전용 모듈이나 대학 교육용 모듈은 별도로 제공하지 않는다고 답했다.
- **SDK 견적은 1,500,000원, 부가세 별도**다. 센서 본체 가격·포함 여부는 별도 확인 대상이다.
- 문의: 전동훈 수석 `dhjeon@xperix.com`, 대표번호 `1588-8817`.

공식 SDK 페이지도 구매가 필요한 제품으로 안내한다. 공개 무료 드라이버와 유료 BioMini SDK는 구분한다. [Xperix SDK 안내](https://www.xperix.com/products/developer/sdks)

### 구매 후보와 아직 확인할 내용

| 대상 | 조사 내용 | 연락·확인 상태 |
|---|---|---|
| [11번가 판매 페이지](https://www.11st.co.kr/products/9384470669) / 판매자 휴노텍 | BioMini Slim 2 지문 등록기 판매 후보. SDK 포함·BMP 취득·FFV 호환 보장은 확인되지 않음 | 봉헌이 구매처에 물었으나 모른다는 답을 받았다고 전달함. 이 문서 작업에서 추가 문의를 보내지는 않음 |
| [사용자가 처음 제시한 11번가 가격비교 링크](https://catalog.11st.co.kr/pc/507179300?sortCds=DLV_INCLUDE&poc=pc) | 판매 후보를 찾은 출발점 | 실제 주문할 판매 페이지·제품 사양을 다시 확인할 필요 |
| [Xperix 제품 페이지](https://www.xperix.com/products/biomini-slim-2) / [문의](https://www.xperix.com/company/contact-us) | 공식 제품 정보와 문의 구매 경로. 조사에서 바로 결제하는 장바구니 페이지는 찾지 못함 | 제조사 연락·회신 있음. 센서 가격과 개발 용도 공급 조건은 추가 확인 필요 |
| [Suprema 고객지원](https://www.supremainc.com/ko/support/main.asp) | 출입통제 제품과 등록 용도 관련 확인 창구 | 별도 메일·문의 발송 완료로 확인된 기록 없음 |
| Neurotechnology | FFV의 개발사. BioMini Slim 2 지원 목록 확인 | 정확한 판매 제품·펌웨어의 호환성을 문의한 기록 없음 |

실제로 회사 회신을 받은 대상은 Xperix다. Suprema나 다른 판매처에도 이미 메일을 보냈다고 가정하지 않는다. 이번 작업에서 추가 이메일이나 문의 양식은 발송하지 않았다.

판매처에 확인할 질문:

1. 이 상품의 정확한 제조사·모델·하드웨어 또는 펌웨어 버전은 무엇인가?
2. Windows PC의 일반적인 이미지 취득 용도로 사용할 수 있는가? 특정 출입통제 환경 전용 구성인가?
3. Neurotechnology FFV 3.1과 호환되는지, 실제 확인 자료나 평가 방법이 있는가?
4. 드라이버 외에 제공되는 프로그램·SDK·라이선스가 있는가? BMP 또는 PNG 저장이 가능한가?
5. 호환성 확인이 안 된 경우 구매 전 시험 또는 개봉·설치 후 반품 조건은 무엇인가?

공식 BioMini Slim 2 사양에는 USB 2.0 High Speed, 500 ppi, 300×400, 8비트 회색조가 기재되어 있다. USB 연결 장치라는 점과 연구용 프로그램이 작동한다는 점은 별도로 확인한다. 아직 팀이 실측한 사양은 아니다. [제품 사양](https://www.xperix.com/products/biomini-slim-2)

### Suprema SDK와 해외 다운로드 조사

Suprema BioStar 2 SDK는 출입통제 연동용이다. BioMini 이미지 취득 SDK 전체를 무료로 제공한다는 의미가 아니다. 공식 BioMini 연동 예제도 `without_UFScanner` 형태로 제공되며 해당 라이브러리는 별도 확보 대상이다. [Suprema BioMini/BioStar 2 연동 예제 안내](https://support.supremainc.com/en/support/solutions/articles/24000051129--biostar-2-sdk-fingerprint-from-biomini-and-transfer-it-to-the-device)

영문 검색에서는 실제 다운로드 배포 페이지도 찾았다:

- [SmartID Vietnam의 BioMini SDK 배포 페이지](https://smartid.com.vn/download-sdk-dau-doc-van-tay-usb-suprema-biomini-slim2-2s-3.html): Windows `Setup_BioMini_SDK_3.11.0.466.exe`, Linux `BioMini_SDK_for_Linux_v3.9.1.279.tar.gz` 링크를 확인했다. 무료 사용 권한·제조사 원본 여부·11번가 제품 호환을 확인한 것은 아니다. Windows 파일의 검사 결과는 아래와 같아 실행 대상에서 제외했다.
- [HTSAXON의 영문 SDK 영상](https://www.youtube.com/watch?v=TEhdwVJ67wk): 설명란의 [HTS 게시물](https://hts.com.pk/blogs/view/13)을 확인했으나, 조사 시 직접 접속 문제가 있었다. 영상이 존재한다는 사실만으로 배포 파일의 신뢰성이나 라이선스가 보장되지는 않는다.
- `python-biomini` 같은 래퍼나 구형 BioMini용 비공식 프로젝트는 Slim 2용 공식 SDK 전체를 대신하는 것으로 확인되지 않았다.

## 7. 해외 SDK 설치파일 검사 결과 — 실행 보류

대상: `Setup_BioMini_SDK_3.11.0.466.exe`

파일 크기: 122,524,288바이트

SHA-256:

```text
DD7B9C2254779290660EE89258CEEFF2C7F740281CCD4314B54D4B4EBB608F22
```

| 확인 항목 | 결과 |
|---|---|
| 설치·실행 | 하지 않음 |
| 디지털 서명 | Authenticode NotSigned |
| 파일 메타데이터 | Xperix Inc., 버전 3.11.0 표기. 진품 인증 근거로는 부족 |
| 2026-09-28 로컬 Microsoft Defender | 지정 파일 검사에서 위협 미탐지, 종료 코드 0 |
| Defender 서명 | 1.459.437.0 |
| VirusTotal 기존 해시 조회 | 1/55, Bkav Pro: W32.AIDetectMalware |
| VirusTotal 분석 시점 | 2024-07-14 16:26:05 KST. 현재 재검사 결과가 아님 |
| VirusTotal 업로드·재분석 | 하지 않음. 기존 동일 해시 보고서만 조회 |

[기존 VirusTotal 결과](https://www.virustotal.com/gui/file/dd7b9c2254779290660ee89258ceeff2c7f740281ccd4314b54d4b4ebb608f22)

**멀웨어로 확정한 것도, 안전한 파일로 판정한 것도 아니다.** 과거 한 엔진 탐지는 오탐일 수 있으나 단정할 근거가 없다. 제조사 원본·동일 버전 해시와 대조하지 못했으므로 팀원에게 실행을 맡기지 않는다. Google Drive의 “파일이 커서 바이러스 검사를 할 수 없다”는 안내 자체는 감염 판정이 아니다. 파일 삭제 완료 여부는 이 문서에서 확인하지 않았다.

공식 드라이버의 경우 별개의 파일이다. 봉헌 PC에 준비한 `Fingerprint_Driver.exe`의 SHA-256은 아래와 같다. 설치 EXE는 서명이 없었으나, 설치된 `sfr500.cat` 카탈로그는 유효한 Microsoft Windows Hardware Compatibility Publisher 서명으로 확인했다. 이 사실이 해외 SDK 설치파일의 신뢰성을 보증하지는 않는다.

```text
62A863123450BCCDE63DA7501C3102B9D4E63F01639260E3FDFA2436E0B0FC5D
```

## 8. 담당별 연결과 남은 실험

| 담당 | 이어서 맡을 범위 |
|---|---|
| 최승빈 — 센서·측정 도구 | 드라이버·장치 연결, SDK 호환 확인, 참조 영상 취득, 저장 품질·오류·반복성 확인, 측정 기록 도구 |
| 유재윤 — AI | 보호 알고리즘, 사용할 비교 엔진과 점수 해석, 보호 전후 성능 실험 설계 |
| 정회서 — 데이터·지문 영역 | 동의 기반 데이터와 익명 ID, 손끝·지문 ROI, 입력 자료 정리 |
| 한윤섭 — 백엔드 | 이미지 처리 API, 처리 상태·오류·평가 결과 전달 계약 |
| 이봉헌 — Android·통합 | 사진 선택/촬영 흐름, API 연동, 보호 전후 표시·저장, 각 파트 공동 통합 확인 |

현재 서비스 흐름은 **Android → 백엔드 → ROI/AI 처리**다. 센서는 Windows에서 연구용 참조 지문을 취득하는 별도 경로다. Android에 센서를 USB로 바로 연결하는 기능이나 센서 점수를 앱에 자동 반영하는 전체 흐름은 아직 완성되지 않았다.

센서 담당과 AI 담당이 먼저 합의할 사항:

- 어떤 비교 엔진·버전으로 어떤 점수를 얻을 것인지.
- 동일인의 센서 참조 영상과 사진 지문을 보호 전에도 비교할 수 있는지.
- 사진의 ROI·회전·크기·해상도·압축 조건을 어떻게 맞출 것인지.
- 원본부터 매칭되지 않는 경우를 보호 성공으로 세지 않는 기준.
- 취득 실패·비교 실패·점수 감소·처리 시간을 각각 어떻게 기록할 것인지.

센서 참조 영상과 일반 사진은 취득 조건이 다르므로, 먼저 **보호 전 원본의 비교 가능성**을 검증한다. 원시 매칭 점수를 근거 없이 “몇 % 일치”나 “도용 성공 확률”로 바꾸지 않는다. FFV만으로 사진 파일 두 장을 넣어 전후 비교하는 기능을 구현할 수 있다고 계획하지 않는다.

[취득 기록 양식](../sensor/templates/capture-log.csv)과 [비교 기록 양식](../evaluation/templates/comparison-log.csv)은 **미측정 상태의 헤더만 있는 제안 양식**이다. 현재 앱이 자동 생성하는 파일이나 확정된 API 계약이 아니다. 점수·엔진·수치가 없으면 비워 두고 실패 사유를 남긴다. 시각은 UTC, 시간은 ms로 기록하며, `baseline_valid`는 보호 전 원본의 비교 가능 여부다. 이 양식을 채운 실제 측정 자료는 별도 비공개 실험 위치에 둔다.

## 9. 승빈이 다음에 제출하면 되는 결과

아래 항목은 모두 이후 확인할 작업이며 완료 표시가 아니다.

- [ ] 구매 후보의 정확한 제품 구성과 사용 조건 확인.
- [ ] 승빈 PC의 OS·드라이버·SDK 버전과 설치 경로 기록.
- [ ] 공식 FFV 전체 패키지 확보, 확장 빌드, 시작 화면 확인.
- [ ] 실물 USB 연결 후 장치 인식 및 실제 스캐너 열기 확인.
- [ ] 동의된 익명 참여자 영상 취득, BMP/PNG 파일 재열기와 속성 확인.
- [ ] 반복 취득 및 실패 기록. 가능한 경우 시간 초과·취소·USB 분리·재연결 후 복구 확인.
- [ ] 사용 중인 프로그램에서 실패 후 오래된 이미지가 새 결과로 저장되는지 확인.
- [ ] 유재윤과 엔진·비교 조건 합의, 원본의 비교 가능성 검증.
- [ ] 설치 방법·오류 재현 절차·수정 코드·검증 결과를 본인 작업으로 기록.

우선 한 번의 실제 취득·저장을 통과시키고, 그다음 반복 측정과 평가 연결을 진행한다. **7주차인 2026-10-16까지 산출물을 완성하고 8주차 발표**에 사용한다. 일정·예산을 이번 인수인계에서 변경하지 않았다.

## 10. GitHub 작업 및 데이터 전달

처음 받는 경우:

```powershell
git clone https://github.com/kara320090/BlurFing.git
cd BlurFing
git status
```

기존 작업 폴더는 미커밋 변경을 먼저 확인하고, 작업 트리가 깨끗하면 `git pull --ff-only origin main`으로 동기화한다. 팀의 기본 대상은 main이다. 동기화 실패나 충돌이 있으면 강제 덮어쓰기하지 않고 상대 변경과 함께 확인한다.

구현한 코드, 설치 문서, 익명화한 검증 기록을 실제 수행한 날짜·작성자로 의미 있는 단위로 커밋한다. 푸시 전 원격 변경을 다시 확인한다. 상세 규칙은 [AGENTS.md](https://github.com/kara320090/BlurFing/blob/main/AGENTS.md), [main 작업 방식](https://github.com/kara320090/BlurFing/blob/main/docs/main-workflow.md)을 따른다.

실제 지문 영상·템플릿 DB·이름·학번·동의서·SDK 바이너리·라이선스 키는 커밋하지 않는다. 저장소가 비공개여도 동일하게 취급한다. 실험 자료는 동의 범위와 접근 권한을 정한 별도 위치에서 공유하고, 코드 검증에는 합성 자료를 사용한다.

이번 GitHub 공유 범위는 문서, 준비된 확장 소스·빌드 스크립트, 빈 측정 양식이다. 팀원에게 전달할 짧은 안내는 [메시지 초안](sensor-handoff-message.txt)에 있다. 기존 로컬 전달 ZIP은 작성 당시 스냅샷이므로 이후 수정 내용은 이 저장소를 기준으로 확인한다.
