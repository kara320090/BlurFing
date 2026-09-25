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
│   │   ├── ImagePickerScreen.kt      # 사진 선택 및 오류 안내 (BF-01)
│   │   ├── RegionEditorScreen.kt     # 손끝 영역 확인/수정 (BF-03)
│   │   ├── ProcessingScreen.kt       # 강도 설정 및 처리 진행/취소 (BF-04)
│   │   └── ComparisonScreen.kt       # 전후 비교 및 사본 저장 (BF-05, BF-06)
│   └── theme/                        # Material3 테마 및 색상
├── utils/
│   ├── CoordinateTransformer.kt  # 뷰 픽셀 ↔ 정규화 좌표 양방향 변환
│   ├── ExifNormalizer.kt         # EXIF 회전각 픽셀 반영 및 정규화
│   ├── ImageSaver.kt             # MediaStore Scoped Storage 사본 저장 (BF-06)
│   └── LocalBlurProcessor.kt     # 개발 프리뷰용 로컬 블러 (AI 성능 미주장)
└── viewmodel/
    └── BlurFingViewModel.kt      # 전체 화면 상태 및 취소/재시도 제어
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

2026-09-27: JDK 21, Gradle 8.9, SDK 35에서 `testDebugUnitTest assembleDebug --max-workers=4` 통과. 테스트 **44개**, 실패·오류·건너뜀 0개. 디버그 APK는 `app/build/outputs/apk/debug/app-debug.apk`에 생성됩니다.

Gradle Wrapper JAR를 저장소에 포함했고 Gradle 배포 ZIP의 SHA-256을 고정했습니다. 최초 실행은 빌드 도구와 테스트용 Android 런타임 다운로드로 시간이 걸릴 수 있습니다. 로컬 JDK 21을 `JAVA_HOME`에 설정하고 Android SDK 경로를 비공개 `local.properties`에 지정하세요.

### 실행 및 완료한 검증
- [x] **상대 좌표 변환 및 경계 검증 (`NormalizedRegionTest`)**: 0.0 ~ 1.0 범위 초과 및 `x+w > 1`, `y+h > 1`에 대한 안전한 예외 발생 및 `safeCreate` 클램핑 확인
- [x] **종횡비 보정 및 좌표계 역변환 (`CoordinateTransformerTest`)**: Letterbox / Pillarbox 여백 계산 및 화면 터치 ↔ 원본 상대 좌표 간 정밀 변환 확인
- [x] **Mock 및 통신 실패 복구 (`ProtectionRepositoryTest`)**: Mock 결과 반환, 15MB 초과 파일 사전 차단, 사전/진행 중 요청 취소(`CancellationException`) 동작 확인
- [x] **평가 점수 무결성 (`EvaluationMetricsTest`)**: 미측정 수치가 null로 유지되어 가짜 일치율(0~100%)을 생성하지 않음을 확인
- [x] **HTTP 계약 (`ApiProtectionIntegrationTest`, 8개)**: multipart 요청, ID·응답 검증, 보호 API 404 후 재시도, 서버 오류·시간 초과·취소, 잘못된 강도 전송 차단
- [x] **서버 주소 (`BackendAddressTest`, 3개)**: 주소 정규화, 개발용 로컬 HTTP, HTTPS, 잘못된 주소 차단
- [x] **처리 이미지 (`ProtectedImageDecoderTest`, 4개)**: 서버 픽셀 사용, 원본 보존, 손상·누락·규격 불일치 거부, Mock 원본 recycle 회귀 검증
- [x] **앱 통합 상태 (`BlurFingViewModelIntegrationTest`, 5개)**: 합성 HTTP 응답 → 비교 상태, 사진·영역 유지 후 재시도, 초기화 후 늦은 응답 폐기, 중복 요청 차단, 서버 503·501·415 안내 후 로컬 Mock 전환
- [x] **저장 상태 (`ProtectedCopySaveTest`, 7개)**: 저장 실패 후 원본·처리본·영역 보존과 재시도, 중복 저장 차단, 저장 함수 예외 처리, 편집 화면의 이전 결과 저장 차단, 초기화·사진 교체·편집 복귀 뒤 늦은 완료 무시

저장 중에는 버튼에 진행 상태를 표시하고 다시 누를 수 없게 한다. 실패하면 비교 화면의 사진·영역을 유지하고 `사본 저장 다시 시도`를 제공한다. 화면 이동·사진 교체는 저장 작업의 화면 반영을 취소한다. 운영체제에서 이미 끝난 파일 쓰기를 되돌리거나 갤러리의 완성 파일을 삭제한다는 뜻은 아니다. 저장 상태 테스트는 주입한 저장 함수로 실패·지연을 재현하며 실제 MediaStore 저장 시험은 별도로 남아 있다.

이미지 테스트는 Robolectric의 Native Graphics 모드로 이미지 디코딩을 실행했습니다. 손상된 합성 이미지 테스트에서 출력되는 decoder 메시지는 의도한 실패 입력에 대한 로그입니다.

### 미실행 검증 (기기 및 서버 준비 후 진행 필요)
- [ ] **실제 기기/에뮬레이터 UI**: 사진 선택, 터치 편집, 비교 화면, MediaStore 저장은 이번 작업에서 실행하지 않았습니다.
- [ ] **팀 백엔드와의 이미지 처리 연동**: 서버는 이미지 검증·AI 모듈 연결 지점·결과 PNG 반환을 구현했습니다. AI 모듈은 미연결 상태여서 영역이 있는 요청에는 HTTP 503을 반환합니다. 앱 테스트는 MockWebServer로 오류를 재현했으며 백엔드 테스트 16개는 별도로 통과했습니다. 앱과 팀 서버를 직접 연결한 성공 처리는 미검증입니다.
- [ ] **실제 AI·센서 평가**: 지문 보호 성능 및 센서 매칭 실측은 이번 앱 검증에 포함되지 않습니다.

[서버 주소 설정 및 연동 가이드](../docs/android-server-integration.md) · [2026-09-21 구현·검증 기록](../docs/worklogs/2026-09-21-이봉헌.md)

[2026-09-22 서버 오류 안내·Mock 전환 검증](../docs/worklogs/2026-09-22-이봉헌.md)

[2026-09-27 저장 오류 수정·팀원 변경 검토](../docs/worklogs/2026-09-27-이봉헌.md)
