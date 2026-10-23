# Szkic: Coturn / WebRTC (rozmowy A/V) – telefon i druga lokalizacja

> ⚠️ **Status: szkic z 2026-10-17, NIEWDROŻONY i NIEPRZETESTOWANY.** Powstał z lektury `docker-compose.yml` i
> `synapse/homeserver.yaml.example`; nic nie zmieniono na VM ani we wzorach konfiguracji. Test A/V jest w README
> wciąż oznaczony jako niepotwierdzony.

## Stan obecny (z plików projektu)

- Coturn (`docker-compose.yml`, usługa `coturn`): `network_mode: host`, port `3478`, relay UDP `49160–49200`,
  uwierzytelnianie wspólnym sekretem (`--use-auth-secret`, `${TURN_SECRET}`), `--external-ip=${TS_IP}`, bez TLS.
- Synapse (`homeserver.yaml.example`): `turn_uris` wskazują `turn:matrix.local:3478` (UDP i TCP),
  `turn_shared_secret` = `TURN_SECRET`, `turn_user_lifetime: 86400000`, `turn_allow_guests: false`.
- Skutek: Windows z wpisem w `hosts` rozwiąże `matrix.local`, **telefon (bez `hosts`) nie** – rozmowa z telefonu
  nie ma jak dotrzeć do TURN. To samo dotyczy komputera w innej lokalizacji (README, 9.3).

## Proponowana zmiana (PoC)

Synapse przekazuje **jedną** listę `turn_uris` wszystkim klientom, więc adres musi działać wszędzie. Nazwa MagicDNS
z Tailscale działa na telefonie i na Windowsie (oba muszą mieć włączone Tailscale, co i tak jest warunkiem połączenia).

`synapse/homeserver.yaml` (lokalny plik, nie wzór):

```yaml
turn_uris:
  - "turn:<PELNA-NAZWA-TS>:3478?transport=udp"
  - "turn:<PELNA-NAZWA-TS>:3478?transport=tcp"
```

Potem `docker compose restart synapse`. Coturn i sekret zostają bez zmian. `--realm=matrix.local` w Coturn nie musi
się rozwiązywać (to tylko etykieta uwierzytelniania), więc można go zostawić.

Wariant awaryjny, gdyby MagicDNS zawodził: wpisać wprost `<IP_TAILSCALE>` zamiast nazwy (adres musi być stały).

## Do sprawdzenia przed testem

1. **Co Synapse faktycznie rozdaje klientom** – zapytanie `GET /_matrix/client/v3/voip/turnServer` z tokenem
   użytkownika (w README, sekcja „Token administratora…”, jest przykład logowania w PowerShellu). Odpowiedź ma
   zawierać nowe `uris`, `username` i `password`.
2. **Zapora VM i ACL Tailscale** – Coturn potrzebuje na adresie Tailscale serwera: `3478` (UDP i TCP) oraz
   `49160–49200` (UDP). Sprawdź `ufw status` (README: zapora istnieje) i ewentualne reguły w panelu Tailscale.
3. **Łączność z klienta** – `tailscale ping <PELNA-NAZWA-TS>` (README 9.3, krok 4).
4. **Logi Coturn w trakcie połączenia** – `docker compose logs -f --tail=0 coturn`; przy udanym połączeniu
   powinny pojawić się wpisy o utworzonej alokacji (komunikaty `ALLOCATE`). Brak wpisów = połączenie nie dochodzi
   do Coturn (DNS, zapora albo ACL).
5. ⚠️ **Hipoteza do sprawdzenia, jeśli alokacja jest, a media nie płyną:** Coturn ma listy dozwolonych/zabronionych
   adresów peerów (`denied-peer-ip`, `allowed-peer-ip`); adresy Tailscale (zakres `100.64.0.0/10`) mogą wymagać
   wpisu. Nie zmieniaj niczego, dopóki objaw tego nie wskaże.

## Kolejność testów

1. Dwa konta w jednej sieci lokalnej z Tailscale (dwa profile Elementa Desktop, `--profile`) – rozmowa 1:1.
2. Telefon ↔ komputer, obie strony z Tailscale.
3. Komputer w innej sieci (README, 9.3) – dopiero gdy 1 i 2 działają.
4. Najpierw zwykłe wiadomości, potem A/V, żeby odróżnić problem z Tailscale od problemu z Coturn.

## Produkcja (osobno, nie PoC)

- Prawdziwy adres i DNS zamiast MagicDNS, publiczny `external-ip` albo adres z DMZ, reguły zapory dla UDP `3478` i
  zakresu relay.
- **TURNS** (TLS, zwykle port `5349` lub `443` dla restrykcyjnych sieci firmowych) z certyfikatem zaufanym bez ręcznej
  instalacji; wymaga zmiany `turn_uris` na `turns:` i opcji TLS w Coturn.
- Ograniczenie zakresu relay i limity (`--total-quota`, `--user-quota`) do rozmiaru kilkuset użytkowników – niesprawdzone.
- Rozmowy grupowe (Element Call / MatrixRTC) to osobny temat i inna infrastruktura; ten szkic dotyczy tylko 1:1.
