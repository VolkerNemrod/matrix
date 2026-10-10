#!/usr/bin/env bash
# Generuje Root CA oraz certyfikat serwera dla matrix.local.
# Uruchom na serwerze w katalogu projektu:  bash pki/generate-pki.sh
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p ../certs

# Root CA (klucz rootCA.key zostaje w pki/ – NIE trafia do kontenerów)
openssl genrsa -out rootCA.key 4096
openssl req -x509 -new -nodes -key rootCA.key -sha256 -days 3650 \
  -subj "/CN=Matrix PoC Root CA" -out rootCA.pem

# Certyfikat serwera z SAN z v3.ext
openssl genrsa -out matrix.key 2048
openssl req -new -key matrix.key -subj "/CN=matrix.local" -out matrix.csr
openssl x509 -req -in matrix.csr -CA rootCA.pem -CAkey rootCA.key -CAcreateserial \
  -out matrix.crt -days 825 -sha256 -extfile v3.ext

# Pliki dla Nginx + rootCA.pem do rozdania na Windows
cp matrix.crt matrix.key ../certs/
cp rootCA.pem ../certs/

echo "Gotowe: certs/matrix.crt, certs/matrix.key, certs/rootCA.pem (ten ostatni zainstaluj na Windows)"
