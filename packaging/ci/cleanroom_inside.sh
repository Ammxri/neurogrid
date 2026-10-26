#!/usr/bin/env bash
# Runs INSIDE the clean-room container (cleanroom_linux.sh): no network (--network none), no Python in the image,
# an unprivileged user (uid 1000). Installs the Linux offline bundle with its own installer and runs every v0.1
# command from the installation on synthetic fixtures (read-only mount) under a Chinese folder name with a space.
# Dataset data never gives exit 2 (UF-08, NG-N01, NG-N04, A-26, A-58).
# Inputs: /in/bundle.tar.gz, /in/fixtures; optional /in/shell.zip. Evidence: /out (exit-codes.txt, *.log,
# strace-*.txt with NG_TRACE=1).
# Environment: NG_TRACE=1 (every step under strace), NG_EXPECT_REFUSAL=1 (only the installer, which must refuse
# with exit 2), NG_PDF_ZIP/NG_PDF_SHA (install the PDF browser from that zip; the PDF report must then succeed).
# The signature of a release bundle is verified on the connected host before (release.yml): cosign could not
# reach Sigstore's trust root from inside the container, exactly as on an offline customer machine.
set -euo pipefail

out=/out
codes="$out/exit-codes.txt"
: >"$codes"
mkdir -p "$HOME"

note() { printf '%s\n' "$*" | tee -a "$codes"; }

step() {
  local name="$1" allowed="$2" start code=0
  shift 2
  start="$(date +%s)"
  if [ "${NG_TRACE:-0}" = 1 ]; then
    strace -f -qq -e trace=connect,sendto,sendmsg -o "$out/strace-$name.txt" "$@" \
      >"$out/$name.out.log" 2>"$out/$name.err.log" || code=$?
  else
    "$@" >"$out/$name.out.log" 2>"$out/$name.err.log" || code=$?
  fi
  note "$name $code ($(($(date +%s) - start)) s)"
  case " $allowed " in
    *" $code "*) ;;
    *)
      printf '%s exited with %s (allowed: %s)\n' "$name" "$code" "$allowed" >&2
      exit 1
      ;;
  esac
}

if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  echo "the image has a Python interpreter: not a clean room" >&2
  exit 1
fi
note "uid $(id -u), glibc $(getconf GNU_LIBC_VERSION 2>/dev/null || echo unknown), $(. /etc/os-release && echo "$PRETTY_NAME")"

room=/tmp/room
mkdir -p "$room" "$room/pdf-browser" "$room/tmp"
export TMPDIR="$room/tmp"
cd "$room"
tar -xzf /in/bundle.tar.gz
bundle="$(echo "$room"/neurogrid-*-offline-linux_x86_64)"
[ -d "$bundle" ] || { echo "no bundle folder in the archive" >&2; exit 1; }
export NEUROGRID_PDF_BROWSER_DIR="$room/pdf-browser"
# No proxy variables (A-49 evidence): a dead proxy such as http://127.0.0.1:9 would turn a phone-home of a
# proxy-honouring client into a loopback connect, which the strace evaluation counts as allowed; without them
# every attempt names its real destination and fails on --network none. Nothing is inherited from the host
# (docker run passes only the -e variables of cleanroom_linux.sh); this unset is for a reused image.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy

# A Chinese folder name with a space in the install prefix too (home folders may carry such names).
prefix="$room/安装 目录/neurogrid"
options=(--prefix "$prefix" --skip-signature-check)
if [ -n "${NG_PDF_ZIP:-}" ]; then options+=(--pdf-browser-zip "$NG_PDF_ZIP" --pdf-browser-sha256 "$NG_PDF_SHA"); fi

if [ "${NG_EXPECT_REFUSAL:-0}" = 1 ]; then
  step install-refused 2 "$bundle/install.sh" "${options[@]}"
  grep -q "glibc" "$out/install-refused.err.log" || { echo "refused without naming glibc" >&2; exit 1; }
  [ ! -e "$prefix" ] || { echo "the refused installation left files behind" >&2; exit 1; }
  note "refusal as expected"
  exit 0
fi

step install 0 "$bundle/install.sh" "${options[@]}"
step install-verify-only 0 "$bundle/install.sh" --verify-only --skip-signature-check
# What the PDF part relies on: the bundled interpreter and installer next to BUNDLE.json (kernel/pdf.py names
# this command when the PDF browser is missing). The installer removes its uv cache.
for rel in bin/neurogrid BUNDLE.json python/bin/python3.12 tools/install_pdf_browser.py venv/bin/neurogrid; do
  [ -e "$prefix/$rel" ] || { echo "the installation lacks $rel" >&2; exit 1; }
