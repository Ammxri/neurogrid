#!/usr/bin/env bash
# Linux clean room of the offline bundle (UF-08, NG-N01, NG-N04, A-26, A-58; CI only, D-09): the bundle is installed
# in a container without network (--network none), without a preinstalled Python and as uid 1000, then every v0.1
# command runs from the installation (packaging/ci/cleanroom_inside.sh). The image and its digest are recorded.
#
# Usage: cleanroom_linux.sh --image IMAGE [--expect-refusal] [--trace] [--pdf-zip ZIP --pdf-sha256 HEX]
#                           [--evidence DIR] ARCHIVE
#   --expect-refusal  the installer must refuse with exit 2 (glibc below 2.28, e.g. ubuntu:18.04)
#   --trace           every step under strace (the image must contain strace; see offline_strace_linux.sh)
set -euo pipefail

image="" refusal=0 trace=0 pdf_zip="" pdf_sha="" evidence="evidence" archive=""
while [ $# -gt 0 ]; do
  case "$1" in
    --image) image="$2"; shift 2 ;;
    --expect-refusal) refusal=1; shift ;;
    --trace) trace=1; shift ;;
    --pdf-zip) pdf_zip="$2"; shift 2 ;;
    --pdf-sha256) pdf_sha="$2"; shift 2 ;;
    --evidence) evidence="$2"; shift 2 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) archive="$1"; shift ;;
  esac
done
[ -n "$image" ] && [ -f "$archive" ] || { echo "usage: cleanroom_linux.sh --image IMAGE [...] ARCHIVE" >&2; exit 2; }

root="$(cd "$(dirname "$0")/../.." && pwd)"
archive="$(realpath "$archive")"
mkdir -p "$evidence"
evidence="$(realpath "$evidence")"
chmod 777 "$evidence"  # the container user (uid 1000) writes the evidence

if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker pull --quiet "$image" >/dev/null
fi
digest="$(docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' "$image")"
printf '%s %s\n' "$image" "$digest" >>"$evidence/images.txt"

mounts=(
  -v "$archive:/in/bundle.tar.gz:ro"
  -v "$root/tests/fixtures:/in/fixtures:ro"
  -v "$root/packaging/ci/cleanroom_inside.sh:/in/cleanroom_inside.sh:ro"
  -v "$evidence:/out"
)
environment=(-e HOME=/tmp/home -e "NG_EXPECT_REFUSAL=$refusal" -e "NG_TRACE=$trace")
if [ -n "$pdf_zip" ]; then
  mounts+=(-v "$(realpath "$pdf_zip"):/in/shell.zip:ro")
  environment+=(-e NG_PDF_ZIP=/in/shell.zip -e "NG_PDF_SHA=$pdf_sha")
fi
capabilities=()
if [ "$trace" -eq 1 ]; then
  capabilities=(--cap-add SYS_PTRACE --security-opt seccomp=unconfined)
fi

docker run --rm --network none --user 1000:1000 "${capabilities[@]}" "${mounts[@]}" "${environment[@]}" \
  "$image" bash /in/cleanroom_inside.sh
