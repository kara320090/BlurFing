#!/usr/bin/env bash
set -euo pipefail
AI_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Python >=3.10 required"; print(sys.version)'
python3 -m pip --version
command -v java >/dev/null || { echo 'Java 11+ missing' >&2; exit 1; }
command -v javac >/dev/null || { echo 'JDK javac missing' >&2; exit 1; }
echo 'Install Python packages in your venv: python -m pip install -r ai/requirements.txt'
echo 'Set BLURFING_NBIS_CONFIG or BLURFING_NBIS_LINUX_CONFIG to a private JSON.'
echo 'Set BLURFING_SOURCEAFIS_HOME for private jars (optional default ai/private/sourceafis).'
python3 "$AI_ROOT/scripts/check_platform_runtime.py" --require-all
