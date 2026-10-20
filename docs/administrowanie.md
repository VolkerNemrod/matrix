# Administrowanie Synapse (podręcznik administratora)

> Część dokumentacji projektu Matrix PoC. Zakłada, że wdrożenie z [README](../README.md) (Część 1, kroki 1–10)
> oraz konta i książka adresowa (Część 2, Etapy 0–2) są gotowe. Tu zbieramy to, co przydaje się na co dzień:
> usuwanie pokoi, konta użytkowników, panel Synapse Admin, restarty i logi, kopie zapasowe, skrypty automatyzujące.
> **Ta sekcja będzie rosła** – nowe automatyzacje i rzeczy „warto mieć pod ręką” dopisuj tutaj.

Szybkie odsyłacze:

- zmiana kont i działów (nowy pracownik, odejście): [README – Aktualizacje w Etapie 1](../README.md#aktualizacje-nowy-pracownik-zmiana-działu-odejście),
- zmiana danych w książce adresowej: [README – Etap 2](../README.md#etap-2), tabela „2.3 Aktualizacja książki”,
- gdy coś nie działa: [Rozwiązywanie problemów](rozwiazywanie-problemow.md).

Synapse nie ma wbudowanego panelu administracyjnego. Zarządzanie odbywa się przez **Admin API** (HTTP),
bezpośrednio w **bazie PostgreSQL** i przez **dokumentację/logi**. Poniżej wszystko, co potrzebne na co dzień.

Do pracy z przeglądarki (konta, pokoje) jest dodatkowo panel
[Synapse Admin](#synapse-admin--panel-www-do-administrowania-serwerem) – działa na tym samym Admin API,
więc skrypty i wywołania z PowerShella nadal działają równolegle.

> Oznaczenia: ✅ = użyte w naszych skryptach albo sprawdzone u nas; ⚠️ = przykład z dokumentacji Synapse,
> niesprawdzony na tym PoC. Przy ⚠️ najpierw spróbuj na koncie testowym.

### Konto administratora ✅

Administrator to zwykłe konto Matrix z flagą `admin`. W PoC jest to `s.lewandowski` (konto testowe z LLDAP,
flaga ustawiona w bazie – patrz [README – Etap 0](../README.md#etap-0)).
Lista administratorów w bazie (🐧 **VM**, `/opt/matrix`):

```bash
docker compose exec postgres psql -U synapse -d synapse -c "select name, admin, deactivated from users where admin = 1;"
```

⚠️ Na produkcji załóż osobne konto serwisowe (patrz [docs/produkcja.md](produkcja.md)).

### Token administratora i wywołania Admin API

Admin API wymaga tokenu (`access_token`) konta z flagą `admin`. Token dostajesz przez zwykłe logowanie
(`POST /_matrix/client/v3/login`) – tak robią nasze skrypty ✅. Przykład z PowerShell (⚠️ składnia nieprzetestowana
w całości; `matrix.local` musi być rozwiązywalne i rootCA zaufane, jak dla Elementa):

🪟 **PC**, PowerShell:

```powershell
$base = "https://matrix.local"
$login = @{
  type = "m.login.password"
  identifier = @{ type = "m.id.user"; user = "s.lewandowski" }
  password = (Read-Host "Hasło administratora")
} | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "$base/_matrix/client/v3/login" -ContentType "application/json" -Body $login).access_token
$h = @{ Authorization = "Bearer $token" }
```

Token działa jak hasło – nie zapisuj go w plikach ani w repozytorium. Każde logowanie administratora wlicza się
do limitu prób (HTTP 429 – patrz [Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4).

> `/_synapse/admin` musi być przepuszczone przez nginx – patrz [README – Etap 0](../README.md#etap-0), punkt 2.
> Bez tego każde wywołanie kończy się `404` od nginx.

### Typowe operacje

Wszystkie przykłady zakładają zmienne `$base` i `$h` z poprzedniego bloku.

| Co zrobić | Jak | Status |
|---|---|---|
| **Utworzyć/zaktualizować konto i nazwę wyświetlaną** | `PUT /_synapse/admin/v2/users/@login:matrix.local` z `displayname` (robi to `provision_synapse_users.py`) | ✅ |
| **Dołączyć użytkownika do pokoju bez zaproszenia** | `POST /_synapse/admin/v1/join/<pokój>` z ciałem `{"user_id": "@login:matrix.local"}` (robi to `setup_directory.py`; pokój podajesz jako identyfikator `!abc:matrix.local`) | ✅ |
| **Lista użytkowników** | `Invoke-RestMethod -Headers $h -Uri "$base/_synapse/admin/v2/users?limit=50&name=kowal"` | ⚠️ |
| **Dezaktywować konto** (np. odejście pracownika) | `POST /_synapse/admin/v1/deactivate/@login:matrix.local`; osobno usuń/zablokuj konto w LLDAP, bo inaczej logowanie przez LDAP założy je znowu | ⚠️ |
| **Lista pokoi** | `Invoke-RestMethod -Headers $h -Uri "$base/_synapse/admin/v1/rooms?limit=100&search_term=ksiazka"` – w wyniku `room_id`, `name`, `canonical_alias`, `joined_members` | ⚠️ |
| **Usunąć pokój** (wszyscy lokalni użytkownicy zostaną usunięci, dane skasowane) | patrz niżej albo panel Synapse Admin (✅ usunięcie z `purge` przez panel – test F4 pkt 6; ⚠️ wywołanie z PowerShella) | ✅/⚠️ |
| **Wyczyścić licznik prób logowania** (po HTTP 429 / `M_LIMIT_EXCEEDED`) | 🐧 **VM** `docker compose restart synapse` | ✅ |
| **Podejrzeć katalog użytkowników** | zapytanie SQL z README – Przygotowanie, punkt A | ✅ |

**Usunięcie pokoju** (⚠️ nieodwracalne; zrób najpierw na pokoju testowym):

```powershell
# 1) znajdź identyfikator pokoju po nazwie
(Invoke-RestMethod -Headers $h -Uri "$base/_synapse/admin/v1/rooms?search_term=Struktura").rooms |
  Select-Object room_id, name, canonical_alias, joined_members

# 2) usuń (purge = skasuj też dane pokoju z bazy); identyfikator ma w adresie wykrzyknik i dwukropek -> koduj
$room = [uri]::EscapeDataString('!abcDEF:matrix.local')
Invoke-RestMethod -Method Delete -Headers $h -Uri "$base/_synapse/admin/v2/rooms/$room" `
  -ContentType "application/json" -Body '{"purge": true}'

# 3) wynik zawiera delete_id; status usuwania:
Invoke-RestMethod -Headers $h -Uri "$base/_synapse/admin/v2/rooms/delete_status/<delete_id>"
```

Pokój „Książka adresowa” odtworzy przy następnym uruchomieniu `setup_directory.py` (po aliasie `ksiazka-adresowa`;
alias zwalnia się dopiero po usunięciu z `purge`).

### Baza danych (PostgreSQL) ✅

Tylko do odczytu i diagnostyki – zmiany w tabelach Synapse rób ostrożnie (jedyna zmiana, którą robimy u siebie:
`UPDATE users SET admin = 1 ...`):

```bash
docker compose exec postgres psql -U synapse -d synapse -c "select count(*) from users;"
docker compose exec postgres psql -U synapse -d synapse -c "select user_id, display_name from user_directory limit 20;"
```

### Logi, restart, kontrola ✅

```bash
docker compose ps                         # co działa
docker compose logs --tail=100 synapse    # ostatnie logi Synapse
docker compose logs -f --tail=0 proxy     # zapytania przechodzące przez nginx na żywo
docker compose restart synapse            # restart (czyści też limity prób logowania)
```

### Kopie zapasowe ⚠️ *(niesprawdzone, do zrobienia przed produkcją)*

Dane do zabezpieczenia: baza Postgres (`pg_dump`), wolumen `lldap_data`, katalog `synapse/` (w tym klucz
podpisu i plik `homeserver.yaml`), pliki mediów Synapse oraz `.env` i `certs/` (poza repozytorium). Przywracanie
nie było testowane.

### Synapse Admin – panel WWW do administrowania serwerem

**Status:** ✅ wdrożony na VM 2026-10-15 (kontener działa, izolacja do loopbacku potwierdzona);
✅ wszystkie 9 testów funkcjonalnych panelu (checklista F4 poniżej) przeszły.

[Synapse Admin](https://github.com/Awesome-Technologies/synapse-admin) (Awesome-Technologies, osobny projekt
społecznościowy) to webowe GUI, które łączy się z serwerem przez to samo Admin API (`/_synapse/admin`) i pozwala
z przeglądarki: przeglądać i dezaktywować konta, oglądać urządzenia, zarządzać pokojami
(w tym usuwać z `purge`), media i limity. Wymaga Synapse ≥ 1.52.0 (u nas ✅ 1.162.0).

**Jak jest wpięty (decyzje projektowe):**

- Usługa `synapse-admin` w `docker-compose.yml`: obraz `awesometechnologies/synapse-admin` z **przypiętym tagiem**
  (`0.11.4`, nie `latest`), **bez publikowanych portów**. ✅ Sprawdzone 2026-10-17: `0.11.4` jest oznaczone jako najnowsze wydanie („Latest”) na stronie wydań projektu i jest
  najwyższym numerowanym tagiem w zewnętrznym zestawieniu tagów obrazu z Docker Huba; przypięty tag zmieniasz świadomie, nie przy `up -d`.
- Nginx dostał osobny blok `server { listen 8080; }` (w `matrix.conf.example`): `/` → panel, a
  `/_matrix` i `/_synapse/admin` → Synapse. Panel i API są pod **tym samym adresem**, więc nie ma problemu z CORS ani
  z certyfikatem (certyfikat serwera ma tylko `matrix.local`). Zwykły HTTP jest tu celowy – ruch idzie po loopbacku
  i tunelu SSH.
- Port 8080 jest publikowany przez Docker **wyłącznie na `127.0.0.1` VM** (`127.0.0.1:8080:8080` w usłudze `proxy`).
  Dostęp „tylko z VM” zapewnia więc sam bind na loopback, a nie reguła `allow/deny` po adresie IP (która w Dockerze
  bywa zawodna: połączenia przez loopback lub tunel mogą być widziane jako adres bramy mostu Dockera).
- Panel **nie** jest w blokach 80/443 ani w bloku Tailscale.

**Adres VM w konfiguracji:** w plikach konfiguracyjnych panelu **nie ma żadnego adresu VM**. W dokumentacji pojawia się
tylko jako placeholder `<IP_VM>` w komendzie tunelu. Przy przepięciu serwerów do innej sieci zmieniasz więc tylko
to, co i tak zależy od adresu: wpis w `hosts` na PC (`<IP_VM>   matrix.local`) i polecenie tunelu SSH.

#### Wdrożenie na istniejącej VM

🐧 **VM**, w `/opt/matrix` – kopie zapasowe (rollback) i sprawdzenie, że port 8080 jest wolny:

```bash
cp docker-compose.yml docker-compose.yml.bak
cp nginx/conf.d/matrix.conf nginx/conf.d/matrix.conf.bak
ss -tlnp | grep 8080          # nic nie powinno być wypisane
```

🪟 **PC** – wyślij dwa zmienione pliki (VM dostaje pliki przez `scp`, nie przez `git pull`; `matrix.conf` jest w
`.gitignore`, więc to **Twój** lokalny plik, wyrównany z tym z VM, nie wzór z repozytorium):

```powershell
scp "<KATALOG_PROJEKTU>\docker-compose.yml" <UZYTKOWNIK>@<IP_VM>:/opt/matrix/
scp "<KATALOG_PROJEKTU>\nginx\conf.d\matrix.conf" <UZYTKOWNIK>@<IP_VM>:/opt/matrix/nginx/conf.d/
```

🐧 **VM** – porównaj z kopią (powinny być tylko oczekiwane zmiany: port 8080, `depends_on`, usługa panelu, blok
`listen 8080`), potem **jedno** uruchomienie:

```bash
diff docker-compose.yml.bak docker-compose.yml
diff nginx/conf.d/matrix.conf.bak nginx/conf.d/matrix.conf
docker compose up -d
docker compose ps                                   # cel: 6 kontenerów Up
docker compose logs --tail=50 proxy synapse-admin   # bez błędów
```

> `nginx -t` uruchomiony **przed** startem zgłosi `host not found in upstream "synapse-admin"` (kontener jeszcze nie
> istnieje) – testuj dopiero po `up`. Dlatego `proxy` ma w `docker-compose.yml` `depends_on: synapse-admin`.

✅ **Sprawdzone 2026-10-15:** `diff` względem kopii pokazał wyłącznie oczekiwane zmiany; `docker compose up -d` OK,
6 kontenerów `Up` (coturn, lldap, postgres, proxy, synapse, synapse-admin), logi `proxy` i `synapse-admin` bez
błędów; `ss -tlnp | grep 8080` pokazuje wyłącznie `127.0.0.1:8080`.

#### Użycie

🪟 **PC** – tunel SSH (okno z tunelem zostaw otwarte):

```powershell
ssh -L 8080:127.0.0.1:8080 <UZYTKOWNIK>@<IP_VM>
```

Przeglądarka na PC: `http://localhost:8080`. W polu serwera wpisz **`http://localhost:8080`**, zaloguj się kontem
administratora (w PoC `s.lewandowski`, hasło z LLDAP). Konto bez flagi `admin` nie wejdzie do panelu.

> ⚠️ Logowanie administratora wlicza się do limitu prób Synapse (HTTP 429 – [Rozwiązywanie problemów](rozwiazywanie-problemow.md) pkt 4), więc nie
> loguj się w panelu i skryptach pod rząd wiele razy.

#### Zasady pracy z panelem (LLDAP)

1. **Konta zakłada i hasła zmienia LLDAP, nie panel.** Konto założone w panelu to lokalne konto Synapse z hasłem poza
   LDAP; reset hasła użytkownikowi z LDAP nic nie daje (logowanie i tak idzie przez LLDAP).
2. **Nazwy wyświetlane** edytowane ręcznie w panelu nadpisze następne uruchomienie `provision_synapse_users.py`.
3. **Pokój „Książka adresowa”** usunięty w panelu odtworzy `setup_directory.py` (po aliasie; alias zwalnia się dopiero
   po `purge`).
4. **Odejście pracownika:** dezaktywacja konta w panelu **oraz** usunięcie/zablokowanie w LLDAP (inaczej logowanie
   przez LDAP założy konto znowu).
5. **Operacje destrukcyjne** (usunięcie pokoju z `purge`, dezaktywacja) najpierw na koncie/pokoju **testowym**.
6. `/_synapse/admin` w bloku 443 pozostaje osiągalne z LAN jak dotąd (chronione tokenem; potrzebne skryptom z PC).
   Panel tego nie zmienia – ewentualne ograniczenie to osobna decyzja (produkcja).

#### Checklista testów panelu (F4)

| # | Test | Status |
|---|---|---|
| 1 | Tunel SSH, `http://localhost:8080` ładuje panel | ✅ |
| 2 | Logowanie `s.lewandowski` (pole serwera `http://localhost:8080`) | ✅ |
| 3 | Lista użytkowników (ok. 204), wyszukiwanie, szczegóły konta, urządzenia | ✅ |
| 4 | Lista pokoi i ich członkowie (wtedy: „Firma” + 7 działów, Spaces wycofane 2026-10-19) | ✅ |
| 5 | Konto bez flagi `admin` (np. `a.nowak`) nie wejdzie do panelu | ✅ |
| 6 | Zapis na koncie/pokoju **testowym**: dezaktywacja konta, usunięcie pokoju z `purge` (zamyka też niesprawdzony punkt w tabeli „Typowe operacje” wyżej) | ✅ |
| 7 | Regresja: logowanie w Elemencie oraz `provision_synapse_users.py --dry-run` (wtedy też `setup_spaces.py --dry-run`, skrypt wycofany) (nie pod rząd – HTTP 429) | ✅ |
| 8 | Bez tunelu: `Test-NetConnection <IP_VM> -Port 8080` z PC → `TcpTestSucceeded : False` | ✅ |
| 9 | Zapora na VM (`ufw`): port 8080 nie jest otwarty | ✅ |

**Rollback:** przywróć `docker-compose.yml.bak` i `nginx/conf.d/matrix.conf.bak` na VM, potem
`docker compose up -d --remove-orphans` (usuwa kontener panelu; dane Synapse i LLDAP nie są ruszane).

> 🏭 **Produkcja (Synapse Admin):** patrz [docs/produkcja.md](produkcja.md).

---

## 🤖 Skrypty automatyzujące

Przegląd skryptów Python w `scripts/` – co robią, kiedy ich użyć, jak uruchomić. Wszystkie czytają adres serwera
i hasła automatycznie z `.env` (nic nie trzeba wpisywać na sztywno ani commitować; hasło administratora Synapse to
`SYNAPSE_ADMIN_PASSWORD`, patrz [README – krok 5.1](../README.md#51-hasła)).

**Wspólne środowisko** (raz, przy pierwszym użyciu któregokolwiek ze skryptów):

🪟 **PC**, PowerShell:

```powershell
cd "<KATALOG_PROJEKTU>\scripts"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Kolejne razy – tylko `venv\Scripts\activate`, bez ponownego tworzenia środowiska i instalowania zależności.

| Skrypt | Co robi | Kiedy użyć |
|---|---|---|
| `seed_test_employees.py` | Tworzy testowe konta w LLDAP (7 grup-działów, wspólne hasło testowe); `--reassign` przepina istniejące konta do aktualnych grup | Potrzebujesz testowej masy pracowników do testów na realnej skali |
| `provision_synapse_users.py` | Zakłada/aktualizuje konta w **Synapse** przez Admin API, bez logowania każdego z osobna, z nazwą `Imię Nazwisko – Dział` | Żeby cała firma była od razu widoczna w katalogu Synapse; po zmianie działów w LLDAP |
| `setup_directory.py` | Buduje pokój „Książka adresowa”: wiadomość wstępna + po jednej na dział, osoby jako pigułki, dane dodatkowe z `directory_extra.csv`; idempotentny (nowe / edycja / bez zmian / usunięcie) | ✅ (pełny przebieg wykonany 2026-10-20) Po dodaniu pracownika lub zmianie działu (po `provision_synapse_users.py`) |
| `setup_announcements.py` | Zakłada pokój „Ogłoszenia” (`#ogloszenia:matrix.local`): publiczny, tylko do odczytu dla zwykłych użytkowników, dołącza wszystkich; skrypt nie wysyła żadnych wiadomości; idempotentny; opcje `--dry-run`, `--alias`, `--skip-join`, `--rejoin`, `--reactions`, `--exclude`; ustawienia `ANNOUNCE_*` w `.env` | Pierwsze założenie pokoju ogłoszeń; po `provision_synapse_users.py`, żeby nowe konta też dołączyły (✅ uruchomiony 2026-10-20) |
| `cleanup_spaces.py` | **Jednorazowe** sprzątanie po wycofaniu Matrix Spaces: usuwa z `purge` pokoje-przestrzenie (`#space-*` lub typ `m.space`) i – bez `--keep-book` – pokój „Książka adresowa”; `--dry-run`, `--yes`, `--keep-book` | Tylko na instalacji, która kiedyś miała Spaces; ⚠️ nieodwracalne, zawsze najpierw `--dry-run` (✅ wykonany 2026-10-20) |
| `deactivate_orphans.py` | Dezaktywuje w Synapse konta, których nie ma już w LLDAP (pomija administratorów, konta techniczne i loginy z `--keep` / `DEACTIVATE_KEEP` w `.env`; nic nie robi przy pustej liście z LLDAP lub gdy do dezaktywacji byłaby ponad połowa kont, chyba że `--force`); `--dry-run`, `--yes`, `--erase` | Po odejściu pracownika (usunięty/zablokowany w LLDAP), żeby zniknął z wyszukiwarki i książki adresowej; ⚠️ nieodwracalne, zawsze najpierw `--dry-run` (✅ wykonany 2026-10-20) |
| `test_directory_message.py` | Eksperyment układu wiadomości (zwijane `<details>` vs nagłówki), `--measure` sprawdza rozmiar | Tylko do prób układu; nie jest częścią normalnego przepływu |
| `setup_main_room.py` | **Biblioteka wspólna** (klasa `Synapse`, `cfg()`, stałe) importowana przez `setup_directory.py` i `test_directory_message.py` | **Nie uruchamiaj** – pokoje i widget wycofane; TODO: wydzielić bibliotekę do osobnego modułu |

Pełny opis, wymagania wstępne i wyniki testów – w README: `seed_test_employees.py` i `provision_synapse_users.py`
w sekcji [Książka adresowa dla całej firmy](../README.md#książka-adresowa-dla-całej-firmy), podsekcje **Przygotowanie, B0** i **Etap 1**;
`setup_directory.py` – [Etap 2.1](../README.md#etap-g--książka-adresowa-jako-pokój-z-wiadomościami).

### Typowe zadania administratora (kolejność skryptów)

⚠️ Poniższe sekwencje wynikają z opisu skryptów i z testów Etapów 1 i 2; nie wszystkie były przećwiczone od początku
do końca.

| Zadanie | Kroki |
|---|---|
| **Nowy pracownik** | LLDAP: utwórz konto i wpisz do grupy-działu → `provision_synapse_users.py` → `setup_directory.py` + `setup_announcements.py` (żeby nowe konto dołączyło do obu pokoi) |
| **Przeniesienie do innego działu** | LLDAP: zmień grupę → `provision_synapse_users.py` (nowa nazwa wyświetlana) → `setup_directory.py` |
| **Odejście pracownika** | LLDAP: usuń/zablokuj konto → `deactivate_orphans.py --dry-run`, potem bez `--dry-run` (albo ręcznie: Admin API / panel Synapse Admin) → `setup_directory.py` |
| **Nowy dział** | LLDAP: utwórz grupę → dopisz ją do `DEPARTMENTS` w `provision_synapse_users.py` → `provision_synapse_users.py` → `setup_directory.py --rebuild` |

---

## Przydatne komendy

🐧 **VM**, zawsze w `/opt/matrix`:

| Co chcę zrobić | Komenda |
|---|---|
| Zobaczyć, co działa | `docker compose ps` |
| Logi jednej usługi | `docker compose logs --tail=50 NAZWA` |
| Logi na żywo | `docker compose logs -f NAZWA` (wyjście: `Ctrl+C`) |
| Zrestartować usługę | `docker compose restart NAZWA` |
| Zatrzymać wszystko | `docker compose down` |
| Uruchomić po zmianach | `docker compose up -d --build` |
| ⚠️ Skasować wszystko razem z danymi | `docker compose down -v` *(usuwa bazę i konta LLDAP!)* |
