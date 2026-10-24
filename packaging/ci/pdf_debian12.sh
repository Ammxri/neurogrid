#!/usr/bin/env bash
# PDF on Linux (A-58, A-26; CI only, D-09): debian:12-slim with the system libraries of the Chrome Headless Shell
# (list from tools/linux_pdf_packages.py, the same data the start check uses) and strace, without Python. The offline
# bundle is installed with the PDF browser from the pinned zip (fetched on the host), then report --format
# html,pdf runs without network and under strace; the PDF QA gate runs inside `report`.
#
# Usage: pdf_debian12.sh ARCHIVE SHELL_ZIP [EVIDENCE_DIR]
set -euo pipefail

archive="${1:?usage: pdf_debian12.sh ARCHIVE SHELL_ZIP [EVIDENCE_DIR]}"
zip="${2:?usage: pdf_debian12.sh ARCHIVE SHELL_ZIP [EVIDENCE_DIR]}"
evidence="${3:-evidence-pdf}"
root="$(cd "$(dirname "$0")/../.." && pwd)"

packages="$(python3 "$root/tools/linux_pdf_packages.py" debian12)"
[ -n "$packages" ] || { echo "no package list for debian12" >&2; exit 2; }
docker build --quiet --tag neurogrid-pdf:debian12 --build-arg "PACKAGES=$packages" - >/dev/null <<'EOF'
FROM debian:12-slim
ARG PACKAGES
RUN apt-get update && apt-get install -y --no-install-recommends strace $PACKAGES && rm -rf /var/lib/apt/lists/*
RUN if command -v python3 || command -v python; then exit 1; fi
EOF

sha="$(sha256sum "$zip" | cut -d ' ' -f 1)"
bash "$root/packaging/ci/cleanroom_linux.sh" --image neurogrid-pdf:debian12 --trace --pdf-zip "$zip" \
  --pdf-sha256 "$sha" --evidence "$evidence" "$archive"
python3 "$root/tools/strace_check.py" "$evidence"
