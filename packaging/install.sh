#!/usr/bin/env bash
# NeuroGrid offline installer for Linux x86_64 with glibc >= 2.28 (Debian 12, Ubuntu 22.04+; UF-08, A-26, A-58,
# D-08, D-10 g). It runs before any Python exists, so its messages are bilingual inline (zh / en). Nothing is
# downloaded: uv runs with UV_OFFLINE=1, --no-index and --require-hashes. Works without root; no profile or PATH
# change; uninstall = delete the install folder (and the PDF browser folder, if one was installed).
# Exit codes: 0 installed (or verified with --verify-only), 2 usage or environment error, 3 integrity error
# (SHA256SUMS), 4 signature error.
set -euo pipefail
export LC_ALL=C

ISSUER="https://token.actions.githubusercontent.com"

say() { printf '%s / %s\n' "$1" "$2"; }
fail() {
  printf '错误 / Error: %s / %s\n' "$2" "$3" >&2
  exit "$1"
}

usage() {
  cat <<'EOF'
install.sh [--prefix DIR] [--cosign PATH] [--skip-signature-check] [--verify-only]
           [--pdf-browser-zip ZIP --pdf-browser-sha256 HEX]
  --prefix DIR              安装文件夹 / install folder (default ${XDG_DATA_HOME:-~/.local/share}/neurogrid/<version>)
  --cosign PATH             用于核验签名的 cosign / cosign used to verify the signature
  --skip-signature-check    已在联网电脑上核验签名 / the signature was verified on a connected machine
  --verify-only             仅核验完整性和签名 / only verify integrity and signature
  --pdf-browser-zip ZIP     从客户提供的 zip 安装 PDF 浏览器 / install the PDF browser from a provided zip
  --pdf-browser-sha256 HEX  该 zip 的 SHA-256 / SHA-256 of that zip
EOF
}