done
[ ! -e "$prefix/.uv-cache" ] || { echo "the installer left its uv cache behind" >&2; exit 1; }
predicted="$(sed -n 's/^ "max_relative_install_path": \([0-9]*\),\{0,1\}$/\1/p' "$prefix/BUNDLE.json")"
longest="$(cd "$prefix" && find . -type f -printf '%P\n' | awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }')"
# A-48: bytecode compiled at install, for every module of the venv (a Chinese prefix once made it silently fail).
modules=0 uncompiled=0
while IFS= read -r -d '' module; do
  name="${module##*/}"
  modules=$((modules + 1))
  [ -f "${module%/*}/__pycache__/${name%.py}.cpython-312.pyc" ] || uncompiled=$((uncompiled + 1))
done < <(find "$prefix/venv/lib/python3.12/site-packages" -type f -name '*.py' -print0)
[ "$modules" -gt 0 ] && [ "$uncompiled" -eq 0 ] \
  || { echo "modules without compiled bytecode: $uncompiled of $modules" >&2; exit 1; }
note "installed: $(du -sm "$prefix" | cut -f1) MiB; longest path below the prefix $longest characters (BUNDLE.json: $predicted); $modules modules, all with compiled bytecode"
ng="$prefix/bin/neurogrid"

# FIF has no synthetic fixture; it is covered by the corpus run (ds000248).
work="$room/work/数据 集"
mkdir -p "$work"
for fixture in edf_ok edf_plus_d bdf_ok brainvision_ok eeglab_ok bids_ok; do
  cp -r "/in/fixtures/synthetic/$fixture" "$work/"
done
chmod -R u+w "$work"
cp /in/fixtures/documented.toml "$work/documented.toml"
{
  sed '/^\[convert\]/,$d' /in/fixtures/documented.toml
  printf '[[convert.files]]\npath = "rec_a.edf"\nsubject = "01"\ntask = "rest"\n\n'
  printf '[[convert.files]]\npath = "rec_b.edf"\nsubject = "02"\ntask = "rest"\n'
} >"$work/convert.toml"
cd "$work"
as_of=(--as-of 2026-10-11)
step scan 0 "$ng" scan "$work/edf_ok" --out "$work/scan.json"
step check-edf 0 "$ng" check edf_ok --config documented.toml --out r-edf.json "${as_of[@]}"
step check-edf-plus-d "0 1" "$ng" check edf_plus_d --config documented.toml --out r-edfd.json "${as_of[@]}"
step check-bdf "0 1" "$ng" check bdf_ok --config documented.toml --out r-bdf.json "${as_of[@]}"
step check-brainvision "0 1" "$ng" check brainvision_ok --config documented.toml --out r-bv.json "${as_of[@]}"
step check-eeglab "0 1" "$ng" check eeglab_ok --config documented.toml --out r-set.json "${as_of[@]}"
step check-bids "0 1" "$ng" check "$work/bids_ok" --rulepack bids --rulepack gxdsl008 --out "$work/r-bids.json" "${as_of[@]}"
step convert 0 "$ng" convert edf_ok --to bids --out converted --config convert.toml
step check-converted "0 1" "$ng" check converted --rulepack bids --out r-conv.json "${as_of[@]}"
step manifest 0 "$ng" manifest bids_ok --out manifest.json
step verify 0 "$ng" verify bids_ok --manifest manifest.json
step report-html 0 "$ng" report r-edf.json --lang zh,en --format html --out report
for lang in zh en; do [ -f "report/report.$lang.html" ] || { echo "report.$lang.html missing" >&2; exit 1; }; done
if [ -n "${NG_PDF_ZIP:-}" ]; then
  step report-pdf 0 "$ng" report r-edf.json --lang zh,en --format html,pdf --out report-pdf
  for lang in zh en; do [ -f "report-pdf/report.$lang.pdf" ] || { echo "report.$lang.pdf missing" >&2; exit 1; }; done
else
  step report-pdf-without-shell 2 "$ng" report r-edf.json --lang en --format pdf --out report-pdf
fi
step usage-error 2 "$ng" check
# A-54: neither the installer nor a NeuroGrid run leaves anything in the temporary folder.
left="$(ls -A "$room/tmp")"
printf '%s\n' "$left" >"$out/temp-left.txt"
[ -z "$left" ] || { echo "entries left in TMPDIR (temp-left.txt)" >&2; exit 1; }
note "all steps passed"
