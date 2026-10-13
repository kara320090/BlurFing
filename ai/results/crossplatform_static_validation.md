# 플랫폼 공통 구현의 정적 검사 기록

이 문서는 Windows 실제 실행 검증 이전에 수행한 정적 검사 기록입니다. 아래 상태 값과 도구 사용 가능 여부는 **당시 기준**이며 현재 Windows 검증 상태는 [최신 검증 기록](../docs/VALIDATION.md)과 [상태 설정](../docs/platform_status.json)을 확인하세요.

Python 파일 39개의 구문 검사가 통과했습니다. 공통 사용자 정의 모듈 가져오기와 운영체제별 호출 분기도 통과했습니다. 특징점 추출·매칭 실행 없이 기존 Linux 설정의 ELF 형식과 SHA를 확인했습니다. SourceAFIS 클래스 경로는 하위 프로세스를 모의 처리하여 Linux 콜론, Windows 세미콜론을 확인했습니다.

Windows NBIS 모의 시험 6개는 정상, insufficient_features, 프로세스 실패, 시간 초과, 잘못된 RAW 표준 출력, 잘못된 MATCH 표준 출력입니다. 이는 Python 어댑터 시험이며 **Windows 실행 환경의 실제 실행이 아닙니다**. 네이티브 알고리즘 부분은 동일하며 Windows 변경은 UTF-16 인자에서 UTF-8로의 변환, 유니코드 파일 접근 및 바이너리 모드 LF 출력입니다.

핵심 변환의 추상 구문 트리(AST)는 시스템 임시 경로를 정규화한 뒤 동일했습니다. Linux NBIS 작업의 AST도 해당 경로 정규화 후 변경되지 않았습니다. Linux 네이티브 소스는 g++ 구문 전용 검사를, Linux 설치 셸 스크립트는 bash -n 검사를 통과했습니다.

이 검사 당시에는 MinGW 교차 컴파일러, CMake 및 PowerShell을 사용할 수 없었습니다. Windows C++ 컴파일·링크 및 PowerShell 구문 검사는 수행하지 않았습니다. Windows EXE나 실행 파일·JAR은 포함하지 않았습니다. 당시에는 실제 Windows 빌드·검증용 자료 확인, 공통 변환 실패 처리 계약 및 SourceAFIS 실행 검증이 추가로 필요했습니다. 이후 수행한 Windows 빌드·공식 검증용 자료·SourceAFIS 실제 실행 결과와 남은 전체 파이프라인 검증 범위는 최신 검증 기록에 별도로 정리되어 있습니다.

당시 LINUX_PIPELINE_VALIDATED=true는 기존 Linux 개발용 기준 구성을 의미합니다. 새 저장소 구조의 회귀 검사는 정적 검사만 수행했습니다. 당시 상태는 WINDOWS_IMPLEMENTATION_READY=true, WINDOWS_CROSS_BUILD_SUCCESS=false, WINDOWS_RUNTIME_VALIDATED=false, FINAL_INDEPENDENT_VALIDATION_COMPLETE=false, PROJECT_COMPLETE=false였습니다.
