# Linux 설치 및 실행

저장소 최상위 디렉터리에서 실행합니다. Python >=3.10, Java/Javac >=11이 필요하며 네이티브 빌드에는 g++/make가 필요합니다.

```sh
python3 -m venv ai/.venv
source ai/.venv/bin/activate
python -m pip install -r ai/requirements.txt
java -version
javac -version
python ai/scripts/reproduce_frozen_pipeline.py --check
```

공개 소스 검사는 코드 존재만 확인하며 비공개 촬영 자료 목록 검사나 실제 변환을 수행하지 않습니다.

## SourceAFIS
SourceAFIS 3.18.1 및 전이 의존성 JAR 15개를 공식 파일 목록 docs/sourceafis_runtime.json으로 준비하고 SHA-256을 검증합니다. 기본 위치는 ai/private/sourceafis/lib입니다. 다른 위치는 BLURFING_SOURCEAFIS_HOME을 사용합니다. 사용자 지정 설정 목록은 BLURFING_SOURCEAFIS_CONFIG로 지정합니다. JAR의 file 필드는 설정 목록 기준 상대 경로나 비공개 절대 경로를 지원합니다. 클래스는 재사용 가능한 경우에만 사용하며, 그렇지 않으면 시스템 임시 폴더에서 Java 11 대상 버전으로 컴파일합니다.

## NBIS
공식 NBIS 5.0.0을 별도의 비공개 새 디렉터리에 준비합니다. 공식 setup.sh install-dir --without-X11 --STDLIBS --64 → make config → 패키지별 cpheaders(IJG/pcasys 포함) → IJG/commonnbis/imgtools/an2k/mindtct/bozorth3 라이브러리 → 필요한 실행 파일 순서로 빌드합니다. 소스는 수정하지 않습니다.

브리지 빌드 예시입니다. NBIS_ROOT는 비공개 Rel_5.0.0 경로입니다.

```sh
g++ -std=c++17 -O2 -Wall -Wextra -I"$NBIS_ROOT/exports/include"   ai/platform/linux/nbis_local_linux.cpp   -Wl,--start-group "$NBIS_ROOT"/exports/lib/lib{mindtct,bozorth3,an2k,image,ihead,wsq,jpegl,jpegb,fet,cblas,ioutil,util}.a   -Wl,--end-group -lm -o /path/to/nbis_local_linux
chmod +x /path/to/nbis_local_linux
```
config/nbis_linux.example.json을 비공개 JSON으로 복사한 뒤 실제 ELF 실행 파일의 절대 경로와 SHA-256을 기록합니다.

```sh
export BLURFING_NBIS_CONFIG=/path/to/nbis.runtime.json
export BLURFING_SOURCEAFIS_HOME=/path/to/sourceafis
bash ai/platform/linux/setup_linux.sh
python ai/scripts/check_platform_runtime.py --require-all
python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input /path/to/input.jpg
```
실제 평가 전에 입력 사용 동의와 독립 검증 자료의 출처를 확인합니다. 출력은 시스템 임시 폴더의 새 디렉터리이며 기존 파일은 덮어쓰지 않습니다.

## 지문 매칭 평가
NBIS/SourceAFIS 공통 API로 `images={'original': original_frame, 'transformed': returned_frame}`와 `pairs=[{'key':'self','probe':'original','candidate':'original'}, {'key':'changed','probe':'original','candidate':'transformed'}]`를 넘깁니다. run_name은 ASCII로 지정합니다. 기존 너비 정규화 관심 영역(ROI) 계약을 따라야 하며 새로운 잘라내기 기준이나 임계값을 만들지 않습니다. 반환된 output_folder/audit_path를 보존합니다.

## 공개 검증용 자료
사용자가 별도 제공한 a011p_03.wsq를 **임시 사본**으로 복사한 다음 공식 dwsq raw fixture.wsq -raw_out 명령으로 디코딩합니다. 336x512·8비트·172032바이트를 확인하고 bridge raw RAW 336 512 500 output.xyt → 87, bridge match output.xyt output.xyt → 499 87 87을 확인합니다. 공개 참조 XYT와 바이트 일치 여부를 비교합니다. 이미지 파일은 공개 저장소에 넣지 않습니다.

## Unified routing

Use the environment configuration and full CLI/API in [FAIL_CLOSED_SYSTEM.md](FAIL_CLOSED_SYSTEM.md). PHOTO missing runtime rejects without pixel changes; quality rejection is normal. The isolated COLFISPOOF environment must not replace the scientific/core environment.
