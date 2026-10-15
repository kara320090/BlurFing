# 명시적 PHOTO 결과 전송

`scripts/export_photo_permissions_v1.py`는 선택한 PHOTO 엔진을 한 번 실행한 뒤 실제 반환 RGB와 원본 좌표의 permission을 검증한다. 새 기본 알고리즘이나 보호 성능 승인 경로는 아니다. 서버는 별도 [V2 진입점](../../backend/README-photo-v2.md)을 사용하며 기존 V1 블러 API는 유지한다.

입력은 클라이언트가 방향과 색상을 sRGB로 정규화한 RGB 8-bit·비인터레이스·불투명 단일 PNG다. 허용 chunk는 IHDR, 선택적인 최소 EXIF 1 eXIf, 연속 IDAT, IEND뿐이다. ICC·색상/HDR 정보·추가 EXIF와 기타 메타데이터는 거절한다. 태그가 없다는 사실만으로 sRGB 변환이 입증되지는 않으므로 클라이언트가 실제 색상 변환을 수행해야 한다. ICC 태그만 삭제하면 색상 의미가 달라질 수 있다.

15MiB·2,000만 화소를 넘거나 투명·애니메이션·16-bit·잘못된 압축 스트림이면 거절한다. 서버나 bridge가 입력을 임의 축소·회전·색상 변환하거나 JPEG로 재압축하지 않는다. A 밖 RGB 보존은 이 정식 업로드 RGB를 기준으로 검사한다. 원본 개인 파일은 정규화 과정에서도 덮어쓰지 않는다.

```text
<AI Python> ai/scripts/export_photo_permissions_v1.py --input <canonical.png> --output <fresh-output-directory> --photo-engine <native_v12|distal_v13|pose_v14> --consumed-registry <private-registry.json> --request-id <unique-id> [--photo-model <V6-model-directory>] [--development-replay]
```

V6 model directory에는 `final_config.private.json`과 `final_context_whole_pad.pt`가 필요하다. Geometry 엔진에는 V6 model을 전달하지 않는다. 각 엔진의 COLFISPOOF·손 자세 런타임은 별도로 명시 설정해야 한다. 다른 엔진이나 기존 블러로 대체 실행하지 않는다. 기존 평가 사진의 재실행은 명시적인 개발 재현이며 독립 평가가 아니다.

Bridge는 원본·semantic mask·모델·입력 grid·worker 관측·저장된 report의 결합을 검사하고, 동일 엔진의 실제 component partition을 재구성한다. 각 적용 영역에는 실제 native RGB에서 통과한 구조 검사 증거가 있어야 한다. 반환 변경 집합 C는 적용 permission A에 포함되고, A와 거절 permission R은 겹치지 않아야 한다. R과 A 밖 RGB는 원본과 동일해야 한다. 표시용 사각형은 permission을 대신하지 않는다.

`result.transport.json`은 [V2 고정 계약](../../contracts/photo-experimental-v2.schema.json)의 전체 응답이다. stdout은 상태와 transport 파일 위치만 포함하는 JSON 한 개다. 비공개 출력 폴더의 원본·mask·중간 자료·모델 경로·matcher 자료를 공개 응답에 복사하지 않는다. 모델·소스 snapshot·원본은 실행 전후 동일해야 한다.

`success`는 검출된 permission component가 모두 변환됐다는 뜻이다. 모든 손가락을 찾았거나 지문 보호 성능을 입증했다는 뜻은 아니다. `partial_success`와 `rejected`는 거절 영역에 원본 지문이 남는다는 안내를 유지한다. V13/V14는 경계 검토가 필요한 실험이며, V13의 기존 정답 자료 경계 정확도 회귀도 유지해 표시한다.
