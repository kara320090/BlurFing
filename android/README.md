# BlurFing Android App

주담당: 이봉헌 (Android 앱 개발 및 시스템 통합, 팀장)

SNS 사진 속 손가락 지문 노출을 줄이는 Android 보호 앱 프로젝트입니다.
정지 사진 입력 → 손끝 영역 확인·수정 → 보호 설정 → 처리 → 전후 비교 → 보호 사본 저장의 전체 흐름을 제공합니다.

---

## 1. 아키텍처 및 모듈 구성

- **UI 프레임워크**: Jetpack Compose (Material3)
- **상태 관리**: ViewModel, StateFlow, Coroutines
- **네트워크 / 직렬화**: OkHttp3, Kotlinx Serialization
- **이미지 및 EXIF**: Coil, AndroidX ExifInterface
- **저장소 패턴**:
  - `ProtectionRepository` 인터페이스를 통해 `MockProtectionRepository`(기본값, 독립 실행 및 UI 개발용)와 `ApiProtectionRepository`(`contracts/protection-api.md` 연동용) 교체 가능
  - 보호 설정 화면에서 서버 처리와 서버 주소를 선택할 수 있습니다. `real` 응답은 서버 이미지를 사용하며 Mock만 로컬 프리뷰를 만듭니다.

### 패키지 구조 (`android/app/src/main/java/com/blurfing/app/`)
```
├── MainActivity.kt               # 화면 전환 네비게이션 및 진입점
├── model/
│   ├── NormalizedRegion.kt       # 0..1 상대 좌표 및 경계 검증 (BF-03)
│   └── ProtectionModels.kt       # 요청/응답 DTO 및 연구용 평가 메트릭 (BF-07)
├── repository/
│   ├── ProtectionRepository.kt   # 공통 인터페이스
│   ├── MockProtectionRepository.kt # 개발용 Mock 구현체 (취소 지원, MOCK_RESULT 명시)
│   └── ApiProtectionRepository.kt  # OkHttp 기반 백엔드 연동 어댑터 (BF-07)
├── ui/
│   ├── components/
│   │   └── FingertipOverlayCanvas.kt # 손끝 지문 패드 인터랙티브 오버레이 (BF-03)
│   ├── screens/
│   │   ├── ImagePickerScreen.kt      # 사진 선택·촬영 진입 및 오류 안내 (BF-01, BF-02)
│   │   ├── RegionEditorScreen.kt     # 손끝 영역 확인/수정 (BF-03)
│   │   ├── ProcessingScreen.kt       # 강도 설정 및 처리 진행/취소 (BF-04)
│   │   └── ComparisonScreen.kt       # 전후 비교 및 사본 저장 (BF-05, BF-06)
│   └── theme/                        # Material3 테마 및 색상
├── utils/
│   ├── CoordinateTransformer.kt  # 뷰 픽셀 ↔ 정규화 좌표 양방향 변환
│   ├── ExifNormalizer.kt         # EXIF 회전각 픽셀 반영 및 정규화
│   ├── SelectedImageLoader.kt    # 파일 용량·해상도 검사 후 동일 바이트에서 픽셀·EXIF 읽기
│   ├── CameraCapture.kt          # 촬영 전용 FileProvider·계약·임시 파일 관리
│   ├── ImageSaver.kt             # MediaStore Scoped Storage 사본 저장 (BF-06)
│   └── LocalBlurProcessor.kt     # 개발 프리뷰용 로컬 블러 (AI 성능 미주장)
└── viewmodel/
    ├── BlurFingViewModel.kt      # 전체 화면 상태 및 취소/재시도 제어
    └── CameraCaptureViewModel.kt # 촬영 대기 URI 저장·복원, 취소·실패 처리
```

---

## 2. 개발 환경 및 요구 사항

- **JDK**: Java 21 LTS 권장 (로컬 환경: `C:\Program Files\BlueJ\jdk` 확인)
- **Android SDK**: `C:\Users\soma\AppData\Local\Android\Sdk`
  - `compileSdk`: 35 (Android 15)
  - `minSdk`: 26 (Android 8.0 Oreo)
  - `targetSdk`: 35
- **빌드 도구**: Gradle 8.9+, Android Gradle Plugin 8.7.0

---

## 3. 실행 및 빌드 방법

### Android Studio에서 실행
1. Android Studio를 실행하고 `android/` 폴더를 프로젝트로 엽니다.
2. Gradle 동기화(Sync)가 완료되면 에뮬레이터(`Medium_Phone` 등) 또는 실물 기기를 선택합니다.
3. `Run 'app'` (Shift + F10)을 실행합니다.

