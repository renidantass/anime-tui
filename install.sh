#!/usr/bin/env bash
# Instala animes-tui no usuário (build com PyInstaller → ~/.local/bin).
#
# Instalação direta do terminal (sem clonar manualmente):
#   curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/install.sh | bash
#
# Uso local (já no repositório):
#   ./install.sh
#   ./install.sh --build-only
#   ./install.sh --prefix DIR
#
set -euo pipefail

REPO_URL="${ANIMES_TUI_REPO:-https://github.com/renidantass/anime-tui.git}"
REPO_BRANCH="${ANIMES_TUI_BRANCH:-main}"
APP_NAME="animes-tui"
INSTALL_PREFIX="${XDG_BIN_HOME:-$HOME/.local/bin}"
BUILD_ONLY=0
SKIP_BUILD=0

usage() {
  cat <<EOF
Uso: $(basename "${0:-install.sh}") [opções]

Opções:
  --build-only       Apenas gera o binário (não instala)
  --install-only     Instala o binário já existente em dist/
  --prefix DIR       Destino do binário (padrão: \$HOME/.local/bin)
  -h, --help         Esta ajuda

Instalação remota:
  curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/install.sh | bash

Exemplos locais:
  ./install.sh
  ./install.sh --build-only
  ./install.sh --prefix "\$HOME/bin"
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

# Mensagens em stderr para não poluir capturas como ROOT="$(resolve_root)"
log() { printf '\033[1;34m==>\033[0m %s\n' "$*" >&2; }
ok()  { printf '\033[1;32m==>\033[0m %s\n' "$*" >&2; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "comando não encontrado: $1"
    exit 1
  fi
}

# Dir temporário do clone remoto (limpado no EXIT do shell principal).
# Não pode ser registrado com trap dentro de $() — o subshell apaga o clone
# antes do cd em main.
CLEANUP_TMP=""

cleanup_install_tmp() {
  if [[ -n "${CLEANUP_TMP:-}" && -d "$CLEANUP_TMP" ]]; then
    rm -rf "$CLEANUP_TMP"
  fi
}

# Define ROOT (global). Se curl|bash, clona em tmp e agenda cleanup.
resolve_root() {
  local script_path="${BASH_SOURCE[0]:-}"
  local candidate=""

  if [[ -n "$script_path" && "$script_path" != "bash" && "$script_path" != "/dev/stdin" && "$script_path" != "-" ]]; then
    if [[ -f "$script_path" ]]; then
      candidate="$(cd "$(dirname "$script_path")" && pwd)"
    fi
  fi

  if [[ -n "$candidate" && -f "$candidate/main.py" && -f "$candidate/pyproject.toml" ]]; then
    ROOT="$candidate"
    return 0
  fi

  # Já estamos no root do projeto
  if [[ -f "./main.py" && -f "./pyproject.toml" ]]; then
    ROOT="$(pwd)"
    return 0
  fi

  need_cmd git
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/animes-tui-install.XXXXXX")"
  CLEANUP_TMP="$tmp"
  trap cleanup_install_tmp EXIT

  log "Clonando repositório ($REPO_BRANCH)…"
  git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$tmp/repo" >&2
  if [[ ! -d "$tmp/repo" || ! -f "$tmp/repo/main.py" ]]; then
    err "clone falhou ou repositório incompleto em $tmp/repo"
    exit 1
  fi
  ROOT="$tmp/repo"
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

  # Imports necessários (evitar --collect-all: puxa pygments, setuptools, etc.)
  local hidden=(
    --hidden-import=textual
    --hidden-import=textual.app
    --hidden-import=textual.widgets
    --hidden-import=textual.containers
    --hidden-import=textual.screen
    --hidden-import=rich
    --hidden-import=bs4
    --hidden-import=PIL
    --hidden-import=PIL.Image
    --hidden-import=PIL.ImageEnhance
    --hidden-import=PIL.ImageFile
    --hidden-import=requests
    --hidden-import=app
    --hidden-import=app.infrastructure.sources.animesonlinecc
    --hidden-import=app.infrastructure.sources.goyabu
    --hidden-import=app.infrastructure.sources.topanimes
    --hidden-import=app.infrastructure.sources.source_discovery
  )

  # Só CSS/dados do Textual + submódulos do app (fontes)
  local collect=(
    --collect-data=textual
    --collect-submodules=app
  )

  # Módulos pesados / irrelevantes para o TUI
  local exclude=(
    --exclude-module=pygments
    --exclude-module=setuptools
    --exclude-module=pkg_resources
    --exclude-module=lxml
    --exclude-module=tkinter
    --exclude-module=unittest
    --exclude-module=pydoc
    --exclude-module=doctest
    --exclude-module=test
    --exclude-module=xmlrpc
    --exclude-module=multiprocessing.popen_spawn_win32
    # Codecs Pillow raros em capas de anime (JPEG/PNG/WebP bastam)
    --exclude-module=PIL.AvifImagePlugin
    --exclude-module=PIL.FtexImagePlugin
    --exclude-module=PIL.BlpImagePlugin
    --exclude-module=PIL.McIdasImagePlugin
    --exclude-module=PIL.MicImagePlugin
    --exclude-module=PIL.MpegImagePlugin
    --exclude-module=PIL.Hdf5StubImagePlugin
    --exclude-module=PIL.DdsImagePlugin
    --exclude-module=PIL.FliImagePlugin
    --exclude-module=PIL.GbrImagePlugin
    --exclude-module=PIL.IcnsImagePlugin
    --exclude-module=PIL.IcoImagePlugin
    --exclude-module=PIL.ImImagePlugin
    --exclude-module=PIL.ImtImagePlugin
    --exclude-module=PIL.IptcImagePlugin
    --exclude-module=PIL.PalmImagePlugin
    --exclude-module=PIL.PcdImagePlugin
    --exclude-module=PIL.PdfImagePlugin
    --exclude-module=PIL.PixarImagePlugin
    --exclude-module=PIL.PsdImagePlugin
    --exclude-module=PIL.SgiImagePlugin
    --exclude-module=PIL.SpiderImagePlugin
    --exclude-module=PIL.SunImagePlugin
    --exclude-module=PIL.WalImagePlugin
    --exclude-module=PIL.WmfImagePlugin
    --exclude-module=PIL.XbmImagePlugin
    --exclude-module=PIL.XpmImagePlugin
    --exclude-module=PIL.XVThumbImagePlugin
    --exclude-module=PIL.ImageTk
    --exclude-module=PIL.ImageQt
    --exclude-module=PIL.ImageShow
    --exclude-module=PIL._imagingtk
    --exclude-module=PIL._avif
  )

  local strip_flag=()
  if command -v strip >/dev/null 2>&1; then
    strip_flag=(--strip)
  fi

  log "Gerando binário one-file com PyInstaller (otimizado)…"
  uv run pyinstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name "$APP_NAME" \
    --paths "$ROOT" \
    --workpath "$BUILD_DIR" \
    --distpath "$DIST_DIR" \
    --specpath "$BUILD_DIR" \
    "${strip_flag[@]}" \
    "${hidden[@]}" \
    "${collect[@]}" \
    "${exclude[@]}" \
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
  # Sem $(): resolve_root define ROOT no shell atual (trap de cleanup funciona)
  resolve_root
  if [[ -z "${ROOT:-}" || ! -d "$ROOT" ]]; then
    err "não foi possível resolver o diretório do projeto (ROOT='${ROOT:-}')"
    exit 1
  fi
  cd "$ROOT"

  DIST_DIR="$ROOT/dist"
  BUILD_DIR="$ROOT/build"
  BIN_OUT="$DIST_DIR/$APP_NAME"

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
