#!/bin/sh
set -eu

OWNER="${OWNER:-gongahkia}"
REPO="${REPO:-gocli-poor}"
BIN_NAME="gocli-poor"
VERSION="${VERSION:-latest}"
INSTALL_DIR="${INSTALL_DIR:-}"

usage() {
  printf '%s\n' "usage: install.sh [--uninstall]"
}

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'missing required command: %s\n' "$1" >&2
    exit 1
  }
}

target_os() {
  case "$(uname -s)" in
    Darwin) printf 'darwin' ;;
    Linux) printf 'linux' ;;
    *) printf 'unsupported OS: %s\n' "$(uname -s)" >&2; exit 1 ;;
  esac
}

target_arch() {
  case "$(uname -m)" in
    x86_64|amd64) printf 'amd64' ;;
    arm64|aarch64) printf 'arm64' ;;
    *) printf 'unsupported arch: %s\n' "$(uname -m)" >&2; exit 1 ;;
  esac
}

latest_tag() {
  latest_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://github.com/${OWNER}/${REPO}/releases/latest")"
  printf '%s\n' "${latest_url##*/}"
}

pick_install_dir() {
  if [ -n "$INSTALL_DIR" ]; then
    printf '%s\n' "$INSTALL_DIR"
  elif [ -d /usr/local/bin ] && [ -w /usr/local/bin ]; then
    printf '%s\n' "/usr/local/bin"
  else
    printf '%s\n' "${HOME}/.local/bin"
  fi
}

checksum_cmd() {
  if command -v shasum >/dev/null 2>&1; then
    printf 'shasum'
  elif command -v sha256sum >/dev/null 2>&1; then
    printf 'sha256sum'
  else
    printf 'missing required command: shasum or sha256sum\n' >&2
    exit 1
  fi
}

verify_checksum() {
  verify_file="$1"
  verify_checksums="$2"
  verify_cmd="$(checksum_cmd)"
  if [ "$verify_cmd" = "shasum" ]; then
    verify_sum="$(shasum -a 256 "$verify_file" | awk '{print $1}')"
  else
    verify_sum="$(sha256sum "$verify_file" | awk '{print $1}')"
  fi
  awk -v want_file="$(basename "$verify_file")" -v got="$verify_sum" '
    $2 == want_file { if ($1 == got) found=1; else bad=1 }
    END { exit bad ? 2 : found ? 0 : 1 }
  ' "$verify_checksums" || {
    printf 'checksum verification failed for %s\n' "$(basename "$verify_file")" >&2
    exit 1
  }
}

uninstall() {
  if [ -n "$INSTALL_DIR" ]; then
    dir="$INSTALL_DIR"
    target="${dir}/${BIN_NAME}"
    if [ -f "$target" ]; then
      rm -f "$target"
      printf 'removed %s\n' "$target"
    else
      printf '%s not installed at %s\n' "$BIN_NAME" "$target"
    fi
    return
  fi
  for dir in /usr/local/bin "${HOME}/.local/bin"; do
    target="${dir}/${BIN_NAME}"
    if [ -f "$target" ]; then
      rm -f "$target"
      printf 'removed %s\n' "$target"
    fi
  done
  if command -v "$BIN_NAME" >/dev/null 2>&1; then
    printf '%s still exists at %s\n' "$BIN_NAME" "$(command -v "$BIN_NAME")" >&2
  fi
}

install() {
  need curl
  need tar
  need awk

  os="$(target_os)"
  arch="$(target_arch)"
  tag="$VERSION"
  if [ "$tag" = "latest" ]; then
    tag="$(latest_tag)"
  fi
  version="${tag#v}"
  archive="${REPO}_${version}_${os}_${arch}.tar.gz"
  url="https://github.com/${OWNER}/${REPO}/releases/download/${tag}/${archive}"
  checksum_url="https://github.com/${OWNER}/${REPO}/releases/download/${tag}/checksums.txt"
  dir="$(pick_install_dir)"
  target="${dir}/${BIN_NAME}"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  mkdir -p "$dir"
  curl -fsSL "$url" -o "${tmp}/${archive}"
  curl -fsSL "$checksum_url" -o "${tmp}/checksums.txt"
  verify_checksum "${tmp}/${archive}" "${tmp}/checksums.txt"
  tar -xzf "${tmp}/${archive}" -C "$tmp" "$BIN_NAME"
  command install -m 0755 "${tmp}/${BIN_NAME}" "$target"
  "$target" --version
  printf 'installed %s\n' "$target"
}

case "${1:-}" in
  --uninstall) uninstall ;;
  -h|--help) usage ;;
  "") install ;;
  *) usage >&2; exit 1 ;;
esac