### 터미널에서 빌드 및 테스트
```powershell
# 디버그 APK 빌드
./gradlew assembleDebug --max-workers=4

# 단위 테스트 실행
./gradlew testDebugUnitTest --max-workers=4
```

---

## 4. 검증 결과 및 구분

2026-10-17: 사진 AI V2에서 저장하지 않은 결과의 종료 확인과 요청별 저장 완료 상태를 추가했습니다. Android 단위 **177개 중 176개 통과·1개 건너뜀**(비공개 사진이 필요한 선택 시험), 신규 `ExperimentalExitDeviceTest` **4개**와 기존 `BackNavigationDeviceTest` **3개** 에뮬레이터 시험이 통과했습니다. [종료 규칙](../docs/android-next-12-experimental-exit.md)과 [검증 기록](../docs/worklogs/2026-10-17-이봉헌-android-experimental-exit.md)을 따릅니다. 아래 내용은 이전 기능별 기록입니다.

2026-10-15: 시스템 뒤로가기와 처리 취소 확인을 연결했습니다. Android 단위 테스트 **136개**, 신규 `BackNavigationDeviceTest` 에뮬레이터 테스트 **3개** 및 debug·계측 APK 빌드가 통과했습니다. 초기 에뮬레이터 환경 문제와 재검증 결과는 [11번 검증 기록](../docs/worklogs/2026-10-15-이봉헌-android-back-navigation.md)에 구분해 기록했습니다. 아래 내용은 이전 기능별 검증 기록입니다.

최종 추가 작업에서는 단위 테스트 107개, 에뮬레이터 UI 5개, 팀 백엔드 직접 연결 4개를 통과했습니다. [설정·복원](../docs/android-session-recovery.md), [비교·평가](../docs/android-comparison.md), [기기 검증](../docs/android-device-verification.md), [백엔드 연결 재현](../docs/android-live-backend-checks.md), [실행 기록과 남은 범위](../docs/worklogs/2026-09-28-이봉헌-android-preparation.md)를 확인하세요. 아래 91개 결과는 카메라 기능 추가 시점의 기록입니다.

### 기본 카메라 앱을 이용한 촬영 (BF-02)

첫 화면의 `카메라로 사진 촬영`을 누르면 휴대폰의 카메라 앱이 열립니다. 촬영 결과는 앱 전용 캐시의 전체 이미지 파일로 받고, 기존 입력 제한과 EXIF 방향 보정을 적용한 뒤 영역 편집으로 이동합니다. 촬영을 취소하면 기존 화면을 유지하고, 카메라 앱 없음·실행 실패·빈 결과·읽기 실패에는 갤러리 선택 또는 재촬영을 안내합니다.

직접 카메라 하드웨어를 제어하는 기능은 아니므로 `CAMERA` 권한을 추가하지 않았습니다. `FileProvider`는 `cache/camera-captures/`만 노출하며 이번 출력 URI에만 임시 읽기·쓰기 권한을 전달합니다. 요청 URI는 `SavedStateHandle`에 보관하고 이미지 픽셀은 저장 상태 Bundle에 넣지 않습니다. 편집 중 사진·좌표 복원은 별도의 [임시 사본·저장 상태 기능](../docs/android-session-recovery.md)으로 지원합니다.

촬영 취소·실행 실패 시 임시 파일을 제거하고, 성공 시에는 이미지 읽기가 완료되거나 실패·취소된 뒤 제거합니다. 정상적인 앱 처리에서는 촬영 원본을 갤러리에 자동 등록하지 않습니다. 앱 비정상 종료로 남은 파일은 다음 카메라 ViewModel 초기화에서 24시간이 지난 앱 생성 파일만 정리하며 복원된 진행 중 요청은 보존합니다. 외부 카메라 앱 자체의 별도 저장 동작은 기기별 확인 대상입니다.

기기 확인 순서: 촬영 → 영역 편집 → Mock 처리 → 비교 → 보호 사본 저장. 촬영 취소, 카메라 앱 실행 실패, 촬영 중 화면 회전·앱 프로세스 재생성, 15MiB·2,000만 화소 제한 초과도 함께 확인합니다. 실제 스마트폰의 카메라 앱 호환성·시스템 결과 전달은 아직 검증하지 않았습니다.

2026-09-28 카메라 입력 추가 후 검증: JDK 21, Gradle 8.9, SDK 35에서 `testDebugUnitTest assembleDebug --max-workers=4` 통과. 테스트 **91개**(기존 76개 + 카메라 15개), 실패·오류·건너뜀 0개. 디버그 APK는 `app/build/outputs/apk/debug/app-debug.apk`에 생성됩니다. [카메라 작업·검증 기록](../docs/worklogs/2026-09-28-이봉헌-camera.md)

