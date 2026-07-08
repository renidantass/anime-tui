#!/usr/bin/env bash
# Gera o binário Linux de animes-tui (PyInstaller) e instala no usuário.
#
# Uso:
#   ./build-and-install.sh              # build + instala em ~/.local/bin
#   ./build-and-install.sh --build-only # só gera o binário em dist/
#   ./build-and-install.sh --prefix DIR # outro diretório do usuário
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

APP_NAME="animes-tui"
DIST_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/build"
BIN_OUT="$DIST_DIR/$APP_NAME"
# instalação no usuário por padrão (sem root)
INSTALL_PREFIX="${XDG_BIN_HOME:-$HOME/.local/bin}"
BUILD_ONLY=0
SKIP_BUILD=0

usage() {
  cat <<EOF
Uso: $(basename "$0") [opções]

Opções:
  --build-only       Apenas gera o binário (não instala)
  --install-only     Instala o binário já existente em dist/
  --prefix DIR       Destino do binário (padrão: \$HOME/.local/bin)
  -h, --help         Esta ajuda

Exemplos:
  ./build-and-install.sh
  ./build-and-install.sh --build-only
  ./build-and-install.sh --prefix "\$HOME/bin"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only) BUILD_ONLY=1; shift ;;
    --install-only) SKIP_BUILD=1; shift ;;
    --prefix)
      INSTALL_PREFIX="${2:?--prefix requer um diretório}"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "comando não encontrado: $1"
    exit 1
  fi
}

build_binary() {
  need_cmd uv

  log "Sincronizando ambiente (uv sync)…"
  uv sync

  log "Instalando PyInstaller no ambiente do projeto…"
  uv pip install --quiet "pyinstaller>=6.0"

  log "Limpando builds anteriores…"
  rm -rf "$BUILD_DIR" "$DIST_DIR"
  mkdir -p "$DIST_DIR"

  # Hidden imports comuns com Textual / BS4 / lxml / Pillow
  local hidden=(
    --hidden-import=textual
    --hidden-import=textual.app
    --hidden-import=textual.widgets
    --hidden-import=textual.containers
    --hidden-import=textual.screen
    --hidden-import=rich
    --hidden-import=bs4
    --hidden-import=lxml
    --hidden-import=lxml.etree
    --hidden-import=lxml._elementpath
    --hidden-import=PIL
    --hidden-import=PIL.Image
    --hidden-import=requests
    --hidden-import=app
    --hidden-import=app.infrastructure.sources.animesonlinecc
    --hidden-import=app.infrastructure.sources.goyabu
    --hidden-import=app.infrastructure.sources.topanimes
    --hidden-import=app.infrastructure.sources.source_discovery
  )

  # Dados do Textual (CSS/temas embutidos)
  local collect=(
    --collect-all=textual
    --collect-all=rich
    --collect-submodules=app
  )

  log "Gerando binário one-file com PyInstaller…"
  # shellcheck disable=SC2086
  uv run pyinstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name "$APP_NAME" \
    --paths "$ROOT" \
    --workpath "$BUILD_DIR" \
    --distpath "$DIST_DIR" \
    --specpath "$BUILD_DIR" \
    "${hidden[@]}" \
    "${collect[@]}" \
    "$ROOT/main.py"

  if [[ ! -f "$BIN_OUT" ]]; then
    err "binário não gerado em $BIN_OUT"
    exit 1
  fi

  chmod +x "$BIN_OUT"
  ok "Binário gerado: $BIN_OUT ($(du -h "$BIN_OUT" | cut -f1))"
}

install_binary() {
  if [[ ! -f "$BIN_OUT" ]]; then
    err "binário não encontrado: $BIN_OUT — rode sem --install-only primeiro"
    exit 1
  fi

  local dest="$INSTALL_PREFIX/$APP_NAME"
  local dest_dir
  dest_dir="$(dirname "$dest")"

  # expand ~ se vier no --prefix
  dest_dir="${dest_dir/#\~/$HOME}"
  dest="${dest/#\~/$HOME}"

  if [[ ! -d "$dest_dir" ]]; then
    log "Criando diretório $dest_dir…"
    mkdir -p "$dest_dir"
  fi

  if [[ ! -w "$dest_dir" ]]; then
    err "sem permissão de escrita em $dest_dir (use um prefixo do usuário, ex.: ~/.local/bin)"
    exit 1
  fi

  log "Copiando para $dest…"
  install -m 755 "$BIN_OUT" "$dest"

  ok "Instalado: $dest"

  case ":$PATH:" in
    *":$dest_dir:"*)
      ok "Execute com: $APP_NAME"
      ;;
    *)
      ok "Execute com: $dest"
      echo "    Dica: adicione ao PATH (ex. no ~/.bashrc):"
      echo "      export PATH=\"$dest_dir:\$PATH\""
      ;;
  esac
}

main() {
  echo "animes-tui — build & install (Linux)"
  echo "projeto: $ROOT"
  echo

  if [[ "$SKIP_BUILD" -eq 0 ]]; then
    build_binary
  fi

  if [[ "$BUILD_ONLY" -eq 1 ]]; then
    ok "Build concluído (--build-only). Binário em: $BIN_OUT"
    exit 0
  fi

  install_binary
}

main
