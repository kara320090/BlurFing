# 사진 AI 실험 연결

사진 선택 화면의 **사진 AI 보호 실험 (미승인)**에서 별도 화면을 연다. 기존 V1 Gaussian/mock 요청·결과·타임아웃은 변경하지 않는다. V12 학습 후보, V13 기하 후보, V14 손 자세 후보를 명시적으로 선택하며 다른 엔진이나 mock으로 자동 전환하지 않는다.

`POST /v2/photo/protect` multipart는 `image`, `request_id`, `method`, `scope=automatic_photo`, `strength=0.5`만 전송한다. `method`는 `photo_native_v12_experimental`, `photo_distal_v13_geometry_experimental`, `photo_pose_v14_geometry_experimental` 중 하나다. V2 서버를 별도로 구성해야 한다.

입력은 방향 보정·불투명 RGB 정규화 후 무손실 PNG로 만든다. 투명 입력은 흰 배경에 합성한다. JPEG 재인코딩이나 원본 축소는 하지 않는다. 15MiB/2,000만 화소 상한과 실제 예상 메모리 예산을 넘으면 원본 파일을 유지하고 거절한다. 업로드 객체는 PNG와 작은 미리보기만 보관하며 전체 원본 Bitmap은 유지하지 않는다.

갤러리 입력의 색상 프로필은 BitmapFactory에서 sRGB로 정상화한다. 이후 canonical HTTP PNG는 sRGB8 픽셀과 색상 메타데이터가 없는 파일이다. 허용 chunk는 IHDR, 선택적 orientation1-only 26바이트 eXIf, 연속 IDAT, IEND뿐이다. iCCP/gAMA/sRGB 등 색상 chunk나 다른 ancillary는 source·return·mask 모두 거절한다. 프로필 제거만으로 색상 변환을 대체하지 않는다. 서로 다른 색상 변환 엔진의 정수 RGB 결과가 항상 같다고 가정하지 않으며, 픽셀 보존은 정상화된 업로드 PNG를 기준으로 검증한다.

응답은 request/source bytes/RGB/engine/method/EXIF1·크기·미승인 플래그를 확인한다. PNG CRC·형식·압축 스트림 끝과 A/R binary 마스크 해시·픽셀 수·겹침을 검사하고, 원본/반환 PNG의 행을 비교해 실제 변경 C가 A 안에만 있는지 확인한다. 사각형은 마스크를 생성하는 데 사용하지 않는다. 개별 후보 hash는 서버가 원래 labelmap으로 검증하며, 앱은 전송된 A/R 합집합 마스크를 독립 검증한다.

`success`는 검출된 후보가 변환되었다는 뜻이다. 검출 누락이나 전체 지문 보호를 보장하지 않는다. `partial_success`/`rejected`에는 원본 지문이 남을 수 있다는 안내를 유지한다. 변경된 결과만 별도 PNG로 저장하며, 저장 뒤 provider에서 다시 읽어 PNG 길이와 SHA256이 일치해야 완료로 표시한다.

단위 테스트는 Pillow가 생성·독립 확인한 합성 RGB/L PNG, 필터 0~4, 비정상 PNG·중복 JSON, 실제 HTTP multipart, 취소·늦은 결과·저장 ticket 수명을 검사한다. 실제 사진·모델·정답 자료는 APK에 포함하지 않는다. `tools/generate_experimental_png_fixtures.py`는 합성 fixture만 재생성한다.

선택적 기기 검사는 `ExperimentalWireInstrumentedTest`를 사용한다. 로컬 자료는 adb로 앱의 private filesDir에 일시 배치하고 `private_input`, `expected_rgb_sha256`을 인자로 준다. `private_response`는 기존 실제 응답을 다시 검증하며, `real_backend_url`/`photo_engine`은 Repository→실제 HTTP 경로를 실행한다. 실제 응답·비교 영수증·PNG는 앱 private filesDir에만 기록한다. provider 검사는 숨겨진 임시 MediaStore record를 읽기 검증 후 삭제한다. 이 검사는 AI의 일반 성능이나 보안 증명이 아니다.
