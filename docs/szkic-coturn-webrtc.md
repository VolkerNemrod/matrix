# Szkic: Coturn / WebRTC (rozmowy A/V) – druga lokalizacja

> ⚠️ **Status: szkic z 2026-10-17, uzupełniony 2026-11-15 po odpięciu od Tailscale; NIEWDROŻONY i NIEPRZETESTOWANY.**
> Powstał z lektury `docker-compose.yml` i `synapse/homeserver.yaml.example`. Test A/V jest w README wciąż oznaczony jako
> niepotwierdzony.

## Stan obecny (z plików projektu)

- Coturn (`docker-compose.yml`, usługa `coturn`): `network_mode: host`, port `3478`, relay UDP `49160–49200`,
  uwierzytelnianie wspólnym sekretem (`--use-auth-secret`, `${TURN_SECRET}`), `--external-ip=${SERVER_IP}`, bez TLS.
- Synapse (`homeserver.yaml.example`): `turn_uris` wskazują `turn:matrix.local:3478` (UDP i TCP), czyli domenę serwera
  (po `render-config.sh`: `<DOMENA>`); `turn_shared_secret` = `TURN_SECRET`, `turn_user_lifetime: 86400000`,
  `turn_allow_guests: false`.
- Każdy klient (także w innej lokalizacji, [README, krok 9.2](../README.md#92-komputer-w-innej-lokalizacji-u-kolegi))
  ma wpis w `hosts` z adresem serwera, więc rozwiązuje `<DOMENA>` także dla TURN. **Żadna zmiana `turn_uris` nie jest
  potrzebna.** (Wcześniejszy pomysł z nazwą MagicDNS z Tailscale odpadł razem z wariantem dostępu po tej nazwie.)

## Jeden zewnętrzny adres

`SERVER_IP` w `.env` (`--external-ip` w Coturn) to **jeden** adres, który Coturn podaje klientom jako adres relay. Musi to
być adres serwera widziany z sieci klienta:

- test przez Tailscale: adres Tailscale serwera (`tailscale ip -4`),
- VPN firmy: adres serwera z tego VPN-u,
- sieć lokalna: adres LAN serwera.

Jeśli równocześnie testujesz kilka sieci (np. LAN i Tailscale), jeden adres może nie obsłużyć wszystkich – ⚠️ niesprawdzone;
w takim razie testuj A/V w jednej sieci naraz.

Po zmianie `SERVER_IP`: `docker compose up -d` (odtworzy kontener `coturn`).

## Do sprawdzenia przed testem

1. **Co Synapse faktycznie rozdaje klientom** – zapytanie `GET /_matrix/client/v3/voip/turnServer` z tokenem
   użytkownika. Odpowiedź ma zawierać `uris`, `username` i `password`.
2. **Zapora VM i ACL sieci VPN** – Coturn potrzebuje na adresie `SERVER_IP`: `3478` (UDP i TCP) oraz `49160–49200` (UDP).
   Sprawdź `ufw status` i ewentualne reguły w VPN (w Tailscale: panel, ACL).
3. **Łączność z klienta** – `Test-NetConnection <IP_SERWERA> -Port 3478` albo `tailscale ping <IP_SERWERA>`
   ([klienci-dodatkowe.md](klienci-dodatkowe.md), sekcja „Dostęp do sieci”).
4. **Logi Coturn w trakcie połączenia** – `docker compose logs -f --tail=0 coturn`; przy udanym połączeniu powinny pojawić
   się wpisy o utworzonej alokacji (komunikaty `ALLOCATE`). Brak wpisów = połączenie nie dochodzi do Coturn (DNS/`hosts`,
   zapora albo ACL).
5. ⚠️ **Hipoteza do sprawdzenia, jeśli alokacja jest, a media nie płyną:** Coturn ma listy dozwolonych/zabronionych
   adresów peerów (`denied-peer-ip`, `allowed-peer-ip`); adresy z zakresu VPN (np. Tailscale `100.64.0.0/10`) mogą wymagać
   wpisu. Nie zmieniaj niczego, dopóki objaw tego nie wskaże.

## Kolejność testów

1. Dwa konta w jednej sieci (dwa profile Elementa Desktop, `--profile`) – rozmowa 1:1.
2. Komputer w innej sieci ([README, krok 9.2](../README.md#92-komputer-w-innej-lokalizacji-u-kolegi)) – dopiero gdy 1 działa.
3. Najpierw zwykłe wiadomości, potem A/V, żeby odróżnić problem z siecią/VPN od problemu z Coturn.

## Produkcja (osobno, nie PoC)

- Prawdziwy adres i DNS zamiast wpisów w `hosts`, publiczny `external-ip` albo adres z DMZ, reguły zapory dla UDP `3478` i
  zakresu relay.
- **TURNS** (TLS, zwykle port `5349` lub `443` dla restrykcyjnych sieci firmowych) z certyfikatem zaufanym bez ręcznej
  instalacji; wymaga zmiany `turn_uris` na `turns:` i opcji TLS w Coturn.
- Ograniczenie zakresu relay i limity (`--total-quota`, `--user-quota`) do rozmiaru kilkuset użytkowników – niesprawdzone.
- Rozmowy grupowe (Element Call / MatrixRTC) to osobny temat i inna infrastruktura; ten szkic dotyczy tylko 1:1.
