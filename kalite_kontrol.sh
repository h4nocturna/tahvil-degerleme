#!/usr/bin/env bash
# Kalite kontrol: black + ruff + mypy + pytest (Linux/macOS / CI uyumlu).
# Kullanım:  ./kalite_kontrol.sh           (yalnızca denetim)
#            ./kalite_kontrol.sh --duzelt  (black/ruff otomatik düzeltme)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  PYTHON="$(command -v python)"
fi

DUZELT=0
if [[ "${1:-}" == "--duzelt" || "${1:-}" == "-Duzelt" ]]; then
  DUZELT=1
fi

hatali=0
run_step() {
  local isim="$1"
  shift
  echo ""
  echo "============================================================"
  echo "  $isim"
  echo "============================================================"
  if "$PYTHON" "$@"; then
    echo "SONUC: $isim temiz gecti."
  else
    echo "SONUC: $isim BASARISIZ"
    hatali=$((hatali + 1))
  fi
}

if [[ "$DUZELT" -eq 1 ]]; then
  run_step "black (formatla)" -m black .
  run_step "ruff (duzelt)" -m ruff check --fix .
else
  run_step "black (denetim)" -m black --check .
  run_step "ruff (denetim)" -m ruff check .
fi
run_step "mypy (tip denetimi)" -m mypy bond_lab
run_step "pytest (birim testleri)" -m pytest tests/ -q

echo ""
if [[ "$hatali" -eq 0 ]]; then
  echo "TUM KALITE KONTROLLERI GECTI."
  exit 0
fi
echo "$hatali adim basarisiz. Yukaridaki ciktilari inceleyin."
exit 1
