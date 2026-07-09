#!/usr/bin/env bash
# Remove o binário do animes-tui instalado pelo install.sh.
#
# Uso:
#   ./uninstall.sh
#   ./uninstall.sh --prefix DIR
#   ./uninstall.sh --purge          # também apaga config, cache e histórico
#
# Remoto:
#   curl -fsSL https://cdn.jsdelivr.net/gh/renidantass/anime-tui@main/uninstall.sh | bash
#   curl -fsSL .../uninstall.sh | bash -s -- --purge
#
set -euo pipefail

APP_NAME="animes-tui"
INSTALL_PREFIX="${XDG_BIN_HOME:-$HOME/.local/bin}"
PURGE=0

# Dados gerados em runtime (não só o binário)
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/animes-tui"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/animes-tui"
HISTORY_DIR="$HOME/.anime-feed-reader"

usage() {
  cat <<EOF
Uso: $(basename "${0:-uninstall.sh}") [opções]

Opções:
  --prefix DIR   Diretório onde o binário foi instalado (padrão: \$HOME/.local/bin)
  --purge        Também remove config, cache e histórico
  -h, --help     Esta ajuda

Exemplos:
  ./uninstall.sh
  ./uninstall.sh --prefix "\$HOME/bin"
  ./uninstall.sh --purge
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      INSTALL_PREFIX="${2:?--prefix requer um diretório}"
      shift 2
      ;;
    --purge) PURGE=1; shift ;;
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
warn(){ printf '\033[1;33m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }

expand_path() {
  local p="$1"
  p="${p/#\~/$HOME}"
  printf '%s\n' "$p"
}

remove_path() {
  local path="$1"
  path="$(expand_path "$path")"
  if [[ -e "$path" || -L "$path" ]]; then
    log "Removendo $path…"
    rm -rf -- "$path"
    ok "Removido: $path"
    return 0
  fi
  return 1
}

main() {
  echo "animes-tui — uninstall"
  echo

  INSTALL_PREFIX="$(expand_path "$INSTALL_PREFIX")"
  local bin="$INSTALL_PREFIX/$APP_NAME"
  local removed=0

  # 1) Binário
  if remove_path "$bin"; then
    removed=1
  else
    # fallback: se estiver no PATH noutro sítio
    if command -v "$APP_NAME" >/dev/null 2>&1; then
      local found
      found="$(command -v "$APP_NAME")"
      if [[ -f "$found" || -L "$found" ]]; then
        if remove_path "$found"; then
          removed=1
        fi
      fi
    fi
  fi

  if [[ "$removed" -eq 0 ]]; then
    warn "Binário não encontrado em $bin"
  fi

  # 2) Dados do usuário (opcional)
  if [[ "$PURGE" -eq 1 ]]; then
    log "Limpando dados do usuário (--purge)…"
    remove_path "$CONFIG_DIR" || true
    remove_path "$CACHE_DIR" || true
    remove_path "$HISTORY_DIR" || true
  else
    local leftovers=()
    [[ -e "$(expand_path "$CONFIG_DIR")" ]] && leftovers+=("$CONFIG_DIR")
    [[ -e "$(expand_path "$CACHE_DIR")" ]] && leftovers+=("$CACHE_DIR")
    [[ -e "$(expand_path "$HISTORY_DIR")" ]] && leftovers+=("$HISTORY_DIR")
    if [[ ${#leftovers[@]} -gt 0 ]]; then
      echo
      warn "Dados do usuário preservados. Para apagar tudo:"
      echo "  $0 --purge"
      for p in "${leftovers[@]}"; do
        echo "    - $p"
      done
    fi
  fi

  echo
  if [[ "$removed" -eq 1 || "$PURGE" -eq 1 ]]; then
    ok "Desinstalação concluída."
  else
    warn "Nada a remover. Use --prefix se instalou noutro diretório."
    exit 1
  fi
}

main
