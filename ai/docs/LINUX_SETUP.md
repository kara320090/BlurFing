# Linux setup

저장소 root에서 실행합니다. Python >=3.10, Java/Javac >=11, native build에는 g++/make가 필요합니다.

```sh
python3 -m venv ai/.venv
source ai/.venv/bin/activate
python -m pip install -r ai/requirements.txt
java -version
javac -version
python ai/scripts/reproduce_frozen_pipeline.py --check
```

공개 check는 코드 존재만 확인하며 private capture inventory 검사나 실제 transform이 아닙니다.

## SourceAFIS
SourceAFIS 3.18.1 및 전이 의존성 JAR 15개를 공식 artifact 목록 docs/sourceafis_runtime.json으로 준비하고 SHA-256을 검증합니다. 기본 위치는 ai/private/sourceafis/lib 입니다. 다른 위치는 BLURFING_SOURCEAFIS_HOME을 사용합니다. custom manifest는 BLURFING_SOURCEAFIS_CONFIG로 지정합니다. JAR file 필드는 manifest의 상대 경로 또는 private absolute path를 지원합니다. 클래스는 재사용 가능할 때만 사용하며 아니면 system temp에서 Java 11 target으로 컴파일합니다.

## NBIS
공식 NBIS 5.0.0을 별도 private clean directory에 준비합니다. 공식 setup.sh install-dir --without-X11 --STDLIBS --64 → make config → package cpheaders(IJG/pcasys 포함) → IJG/commonnbis/imgtools/an2k/mindtct/bozorth3 libs → 필요한 bins 순서입니다. source patch는 하지 않습니다.

Bridge build 예시 (NBIS_ROOT는 private Rel_5.0.0):
```sh
g++ -std=c++17 -O2 -Wall -Wextra -I"$NBIS_ROOT/exports/include"   ai/platform/linux/nbis_local_linux.cpp   -Wl,--start-group "$NBIS_ROOT"/exports/lib/lib{mindtct,bozorth3,an2k,image,ihead,wsq,jpegl,jpegb,fet,cblas,ioutil,util}.a   -Wl,--end-group -lm -o /path/to/nbis_local_linux
chmod +x /path/to/nbis_local_linux
```
config/nbis_linux.example.json을 private JSON으로 복사한 뒤 실제 absolute ELF path와 SHA-256을 기록합니다.
```sh
export BLURFING_NBIS_CONFIG=/path/to/nbis.runtime.json
export BLURFING_SOURCEAFIS_HOME=/path/to/sourceafis
bash ai/platform/linux/setup_linux.sh
python ai/scripts/check_platform_runtime.py --require-all
python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input /path/to/input.jpg
```
실제 평가 전 입력 사용 동의와 독립 검증 provenance를 확인합니다. 출력은 system temp의 새 디렉터리이며 기존 파일은 덮어쓰지 않습니다.

## Matcher evaluation
NBIS/SourceAFIS 공통 API로 `images={'original': original_frame, 'transformed': returned_frame}`와 `pairs=[{'key':'self','probe':'original','candidate':'original'}, {'key':'changed','probe':'original','candidate':'transformed'}]`를 넘깁니다. run_name은 ASCII로 지정합니다. 기존 width-normalized ROI 계약을 따라야 하며 새 crop이나 threshold를 만들지 않습니다. 반환된 output_folder/audit_path를 보존합니다.

## Public fixture
사용자가 별도 제공한 a011p_03.wsq를 **임시 사본**에 복사한 다음 official dwsq raw fixture.wsq -raw_out으로 decode합니다. 336x512/8-bit/172032 bytes를 확인하고 bridge raw RAW 336 512 500 output.xyt → 87, bridge match output.xyt output.xyt → 499 87 87을 확인합니다. 공개 reference XYT와 byte equality를 비교합니다. 이미지 파일은 공개 tree에 넣지 않습니다.

## Unified routing

Use the environment configuration and full CLI/API in [FAIL_CLOSED_SYSTEM.md](FAIL_CLOSED_SYSTEM.md). PHOTO missing runtime rejects without pixel changes; quality rejection is normal. The isolated COLFISPOOF environment must not replace the scientific/core environment.