Windows 자동 테스트에서는 AndroidX FileProvider의 경로 구분자 차이 때문에 촬영 URI 발급·파일 I/O를 제어 가능한 테스트 구현으로 대체합니다. 앱의 실제 FileProvider 공유 범위는 Manifest·경로 XML로 검사하지만, 실제 카메라 앱에 대한 권한 전달·촬영은 기기 검증이 남아 있습니다.

Gradle Wrapper JAR를 저장소에 포함했고 Gradle 배포 ZIP의 SHA-256을 고정했습니다. 최초 실행은 빌드 도구와 테스트용 Android 런타임 다운로드로 시간이 걸릴 수 있습니다. 로컬 JDK 21을 `JAVA_HOME`에 설정하고 Android SDK 경로를 비공개 `local.properties`에 지정하세요.

### 실행 및 완료한 검증
- [x] **촬영 입력 (`CameraCaptureTest`, 15개)**: 촬영 전용 URI·Manifest·Intent, EXIF 보정 후 영역 편집, 중복 요청·취소·실행 실패·빈/손상 결과·상태 복원·임시 파일 정리·다른 파일 보호·기본 ViewModel 생성 검증
- [x] **상대 좌표 변환 및 경계 검증 (`NormalizedRegionTest`)**: 0.0 ~ 1.0 범위 초과 및 `x+w > 1`, `y+h > 1`에 대한 안전한 예외 발생 및 `safeCreate` 클램핑 확인
- [x] **종횡비 보정 및 좌표계 역변환 (`CoordinateTransformerTest`)**: Letterbox / Pillarbox 여백 계산 및 화면 터치 ↔ 원본 상대 좌표 간 정밀 변환 확인
- [x] **Mock 및 통신 실패 복구 (`ProtectionRepositoryTest`)**: Mock 결과 반환, 15MB 초과 파일 사전 차단, 사전/진행 중 요청 취소(`CancellationException`) 동작 확인
- [x] **평가 점수 무결성 (`EvaluationMetricsTest`)**: 미측정 수치가 null로 유지되어 가짜 일치율(0~100%)을 생성하지 않음을 확인
- [x] **HTTP 계약 (`ApiProtectionIntegrationTest`, 8개)**: multipart 요청, ID·응답 검증, 보호 API 404 후 재시도, 서버 오류·시간 초과·취소, 잘못된 강도 전송 차단
- [x] **서버 주소 (`BackendAddressTest`, 3개)**: 주소 정규화, 개발용 로컬 HTTP, HTTPS, 잘못된 주소 차단
- [x] **처리 이미지 (`ProtectedImageDecoderTest`, 4개)**: 서버 픽셀 사용, 원본 보존, 손상·누락·규격 불일치 거부, Mock 원본 recycle 회귀 검증
- [x] **앱 통합 상태 (`BlurFingViewModelIntegrationTest`, 5개)**: 합성 HTTP 응답 → 비교 상태, 사진·영역 유지 후 재시도, 초기화 후 늦은 응답 폐기, 중복 요청 차단, 서버 503·501·415 안내 후 로컬 Mock 전환
- [x] **저장 상태 (`ProtectedCopySaveTest`, 7개)**: 저장 실패 후 원본·처리본·영역 보존과 재시도, 중복 저장 차단, 저장 함수 예외 처리, 편집 화면의 이전 결과 저장 차단, 초기화·사진 교체·편집 복귀 뒤 늦은 완료 무시
- [x] **저장 I/O (`ImageSaverTest`, 10개)**: 제어 가능한 ContentProvider에서 PNG/JPEG 출력과 갤러리 등록, 등록 실패·생성 실패·정리 실패·취소 처리, SDK 28/29 저장 열 차이 확인
- [x] **저장 권한 (`SavePermissionTest`, 12개)**: SDK 26/28 권한 대기, 허용 후 동일 사본 1회 저장, 거부 후 상태 유지·재시도, 실제 권한 재확인, SDK 29의 기존 저장 권한 생략, 화면 이동·사진 교체·초기화·새 처리 후 오래된 응답 무시
- [x] **사진 입력 (`SelectedImageLoaderTest`, 10개)**: 정상 PNG, JPEG EXIF 회전, 용량·해상도 제한과 경계값, 손상 이미지, 내부 경로를 숨긴 오류 안내, 오류 후 재선택, 사진 선택 취소