# 0 if the glibc version ($1, e.g. 2.36) is at least 2.28 (A-58).
glibc_supported() {
  local major minor rest
  IFS=. read -r major minor rest <<<"$1"
  [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
  ((major > 2 || (major == 2 && minor >= 28)))
}

# A top-level field of BUNDLE.json (written with one space of indentation and sorted keys).
bundle_field() {
  sed -n "s/^ \"$2\": \"\\{0,1\\}\\([^\",]*\\)\"\\{0,1\\},\\{0,1\\}\$/\\1/p" "$1/BUNDLE.json" | head -n 1
}

main() {
  local bundle prefix="" cosign="" skip_signature=0 verify_only=0 pdf_zip="" pdf_sha=""
  bundle="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  while [ $# -gt 0 ]; do
    case "$1" in
      --prefix | --cosign | --pdf-browser-zip | --pdf-browser-sha256)
        [ $# -ge 2 ] || fail 2 "$1 需要一个值" "$1 needs a value"
        case "$1" in
          --prefix) prefix="$2" ;;
          --cosign) cosign="$2" ;;
          --pdf-browser-zip) pdf_zip="$2" ;;
          --pdf-browser-sha256) pdf_sha="$2" ;;
        esac
        shift 2
        ;;
      --skip-signature-check) skip_signature=1; shift ;;
      --verify-only) verify_only=1; shift ;;
      -h | --help) usage; exit 0 ;;
      *) fail 2 "未知参数：$1" "unknown option: $1" ;;
    esac
  done

  [ -f "$bundle/BUNDLE.json" ] || fail 3 "缺少 BUNDLE.json" "BUNDLE.json missing"
  local version platform identity max_path
  version="$(bundle_field "$bundle" version)"
  platform="$(bundle_field "$bundle" platform)"
  identity="$(bundle_field "$bundle" release_identity)"
  max_path="$(bundle_field "$bundle" max_relative_install_path)"
  [ "$identity" != "null" ] || identity=""
  if [ "$platform" != "linux_x86_64" ] || ! [[ "$version" =~ ^[A-Za-z0-9.+-]+$ ]]; then
    fail 2 "此安装包不适用于 Linux x86_64" "this bundle is not for Linux x86_64"
  fi
  if [ -n "$pdf_zip$pdf_sha" ]; then
    [ -n "$pdf_zip" ] && [[ "$pdf_sha" =~ ^[0-9a-fA-F]{64}$ ]] \
      || fail 2 "--pdf-browser-zip 须与 --pdf-browser-sha256（64 位十六进制）同时使用" \
        "--pdf-browser-zip needs --pdf-browser-sha256 (64 hex digits)"
    [ -f "$pdf_zip" ] || fail 2 "找不到文件：$pdf_zip" "file not found: $pdf_zip"
    pdf_zip="$(cd "$(dirname "$pdf_zip")" && pwd -P)/$(basename "$pdf_zip")"
  fi

  # 1. Integrity: every listed file with its SHA-256, no unlisted file, symbolic links exactly as in SYMLINKS.
  cd "$bundle"
  [ -f SHA256SUMS ] || fail 3 "缺少 SHA256SUMS" "SHA256SUMS missing"
  local malformed listed present extra links count
  malformed="$(grep -vE '^[0-9a-f]{64}  [A-Za-z0-9._+/-]+$' SHA256SUMS | head -n 1 || true)"
  [ -z "$malformed" ] || fail 3 "SHA256SUMS 格式错误：$malformed" "malformed SHA256SUMS line: $malformed"
  ! grep -qE '  (\.\.?/|.*/\.\.?(/|$)|\.\.?$)' SHA256SUMS || fail 3 "SHA256SUMS 格式错误" "malformed SHA256SUMS"
  listed="$(sed 's/^[0-9a-f]\{64\}  //' SHA256SUMS | sort)"
  [ -z "$(printf '%s\n' "$listed" | uniq -d)" ] || fail 3 "SHA256SUMS 中有重复" "SHA256SUMS lists a file twice"
  sha256sum --check --strict --quiet SHA256SUMS >&2 || fail 3 "文件与 SHA256SUMS 不符，未安装" \
    "files do not match SHA256SUMS; nothing installed"
  present="$(find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.sigstore.json -printf '%P\n' | sort)"
  extra="$(comm -13 <(printf '%s\n' "$listed") <(printf '%s\n' "$present"))"
  [ -z "$extra" ] || fail 3 "存在未列出的文件：${extra//$'\n'/ }" "unlisted files present: ${extra//$'\n'/ }"
  [ -z "$(find . ! -type f ! -type l ! -type d | head -n 1)" ] || fail 3 "存在特殊文件" "special files present"
  links="$(find . -type l -printf '%P -> %l\n' | sort)"
  [ -f SYMLINKS ] && [ "$links" = "$(sort SYMLINKS)" ] || fail 3 "符号链接与 SYMLINKS 不符" \
    "symbolic links differ from SYMLINKS"
  count="$(printf '%s\n' "$listed" | wc -l)"
  say "完整性已核对（${count// /} 个文件）" "integrity verified (${count// /} files)"

  # 2. Signature (Sigstore keyless, D-10 g). A check inside the archive proves integrity; authenticity comes from
  #    the check on a connected machine before the transfer (README.txt, docs/installation.html). cosign needs
  #    Sigstore's trust root (network or a prepared cache), so an explicit --skip-signature-check wins over a cosign
  #    found on PATH; --cosign always verifies.
  if [ -n "$cosign" ] && [ "$skip_signature" -eq 1 ]; then
    fail 2 "--cosign 与 --skip-signature-check 不能同时使用" "--cosign and --skip-signature-check exclude each other"
  fi
  if [ -f SHA256SUMS.sigstore.json ]; then
    [ -n "$identity" ] || fail 4 "BUNDLE.json 未写明签名者身份" "BUNDLE.json names no signer identity"
    if [ -z "$cosign" ] && [ "$skip_signature" -eq 0 ]; then cosign="$(command -v cosign || true)"; fi
    if [ -n "$cosign" ]; then
      [ -x "$cosign" ] || fail 2 "找不到 cosign：$cosign" "cosign not found: $cosign"
      "$cosign" verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json --certificate-identity "$identity" \
        --certificate-oidc-issuer "$ISSUER" >&2 \
        || fail 4 "签名核验失败，未安装（cosign 需要 Sigstore 信任根：联网或已准备的缓存）" \
          "signature check failed; nothing installed (cosign needs the Sigstore trust root: network or a prepared cache)"
      say "签名已核验：$identity" "signature verified: $identity"
    elif [ "$skip_signature" -eq 1 ]; then
      say "按要求未在本机核验签名；请确认已在联网电脑上核验" \
        "signature not verified here, as requested; make sure it was verified on a connected machine"
    else
      fail 4 "未找到 cosign：请先在联网电脑上核验签名（见 README.txt），然后加 --skip-signature-check，或用 --cosign 指定" \
        "cosign not found: verify the signature on a connected machine first (see README.txt), then pass --skip-signature-check, or name cosign with --cosign"
    fi
  elif [ "$skip_signature" -eq 1 ]; then
    say "未签名的开发版本，签名未核验" "unsigned development bundle, signature not verified"
  else
    fail 4 "未签名的开发版本；如需继续请加 --skip-signature-check" \
      "unsigned development bundle; pass --skip-signature-check to continue"
  fi
  if [ "$verify_only" -eq 1 ]; then
    say "仅核验，未安装" "verified only, nothing installed"
    exit 0
  fi

  # 3. Platform (A-58): Linux x86_64 with glibc >= 2.28.
  [ "$(uname -s)" = "Linux" ] && [ "$(uname -m)" = "x86_64" ] || fail 2 "仅支持 Linux x86_64" "only Linux x86_64 is supported"
  local glibc=""
  read -r _ glibc <<<"$(getconf GNU_LIBC_VERSION 2>/dev/null || true)" || true
  glibc_supported "${glibc:-}" || fail 2 "需要 glibc 2.28 或更高版本（当前：${glibc:-未知}）" \
    "glibc 2.28 or newer is required (found: ${glibc:-unknown})"

  # 4. Target folder: absolute, new or empty.
  if [ -z "$prefix" ]; then
    [ -n "${XDG_DATA_HOME:-}${HOME:-}" ] || fail 2 "未设置 HOME，请用 --prefix 指定" "HOME is not set; choose the folder with --prefix"
    prefix="${XDG_DATA_HOME:-$HOME/.local/share}/neurogrid/$version"
  fi
  case "$prefix" in
    /*) ;;
    *) fail 2 "安装文件夹须为绝对路径：$prefix" "the install folder must be an absolute path: $prefix" ;;
  esac
  prefix="${prefix%/}"
  local created=1
  if [ -e "$prefix" ]; then
    [ -d "$prefix" ] && [ -z "$(ls -A "$prefix")" ] || fail 2 "目标已存在且不为空：$prefix（新版本请装入新文件夹）" \
      "target exists and is not empty: $prefix (install a new version into a new folder)"
    created=0
  fi
  [ -n "$max_path" ] || fail 3 "BUNDLE.json 不完整" "BUNDLE.json incomplete"

  # 5. Install offline: interpreter, venv, wheelhouse with hashes, bytecode compiled at install (A-48).
  INSTALL_DONE=0
  INSTALL_PREFIX="$prefix"
  INSTALL_CREATED="$created"
  trap 'if [ "$INSTALL_DONE" -eq 0 ] && [ "$INSTALL_CREATED" -eq 1 ]; then rm -rf -- "$INSTALL_PREFIX"; fi' EXIT
  mkdir -p "$prefix"
  cp -a "$bundle/python" "$prefix/python"
  export UV_OFFLINE=1 UV_NO_CONFIG=1 UV_PYTHON_DOWNLOADS=never UV_NO_PROGRESS=1 UV_CACHE_DIR="$prefix/.uv-cache"
  # uv hands the files to compile to the interpreter through a pipe: UTF-8 for prefixes with Chinese characters
  # (on Windows the ANSI code page made the compilation silently skip every file; A-48).
  export PYTHONIOENCODING=utf-8
  "$bundle/uv/uv" venv --quiet --python "$prefix/python/bin/python3.12" "$prefix/venv" \
    || fail 2 "创建虚拟环境失败" "creating the virtual environment failed"
  "$bundle/uv/uv" pip sync --quiet --python "$prefix/venv/bin/python" --no-index --find-links "$bundle/wheels" \
    --require-hashes --no-build --compile-bytecode --link-mode copy "$bundle/requirements.lock.txt" \
    || fail 2 "离线安装失败" "offline installation failed"
  rm -rf -- "$UV_CACHE_DIR"

  # 6. Launcher (exit codes pass through; nothing is set for DENO_DIR, which NeuroGrid sets per run, A-06/A-54),
  #    the PDF browser installer and the bundle's BUNDLE.json: next to python/ and tools/ it marks this folder as
  #    an offline-bundle installation, so a missing PDF browser is reported with the bundled command (D-08).
  mkdir -p "$prefix/bin" "$prefix/tools"
  cat >"$prefix/bin/neurogrid" <<'EOF'
#!/bin/sh
# NeuroGrid launcher of the offline bundle. Moving the install folder breaks the venv: reinstall instead.
unset PYTHONPATH PYTHONHOME
here="$(dirname "$(readlink -f "$0")")"
exec "$here/../venv/bin/neurogrid" "$@"
EOF
  chmod 755 "$prefix/bin/neurogrid"
  cp "$bundle/tools/install_pdf_browser.py" "$prefix/tools/install_pdf_browser.py"
  cp "$bundle/BUNDLE.json" "$prefix/BUNDLE.json"

  # 7. Self-test.
  "$prefix/bin/neurogrid" --help >/dev/null || fail 2 "安装后自检失败" "self-test after installation failed"
  INSTALL_DONE=1

  # 8. Optional: PDF browser from a zip the customer provides, into NeuroGrid's own browser folder (D-08).
  if [ -n "$pdf_zip" ]; then
    "$prefix/python/bin/python3.12" -I "$prefix/tools/install_pdf_browser.py" --from-zip "$pdf_zip" \
      --sha256 "$(printf '%s' "$pdf_sha" | tr 'A-F' 'a-f')" \
      || fail 2 "NeuroGrid 已安装，但 PDF 浏览器未安装" "NeuroGrid is installed, but the PDF browser is not"
    say "PDF 浏览器已安装；它还需要系统库（见 docs/installation.html）" \
      "PDF browser installed; it also needs system libraries (see docs/installation.html)"
  fi

  say "已安装：$prefix/bin/neurogrid" "installed: $prefix/bin/neurogrid"
  say "结果只写入 --out 指定的位置，不会上传任何数据" "results are written only where --out points; nothing is uploaded"
  # The PDF browser lies outside the prefix: NEUROGRID_PDF_BROWSER_DIR or NeuroGrid's default folder (D-08).
  local pdf_folder="\${XDG_DATA_HOME:-~/.local/share}/neurogrid/pdf-browser"
  [ -z "${NEUROGRID_PDF_BROWSER_DIR:-}" ] || pdf_folder="$NEUROGRID_PDF_BROWSER_DIR"
  say "卸载：删除文件夹 $prefix（若装过 PDF 浏览器，另删 $pdf_folder）" \
    "uninstall: delete the folder $prefix (and $pdf_folder if the PDF browser was installed)"
  printf '%s\n' "使用 NeuroGrid 进行的预检。不构成国家药品监督管理局（NMPA）法规意义上的符合性评价。"
  printf '%s\n' "Pre-check with NeuroGrid. Not a conformity assessment within the meaning of NMPA regulations."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
