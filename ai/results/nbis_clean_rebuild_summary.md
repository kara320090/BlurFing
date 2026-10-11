# NBIS clean rebuild summary

Official NBIS 5.0.0 archive에서 별도 clean tree를 만들었습니다. 기존 build tree를 사용하지 않았으며 source patch 없이 공식 setup/config/header-copy 절차를 사용했습니다. pcasys의 generated little.h 및 IJG headers/libs도 공식 build 순서로 준비했습니다.

MINDTCT, BOZORTH3, required static libs, native bridge compile/link 및 dwsq가 성공했습니다. ELF64 little-endian x86-64이며 unresolved NBIS symbols는 없습니다. 시스템 동적 라이브러리 imports는 정상적으로 남습니다.

Public fixture: 336x512, depth 8, raw 172032 bytes, minutiae 87 rows, 공개 fixture XYT와 byte-identical, self-match `499 87 87`.

Clean rebuilt bridge SHA-256는 stable bridge와 동일합니다:
`b8eff6329edf8ee59c5462afc8f07caab2f346ecc70507811808b552ff4299dc`.

이 결과는 fixture 및 clean build 재현성 검증입니다. Windows full equivalence나 실제 보호 효과를 주장하지 않습니다.