사진 파일은 최대 15MiB(15 × 1024 × 1024바이트), 20,000,000픽셀까지 읽습니다. 픽셀을 할당하기 전에 해상도를 확인하며 임의로 축소하지 않습니다. 파일을 한 번 열어 제한된 양의 바이트만 읽고, 그 데이터에서 픽셀과 EXIF를 모두 해석합니다. 업로드할 때 다시 인코딩한 PNG의 15MiB 제한은 API 계층에서 별도로 검사합니다. 입력 제한이 모든 기기에서 메모리 부족을 방지한다는 뜻은 아니며 기기별 메모리 검증은 남아 있습니다.

저장 중에는 버튼에 진행 상태를 표시하고 다시 누를 수 없게 한다. 실패하면 비교 화면의 사진·영역을 유지하고 `사본 저장 다시 시도`를 제공한다. 화면 이동·사진 교체는 저장 작업의 화면 반영을 취소한다. 운영체제에서 이미 끝난 파일 쓰기를 되돌리거나 갤러리의 완성 파일을 삭제한다는 뜻은 아니다. 저장 상태 테스트는 주입한 저장 함수로 실패·지연을 재현하며, 별도로 에뮬레이터의 실제 MediaStore 사본 저장·원본 불변을 검증했다.

저장 I/O는 MediaStore 등록 결과가 1개일 때 성공으로 처리합니다. 실패·취소 시 이번 호출에서 생성한 미완성 항목만 삭제하고, 삭제 실패는 최초 오류와 함께 보존합니다. 입력·저장 테스트에는 합성 파일만 사용했고 실제 기기 권한 및 갤러리 동작을 검증한 것으로 간주하지 않습니다.

Android 8·9에서는 저장 버튼을 누를 때 `WRITE_EXTERNAL_STORAGE`를 확인합니다. 권한이 없으면 시스템 권한 창을 요청하고, 필요 시 목적 설명과 취소 버튼을 먼저 제공합니다. 허용 응답과 실제 권한을 확인한 뒤 요청한 사본을 한 번 저장합니다. 거부·취소해도 비교 상태를 유지하며 재시도 또는 앱 설정에서 권한 허용을 안내합니다. 사진 교체·편집 복귀·새 처리·초기화는 이전 권한 요청을 무효화합니다. Android 10 이상에서 앱 소유 미디어를 저장할 때는 이 권한 요청을 생략합니다.

이미지 테스트는 Robolectric의 Native Graphics 모드로 이미지 디코딩을 실행했습니다. 손상된 합성 이미지 테스트에서 출력되는 decoder 메시지는 의도한 실패 입력에 대한 로그입니다.

### 미실행 검증 (기기 및 서버 준비 후 진행 필요)
- [ ] **실제 휴대폰과 구형 권한 창**: 에뮬레이터의 화면·영역 추가/삭제·비교·설정 재생성·MediaStore 저장은 검증했습니다. 실제 휴대폰 카메라·갤러리 선택, Android 8·9 시스템 권한 창·회전 중 권한 응답은 별도 검증 대상입니다.
- [ ] **배포된 팀 서버와 실제 AI**: 로컬 팀 백엔드에 직접 연결해 503·no_regions·필수 입력 오류를 검증하고 합성 처리 함수를 주입해 성공 이미지 경로도 확인했습니다. 백엔드 자체 테스트 20개도 통과했습니다. 실제 AI가 미연결인 기본 서버는 503을 반환하며, 독립 배포 서버와 실모델 성공 처리는 아직 검증하지 않았습니다.
- [ ] **실제 AI·센서 평가**: 지문 보호 성능 및 센서 매칭 실측은 이번 앱 검증에 포함되지 않습니다.

[서버 주소 설정 및 연동 가이드](../docs/android-server-integration.md) · [2026-09-21 구현·검증 기록](../docs/worklogs/2026-09-21-이봉헌.md)

[2026-09-22 서버 오류 안내·Mock 전환 검증](../docs/worklogs/2026-09-22-이봉헌.md)

[2026-09-27 저장 오류 수정·팀원 변경 검토](../docs/worklogs/2026-09-27-이봉헌.md)

[2026-09-27 사진 입력·MediaStore 저장 보완 및 검증](../docs/worklogs/2026-09-27-이봉헌-입출력보완.md)

[2026-09-28 Android 8·9 저장 권한 및 오래된 권한 응답 처리](../docs/worklogs/2026-09-28-이봉헌.md)

[시스템 뒤로가기와 처리 취소 확인](../docs/android-next-11-back-navigation.md): 설정·비교 화면에서 편집으로 돌아가고, 처리 중에는 취소 여부를 확인합니다. 편집 화면에서 첫 화면으로 돌아가면 편집 복원용 임시 사본을 정리합니다.
