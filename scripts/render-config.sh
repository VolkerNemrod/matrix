#!/usr/bin/env bash
# Tworzy synapse/homeserver.yaml i nginx/conf.d/matrix.conf ze wzorow *.example, podstawiajac domene
# z MATRIX_DOMAIN (plik .env; domyslnie matrix.local).
# Uruchom RAZ, PRZED wpisaniem hasel do homeserver.yaml (README, krok 5):  bash scripts/render-config.sh
# Skrypt NIE nadpisuje istniejacych plikow (zeby nie skasowac wpisanych hasel).
# Nazwy plikow matrix.local.log.config i matrix.local.signing.key zostaja bez zmian (to nazwy plikow, nie domena).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "BLAD: brak pliku .env (najpierw: cp .env.example .env i ustaw MATRIX_DOMAIN)." >&2
  exit 1
fi

MATRIX_DOMAIN=matrix.local
v=$(grep -E '^MATRIX_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '\r"' || true)
if [ -n "$v" ]; then MATRIX_DOMAIN="$v"; fi
if ! [[ "$MATRIX_DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]; then
  echo "BLAD: MATRIX_DOMAIN='$MATRIX_DOMAIN' - dozwolone tylko male litery, cyfry, kropki i myslniki." >&2
  exit 1
fi
echo "Domena: $MATRIX_DOMAIN"

render() {
  local src="$1" dst="$2"
  if [ -e "$dst" ]; then
    echo "POMINIETO: $dst juz istnieje (nie nadpisuje; usun go, jesli chcesz wygenerowac od nowa)."
    return 0
  fi
  sed -e 's/matrix\.local\.log\.config/@@LOGCFG@@/g' \
      -e 's/matrix\.local\.signing\.key/@@SIGNKEY@@/g' \
      -e "s/matrix\.local/${MATRIX_DOMAIN}/g" \
      -e 's/@@LOGCFG@@/matrix.local.log.config/g' \
      -e 's/@@SIGNKEY@@/matrix.local.signing.key/g' \
      "$src" > "$dst"
  echo "Utworzono: $dst"
}

render synapse/homeserver.yaml.example synapse/homeserver.yaml
render nginx/conf.d/matrix.conf.example nginx/conf.d/matrix.conf

echo
echo "Gotowe. Dalej: wpisz hasla (README, krok 5.1) w .env i synapse/homeserver.yaml."
echo "Na kazdym kliencie dopisz do pliku hosts:  <IP_VM_lub_TAILSCALE>   ${MATRIX_DOMAIN}"
