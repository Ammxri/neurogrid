#!/usr/bin/env bash
# OS-level offline evidence on Linux (NG-N01, CON-04, ARC-06, A-49; CI only, D-09): the installed offline bundle
# runs the installer and every v0.1 command in a container without network (--network none) under
# strace -f -e trace=connect,sendto,sendmsg. tools/strace_check.py fails on any AF_INET/AF_INET6 address that is
# not loopback and lists the loopback calls. The image is debian:12-slim plus strace, without Python.
#
# Usage: offline_strace_linux.sh ARCHIVE [EVIDENCE_DIR]
set -euo pipefail

archive="${1:?usage: offline_strace_linux.sh ARCHIVE [EVIDENCE_DIR]}"
evidence="${2:-evidence-strace}"
root="$(cd "$(dirname "$0")/../.." && pwd)"

docker build --quiet --tag neurogrid-strace:debian12 - >/dev/null <<'EOF'
FROM debian:12-slim
RUN apt-get update && apt-get install -y --no-install-recommends strace && rm -rf /var/lib/apt/lists/*
RUN if command -v python3 || command -v python; then exit 1; fi
EOF

bash "$root/packaging/ci/cleanroom_linux.sh" --image neurogrid-strace:debian12 --trace --evidence "$evidence" "$archive"
python3 "$root/tools/strace_check.py" "$evidence"
