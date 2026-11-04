# Rozwiązywanie problemów

> Część dokumentacji projektu Matrix PoC. Patrz też [README](../README.md) i [docs/administrowanie.md](administrowanie.md).

## ✅ Zweryfikowane

**1. `-bash: pki/generate-pki.sh: Permission denied`**
- **Przyczyna:** komenda wpisana jako `$bash pki/generate-pki.sh`. Znak `$` na początku robi z `bash` pustą
  zmienną, więc system próbuje uruchomić sam plik, który nie ma prawa wykonywania.
- **Rozwiązanie:** wpisz bez `$`: `bash pki/generate-pki.sh`.

**2. `ping matrix.local` → „could not find host", przeglądarka nie otwiera strony**
- **Przyczyna:** wpis w pliku `hosts` nie został zapisany (Notatnik otwarty, ale bez Ctrl+S). Inne możliwe
  przyczyny: brak uprawnień administratora, plik zapisany jako `hosts.txt`.
- **Diagnoza:** `Get-Content C:\Windows\System32\drivers\etc\hosts` – czy jest tam linia z `matrix.local`.
- **Rozwiązanie:** zapisz plik albo dopisz z PowerShella jako administrator:
  `Add-Content C:\Windows\System32\drivers\etc\hosts "`n<IP_TAILSCALE>   matrix.local"`,
  potem `ipconfig /flushdns`.

**3. Element (na komputerze bez wpisu w `hosts`) loguje się, ale „Wstępna synchronizacja – czekanie na odpowiedź serwera" wisi bez końca**
- **Objawy:** w logu Nginx (`docker compose logs --tail=60 proxy | grep -E "sync|keys|login"`) są tylko
  dwa wpisy `GET` i `POST /_matrix/client/r0/login` z kodem 200, potem nic – ani `sync`, ani `keys`.
  Serwer jest bezczynny (`docker stats`), a przeglądarka klienta ładuje `/_matrix/client/versions`.
- **Przyczyna:** w `homeserver.yaml` było `public_baseurl: "https://matrix.local/"`. Synapse dokleja ten adres
  do odpowiedzi na logowanie, więc Element po zalogowaniu przełączał się na `matrix.local`, którego klient
  nie rozwiązuje – kolejne zapytania nie docierały do serwera.
- **Rozwiązanie:** `public_baseurl: "https://<PELNA-NAZWA-TS>/"`, `docker compose restart synapse`,
  wylogowanie (albo wyczyszczenie danych Elementa) i ponowne logowanie na `https://<PELNA-NAZWA-TS>`.
- **Wskazówka:** `sudo ss -tn | grep IP_KLIENTA` na VM **nic nie pokazuje**, bo Nginx działa w kontenerze –
  do podglądu zapytań użyj logów (`docker compose logs -f --tail=0 proxy`).

**4. Skrypt (`setup_directory.py`, `provision_synapse_users.py`) kończy się `HTTP 429 M_LIMIT_EXCEEDED` przy logowaniu administratora**
- **Objawy:** `Logowanie admina '<LOGIN_ADMINA>' nie powiodło się: HTTP 429 ... retry_after_ms`.
- **Przyczyna:** limiter prób logowania w Synapse (to nie jest błąd hasła). Każde uruchomienie skryptu loguje
  to samo konto, a kilka uruchomień pod rząd wydłuża czas oczekiwania (2026-10-14: z kilkunastu sekund do ok.
  4 minut).
- **Rozwiązanie:** poczekaj. Skrypt sam czeka i ponawia logowanie (wypisuje `limit prób logowania, czekam Ns`) –
  nie przerywaj go i nie uruchamiaj drugiego równolegle, bo to wydłuża czekanie. Ewentualnie `docker compose
  restart synapse` czyści licznik.

**5. Admin API zwraca `404 Not Found` (od nginx, nie od Synapse)**
- **Przyczyna:** nginx nie przepuszcza `/_synapse/admin` (stary `matrix.conf` na VM).
- **Rozwiązanie:** patrz [Etap 0](administrowanie.md#etap-0), punkt 2 (dopisać `|/_synapse/admin` do regexu i przeładować nginx).

**6. Synapse restartuje się w kółko: `PermissionError: [Errno 13] Permission denied: '/data/matrix.local.signing.key'`** (potwierdzone 2026-10-29)
- **Przyczyna:** Synapse działa w kontenerze jako użytkownik `991`, a katalog `synapse/` (zamontowany jako `/data`) należy do Ciebie, więc
  Synapse nie może zapisać klucza podpisu. `matrix-proxy` też się wtedy restartuje (nie widzi upstreamu `synapse`) – po naprawie
  Synapse'a podniesie się sam.
- **Rozwiązanie** (to samo jest w [README – krok 7](../README.md#krok-7--uruchomienie-usług) przed pierwszym startem):

  ```bash
  cd /opt/matrix
  sudo chown 991:991 synapse
  docker compose restart synapse
  sleep 15
  docker compose restart proxy
  docker compose ps
  ```

  Plik `synapse/homeserver.yaml` musi zostać czytelny dla innych (`chmod 644`).

## ⚠️ Możliwe, niesprawdzone (zajrzyj tu dopiero, jeśli zobaczysz taki objaw)

**7. Błędy `\r` przy uruchamianiu skryptu** – windowsowe końce linii; naprawa:
`sed -i 's/\r$//' pki/generate-pki.sh pki/v3.ext`.

**8. Nginx (`matrix-proxy`) nie startuje** – zwykle brakuje certyfikatów w `/opt/matrix/certs`. Sprawdź
`ls certs` i powtórz [README – krok 6](../README.md#krok-6--certyfikaty-pki). Po dodaniu bloków dla Tailscale brakujące pliki
`<PELNA-NAZWA-TS>.crt` i `.key` też zatrzymają Nginx.

**9. Pracownik ma w książce adresowej „Bez działu” albo nie ma działu w nazwie wyświetlanej** – sprawdź w panelu LLDAP, czy konto ma grupę-dział
(4 konta testowe nie mają: `j.kowalski`, `a.nowak`, `t.perlik`, `p.wisniewski`); potem
`provision_synapse_users.py` i `setup_directory.py`.

**10. Panel Synapse Admin nie otwiera się pod `http://localhost:8080`** – sprawdź po kolei: czy okno z tunelem SSH jest
otwarte, czy na VM `docker compose ps` pokazuje `matrix-proxy` i `matrix-synapse-admin` jako `Up`, czy
`ss -tlnp | grep 8080` pokazuje `127.0.0.1:8080`, oraz `docker compose logs --tail=50 proxy synapse-admin`.
Po błędzie `host not found in upstream "synapse-admin"` uruchom `docker compose up -d` (kontener panelu musi istnieć).
