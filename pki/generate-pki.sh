#!/usr/bin/env bash
# Generuje Root CA oraz certyfikat serwera dla domeny z MATRIX_DOMAIN (plik .env; domyślnie matrix.local).
# Uruchom na serwerze w katalogu projektu:  bash pki/generate-pki.sh
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p ../certs

# Domena z .env (domyślnie matrix.local)
MATRIX_DOMAIN=matrix.local
if [ -f ../.env ]; then
  v=$(grep -E '^MATRIX_DOMAIN=' ../.env | tail -1 | cut -d= -f2- | tr -d '\r"' || true)
  if [ -n "$v" ]; then MATRIX_DOMAIN="$v"; fi
fi
if ! [[ "$MATRIX_DOMAIN" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]; then
  echo "BŁĄD: MATRIX_DOMAIN='$MATRIX_DOMAIN' – dozwolone tylko małe litery, cyfry, kropki i myślniki." >&2
  exit 1
fi
echo "Domena: $MATRIX_DOMAIN"

# Root CA (klucz rootCA.key zostaje w pki/ – NIE trafia do kontenerów)
openssl genrsa -out rootCA.key 4096
openssl req -x509 -new -nodes -key rootCA.key -sha256 -days 3650 \
  -subj "/CN=Matrix PoC Root CA - ${MATRIX_DOMAIN}" -out rootCA.pem

# Certyfikat serwera z SAN z v3.ext (matrix.local w v3.ext jest podmieniane na MATRIX_DOMAIN)
sed "s/matrix\.local/${MATRIX_DOMAIN}/g" v3.ext > v3.rendered.ext
openssl genrsa -out matrix.key 2048
openssl req -new -key matrix.key -subj "/CN=${MATRIX_DOMAIN}" -out matrix.csr
openssl x509 -req -in matrix.csr -CA rootCA.pem -CAkey rootCA.key -CAcreateserial \
  -out matrix.crt -days 825 -sha256 -extfile v3.rendered.ext
rm -f v3.rendered.ext

# Pliki dla Nginx + rootCA.pem do rozdania na Windows
cp matrix.crt matrix.key ../certs/
cp rootCA.pem ../certs/

echo "Gotowe: certs/matrix.crt, certs/matrix.key, certs/rootCA.pem (ten ostatni zainstaluj na Windows)"
