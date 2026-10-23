# Administrowanie Synapse (podręcznik administratora)

> Część dokumentacji projektu Matrix PoC. Zaczyna się od wdrożenia kont i książki adresowej (Etapy 0–2), które zakłada gotową
> instalację z [README](../README.md) (kroki 1–10). Dalej zbieramy to, co przydaje się na co dzień:
> usuwanie pokoi, konta użytkowników, panel Synapse Admin, restarty i logi, kopie zapasowe, skrypty automatyzujące.
> **Ta sekcja będzie rosła** – nowe automatyzacje i rzeczy „warto mieć pod ręką” dopisuj tutaj.

Szybkie odsyłacze:

- zmiana kont i działów (nowy pracownik, odejście): [Typowe zadania administratora](#typowe-zadania-administratora-kolejność-skryptów),
- zmiana danych w książce adresowej: [Etap 2](#etap-2), tabela „2.3 Aktualizacja książki”,
- gdy coś nie działa: [Rozwiązywanie problemów](rozwiazywanie-problemow.md).

Synapse nie ma wbudowanego panelu administracyjnego. Zarządzanie odbywa się przez **Admin API** (HTTP),
bezpośrednio w **bazie PostgreSQL** i przez **dokumentację/logi**. Poniżej wszystko, co potrzebne na co dzień.

Do pracy z przeglądarki (konta, pokoje) jest dodatkowo panel
[Synapse Admin](#synapse-admin--panel-www-do-administrowania-serwerem) – działa na tym samym Admin API,
więc skrypty i wywołania z PowerShella nadal działają równolegle.

> Oznaczenia: ✅ = użyte w naszych skryptach albo sprawdzone u nas; ⚠️ = przykład z dokumentacji Synapse,
> niesprawdzony na tym PoC. Przy ⚠️ najpierw spróbuj na koncie testowym.

## Wdrożenie: konta i książka adresowa (Etapy 0–2)

Zakładamy, że [Część 1 README](../README.md#czesc-1) jest gotowa: komunikator działa, a w LLDAP (w firmie: Active Directory)
są konta i grupy-działy. Ta sekcja prowadzi od kont do działającej książki adresowej; dalsza, codzienna praca to
[Bieżąca praca (Etap 3)](#bieżąca-praca-etap-3) poniżej.

| Etap | Co robisz | Powtarzasz, gdy… |
|---|---|---|
| [Przygotowanie](#przygotowanie-jednorazowo) | jednorazowa konfiguracja katalogu, dane w LLDAP | – |
| [Etap 0](#etap-0) | konto administratora Synapse | – (raz) |
| [Etap 1](#etap-1) | konta w Synapse na podstawie LLDAP | nowy pracownik, zmiana działu lub nazwiska, odejście |
| [Etap 2](#etap-2) | książka adresowa: pokój, dane dodatkowe; pokój „Ogłoszenia” | j.w. oraz zmiana telefonu, pokoju, piętra |
| [Etap 3](#bieżąca-praca-etap-3) | bieżąca praca | na bieżąco |

### Założenia

**Wymagania** (docelowo kilkuset pracowników w kilku lokalizacjach):

- pracownik loguje się i od razu może znaleźć każdego kolegę,
- bez klikania zgód i bez pośredników (`matrix.to`),
- kliknięcie osoby otwiera rozmowę 1:1,
- nowi pracownicy z LLDAP pojawiają się automatycznie,
- w wynikach widać dział,
- nikt nie pisze w pokoju książki adresowej (tylko do odczytu); rozmowy 1:1 są dozwolone.

**Rozwiązanie** – książka adresowa to dwa elementy:

1. **Wbudowany katalog użytkowników Synapse** – wyszukiwanie po imieniu, nazwisku albo dziale
   (nazwa wyświetlana ma format `Imię Nazwisko – Dział`). Znalezioną osobę klika się i od razu jest rozmowa 1:1.
   Każde konto LLDAP ma **dokładnie jedną** grupę-dział (7 grup); oddziały A i B mają tylko dział
   „Obsługa”, siedziba ma pozostałe działy.
2. **Pokój „Książka adresowa”** (skrypt `setup_directory.py`, patrz [Etap 2.1](#etap-g--książka-adresowa-jako-pokój-z-wiadomościami)) –
   lista pracowników pogrupowana po działach, do przeglądania bez wyszukiwania, z opcjonalnymi danymi kontaktowymi
   (stanowisko, telefon, pokój, piętro). Pokój jest tylko do odczytu, widoczny dla wszystkich.

<a id="przygotowanie-jednorazowo"></a>
### Przygotowanie (jednorazowo)

#### A. Wyszukiwanie wszystkich użytkowników ✅

W `synapse/homeserver.yaml` dopisz:

```yaml
user_directory:
  search_all_users: true
```

Według dokumentacji Synapse bez tej opcji katalog pokazuje tylko osoby, które mają z Tobą wspólny pokój albo
są w pokojach publicznych. Po zmianie (🐧 **VM**, w `/opt/matrix`): `docker compose restart synapse`.

Nazwa wyświetlana z LLDAP przechodzi w całości, razem z działem, więc wyszukiwanie działa po dziale.

Podgląd katalogu w bazie (🐧 **VM**):

```bash
docker compose exec postgres psql -U synapse -d synapse -c "select user_id, display_name from user_directory;"
```

**Ważne:** konto trafia do katalogu dopiero po **pierwszym logowaniu** (przed nim w tabeli go nie ma,
więc wyszukiwarka go nie znajdzie). Dla całej firmy rozwiązuje to [Etap 1](#etap-1).

Kliknięcie znalezionej osoby otwiera od razu rozmowę 1:1 (sprawdzone 2026-10-10, bez `matrix.to` i bez dodatkowych zgód).

<a id="etap-b0--testowa-struktura-firmy-w-lldap"></a>
#### B0. Konta i grupy w LLDAP (w PoC: testowa masa pracowników) ✅

*Opcjonalne – do testów na skali (ok. 200 fikcyjnych kont); przy pierwszym wdrożeniu wystarczą konta z kroku 8 README.
Sprawdzone na PoC 2026-10-11; struktura grup zmieniona 2026-10-14.*

Żeby mieć co testować w skali, potrzebna jest realna liczba kont w LLDAP – kilka ręcznie wpisanych użytkowników
nie pokazuje, jak zachowa się katalog przy setkach osób. Skrypt `scripts/seed_test_employees.py` (uruchamiany na PC)
generuje testową strukturę **w samym LLDAP** (nie w Synapse – to [Etap 1](#etap-1)).

**Co robi:** tworzy ok. 200 fikcyjnych pracowników (imię + nazwisko, login w formacie `i.nazwisko`) i przypisuje każdego
do **jednej z 7 grup-działów**: Księgowość, Projekty, Dyrekcja, IT, Sprzedaż, Oddział A Obsługa, Oddział B
Obsługa. Wszystkie konta mają **jedno wspólne hasło testowe**. Wyłącznie do testów PoC – nigdy tak na produkcji
z prawdziwymi ludźmi. Istniejące konta przepina do aktualnych grup tryb `--reassign` (bez kasowania kont i bez ruszania haseł).

**Dwa kroki:** konta i grupy tworzy się przez GraphQL API LLDAP (zwykłe zapytania HTTP, z PC), a **hasła** ustawia
oficjalny plik binarny `lldap_set_password` wewnątrz kontenera LLDAP (`/app/lldap_set_password`, nie ma go w `$PATH`).
Działa tylko na **VM** (`docker compose exec`), nie zdalnie z PC.

**Krok 1 – konta i grupy (PC).** Środowisko `venv` jak w sekcji [Skrypty automatyzujące](#-skrypty-automatyzujące).

🪟 **PC**, PowerShell:

```powershell
cd "<KATALOG_PROJEKTU>\scripts"
venv\Scripts\activate
python seed_test_employees.py
```

Skrypt sam czyta adres serwera (`TS_IP`) i hasło admina (`LLDAP_ADMIN_PASSWORD`) z Twojego `.env`. Na górze pliku jest `LIMIT` –
**zacznij od małej wartości (np. 3)**, sprawdź, czy działa, dopiero potem ustaw `LIMIT = None` (wszyscy, do `TOTAL_TARGET`).
Skrypt jest idempotentny – pomija już istniejące konta. Dla istniejących kont:

```powershell
python seed_test_employees.py --reassign --dry-run   # pokaż, kogo przepięto by do nowych grup
python seed_test_employees.py --reassign             # przepnij istniejące konta (bez kasowania, bez haseł)
```

Po zakończeniu w `scripts/` pojawia się wygenerowany `set_test_passwords.sh` (w `.gitignore`, nie trafia do repozytorium).

**Krok 2 – hasła (VM).** Najpierw dopisz do `.env` **na VM** własne hasło testowe (`TEST_PASSWORD`) – skrypt czyta je razem
z `LLDAP_ADMIN_PASSWORD`; brak wartości albo placeholder `CHANGE_ME...` kończy go czytelnym komunikatem.

🪟 **PC**:

```powershell
scp "<KATALOG_PROJEKTU>\scripts\set_test_passwords.sh" <UZYTKOWNIK>@<IP_VM>:/opt/matrix/scripts/
```

(Jeśli `scp` zwraca `dest open ... Failure`, katalog `scripts/` nie istnieje jeszcze na VM: 🐧 **VM** `mkdir -p /opt/matrix/scripts`.)

🐧 **VM**:

```bash
cd /opt/matrix
bash scripts/set_test_passwords.sh
```

Dla każdego konta skrypt woła `docker compose exec lldap /app/lldap_set_password`. Potem zaloguj się w Elemencie jednym
z testowych kont (login z listy, hasło = `TEST_PASSWORD`).

> ⚠️ `M_LIMIT_EXCEEDED` przy logowaniu to limiter prób logowania w Synapse (ochrona przed brute-force), nie błąd hasła.
> Rozwiązanie: 🐧 **VM** `docker compose restart synapse` (czyści licznik), potem spróbuj **raz**.

<a id="etap-0"></a>
### Etap 0 – Konto administratora Synapse

Skrypty z Etapów 1 i 2 logują się do Synapse jako administrator i wywołują Admin API. Przygotowujesz to **raz**,
przed pierwszym uruchomieniem jakiegokolwiek skryptu.

**1. Konto administratora.** Zamiast zakładać nowe (co wymagałoby `registration_shared_secret`, którego nie mamy
skonfigurowanego), podnosimy uprawnienia jednemu z istniejących kont testowych z B0 (dowolnemu – jego login oznaczamy dalej `<LOGIN_ADMINA>`; wpisujesz go w `.env` jako `SYNAPSE_ADMIN_LOGIN`) bezpośrednim
wpisem w bazie.

🐧 **VM**, w `/opt/matrix` (koniecznie w tym katalogu – inaczej `docker compose` zwróci `no configuration file provided`):

```bash
docker compose exec postgres psql -U synapse -d synapse -c "UPDATE users SET admin = 1 WHERE name = '@<LOGIN_ADMINA>:matrix.local';"
```

Powinno pokazać `UPDATE 1`. To NIE zmienia hasła ani niczego w LLDAP – tylko flagę admina w Synapse.

**2. Admin API musi być przepuszczone przez reverse proxy.** Wzór `nginx/conf.d/matrix.conf.example` ma już regułę z
`/_synapse/admin`. Jeśli Twój `matrix.conf` jej nie ma, wywołania Admin API kończą się `404` od samego nginx i trzeba
dodać ją ręcznie:

🐧 **VM**, w `/opt/matrix`:

```bash
sed -i 's#\^(/_matrix|/_synapse/client)#^(/_matrix|/_synapse/client|/_synapse/admin)#' nginx/conf.d/matrix.conf
```

> Jeśli `grep -A1 "API Matrix" nginx/conf.d/matrix.conf` nie pokaże zmiany – edytuj plik ręcznie (`nano nginx/conf.d/matrix.conf`):
> dopisz `|/_synapse/admin` do regexu w linii `location ~ ^(/_matrix|/_synapse/client) {`.

Potem przeładuj nginx:

```bash
docker compose exec proxy nginx -s reload
```

> Admin API jest w ten sposób wystawione przez to samo proxy co klienci – wciąż chronione tokenem administratora, ale na
> produkcji warto rozważyć dodatkowe ograniczenie (np. po adresie IP).

<a id="etap-1"></a>
### Etap 1 – Konta w Synapse na podstawie LLDAP ✅

*Sprawdzone na PoC; format nazwy wyświetlanej zmieniony 2026-10-14.*

Konto w Synapse (i wpis w katalogu `user_directory`, z którego korzysta wyszukiwarka w Elemencie) powstaje domyślnie
dopiero przy **pierwszym logowaniu** przez LDAP. Skrypt zakłada konta z wyprzedzeniem, przez Admin API Synapse, bez
potrzeby logowania każdej osoby osobno, i ustawia nazwę wyświetlaną.

- **Plik:** `scripts/provision_synapse_users.py` (uruchamiany na PC).
- **Warunki:** gotowy [Etap 0](#etap-0) i dane w LLDAP (konto + grupa-dział dla każdego pracownika).
- **Format nazwy wyświetlanej:** `Imię Nazwisko – Dział`; konta bez grupy-działu dostają samo imię i nazwisko.

#### Pierwsze uruchomienie

🪟 **PC**, PowerShell (ten sam `venv` co w B0):

```powershell
cd "<KATALOG_PROJEKTU>\scripts"
python provision_synapse_users.py
```

Skrypt: (1) czyta wszystkich użytkowników z LLDAP razem z ich grupami (dział) przez GraphQL, (2) loguje się do Synapse jako
administrator (`SYNAPSE_ADMIN_LOGIN`, hasło z `SYNAPSE_ADMIN_PASSWORD` w `.env`) przez zwykłe `/login`, (3) dla każdego usera
woła `PUT /_synapse/admin/v2/users/@login:matrix.local` z `displayname` (bez pola `password` – logowanie i tak idzie przez
LDAP). Jak w B0: **`LIMIT`** na górze pliku – zacznij od małej wartości, sprawdź, dopiero potem `LIMIT = None`.

**Jak sprawdzić, czy zadziałało:** w Elemencie (kontem, którym normalnie pracujesz) wyszukaj jedną z przetworzonych osób po
dziale – **bez logowania się na jej konto**. Jeśli się znajdzie, konto istnieje w katalogu mimo braku logowania.

> ⚠️ **Zaobserwowany efekt uboczny (nie błąd):** DM do konta założonego przez Admin API (nigdy niezalogowanego) otwiera się
> jako **nieszyfrowany**, z ostrzeżeniem Elementa o braku E2E. To logiczne – takie konto nie ma jeszcze żadnego urządzenia
> ani kluczy szyfrowania (powstają przy pierwszym prawdziwym logowaniu tej osoby). Czy po jej zalogowaniu ten sam pokój
> staje się szyfrowany, czy trzeba nowego pokoju/weryfikacji – **niesprawdzone**.

#### Aktualizacje: nowy pracownik, zmiana działu, odejście

Źródłem jest zawsze LLDAP (w firmie: AD): zmianę robisz tam, a potem uruchamiasz skrypty po kolei, zaczynając od tego Etapu.
Gotowe sekwencje dla każdej sytuacji (nowy pracownik, konto bez działu, zmiana nazwiska lub działu, odejście, nowy dział):
[Typowe zadania administratora](#typowe-zadania-administratora-kolejność-skryptów).

Zasady:

- Najpierw `--dry-run` każdego skryptu, dopiero potem właściwe uruchomienie.
- Skrypty logują administratora; przy HTTP 429 odczekaj kilka minut ([Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4).
- Przed pełnym przebiegiem sprawdź, czy stała `LIMIT` na górze `provision_synapse_users.py` nie ogranicza liczby kont
  (pełny przebieg: `None`).
- Nowy pracownik **nie musi** się wcześniej logować – konto powstaje z wyprzedzeniem.

<a id="etap-2"></a>
### Etap 2 – Książka adresowa

Książka składa się z dwóch elementów (patrz [Założenia](#założenia)): katalog użytkowników (działa już po Etapie 1)
i pokój z wiadomościami (2.1). Dane dodatkowe (2.2) są opcjonalne i można je dodać później. Osobno (2.4) powstaje pokój
„Ogłoszenia” – nie jest częścią książki, ale działa na tych samych zasadach. Kolejność: 2.1 → 2.2 (2.4 niezależnie).

Każde uruchomienie loguje konto administratora – nie uruchamiaj skryptów wielokrotnie pod rząd (patrz
[Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4).

**Kolejność przy pierwszym wdrożeniu:** `seed_test_employees.py` (konta i grupy w LLDAP, hasła na VM) →
`provision_synapse_users.py` (konta w Synapse) → `setup_directory.py` (książka adresowa, 2.1) → `setup_announcements.py`
(pokój „Ogłoszenia”, 2.4).

**Po starszej wersji ze Spaces (jednorazowo, ✅ uruchomione 2026-10-20):** na PC `python cleanup_spaces.py --dry-run` (lista
pokoi do usunięcia), potem `python cleanup_spaces.py` (usuwa stare przestrzenie i książkę; `--keep-book` zostawia książkę),
odczekaj ok. 4 min (HTTP 429) i dalej jak wyżej.

<a id="etap-g--książka-adresowa-jako-pokój-z-wiadomościami"></a>
#### 2.1 Pokój „Książka adresowa” – wiadomości z listą osób

> ✅ **Status:** skrypt uruchomiony przez użytkownika w pełnym przebiegu (2026-10-20); wcześniej (2026-10-18) sprawdzony
> w Element Desktop: `--dry-run` na 204 kontach i pokój próbny (`--fake-extra --alias test-ksiazka-pelna --limit 20`).
> **Niesprawdzone:** wygląd na telefonie i prawdziwe dane z `directory_extra.csv`.

**Po co:** samo wyszukiwanie w katalogu wymaga znajomości nazwiska albo działu. Pokój z wiadomościami daje listę ludzi
pogrupowaną po działach, do przeglądania bez wyszukiwania, z opcjonalnymi danymi kontaktowymi.

**Jak wygląda wynik:** pokój `#ksiazka-adresowa:matrix.local` (alias domyślny `ksiazka-adresowa`), tylko do odczytu
(piszą administrator i osoby z `DIRECTORY_WRITERS`; reakcje emoji są zablokowane). W pokoju jest jedna wiadomość wstępna
i po jednej wiadomości na dział. Dział rozwija się kliknięciem (znacznik `<details>`), osoby są „pigułkami” Elementa, a obok
nazwiska stoją opcjonalnie: stanowisko, telefon, pokój, piętro.

**Skąd dane:**

- kto, jaki dział, jaka lokalizacja – konta Synapse i ich nazwa wyświetlana (`Imię Nazwisko – Dział[, Lokalizacja]`,
  ustawia ją `provision_synapse_users.py` z LLDAP),
- stanowisko / telefon / pokój / piętro – plik `scripts/directory_extra.csv` (edytowany w Excelu; kolumny: `login`,
  `imie_nazwisko`, `dzial`, `stanowisko`, `telefon`, `pokoj`, `pietro`; separator `;`, UTF-8 z BOM). Szablon z wszystkimi
  loginami tworzy `--write-extra-template`; nie nadpisuje wpisanych wartości, dopisuje tylko nowe osoby. W repozytorium pliku
  nie ma (dane osobowe).

**Co robi** (każdy krok idempotentny – można puszczać wielokrotnie, np. po dodaniu pracownika):

1. Loguje się do Synapse jako administrator i pobiera wszystkie aktywne konta lokalne.
2. Buduje wiadomości: wstęp + po jednej na dział (zbyt duży dział jest dzielony na części).
3. Znajduje pokój po aliasie albo go tworzy; ustawia nazwę, temat i uprawnienia „tylko do odczytu”.
4. Dołącza do pokoju wszystkich z listy **przed** wysłaniem wiadomości (inaczej pigułki mogłyby pokazać sam identyfikator
   zamiast nazwy).
5. Wysyła nowe wiadomości, **edytuje** te, których treść się zmieniła, nie rusza niezmienionych i usuwa wiadomości działów,
   których już nie ma. Stan (id wiadomości i skrót treści) trzyma w pokoju, w zdarzeniu stanu `local.matrix.directory` –
   dzięki temu skrypt działa z dowolnego komputera i konta, bez plików lokalnych.
6. Domyślnie **nie** przypina wiadomości (pasek przypiętych skleja tekst) i zdejmuje stare przypięcia; `--pin` przypina
   wiadomość wstępną.

| Opcja | Co robi |
|---|---|
| `--dry-run` | pokazuje, co by zrobił, i rozmiary wiadomości; bez zapisu |
| `--write-extra-template` | tworzy/uzupełnia `directory_extra.csv` |
| `--extra-file ŚCIEŻKA` | inny plik CSV niż domyślny |
| `--fake-extra` | sztuczne dane (stanowisko, telefon…) do oglądania układu; wiadomość dostaje dopisek „dane demonstracyjne”; **wymaga `--alias`** (poza `--dry-run`) |
| `--alias NAZWA` | inny alias pokoju (do prób) |
| `--limit N` | tylko N osób (próbka rozrzucona po działach); **wymaga `--alias`** (poza `--dry-run`), żeby nie zmienić właściwego pokoju |
| `--exclude login1,login2` | pomija wskazane loginy (stałe pomijanie: `DIRECTORY_EXCLUDE` w `.env`) |
| `--skip-join` / `--rejoin` | bez dołączania osób do pokoju / dołączanie także tych, którzy sami wyszli |
| `--rebuild` | usuwa stare wiadomości i wysyła wszystko od nowa w porządku alfabetycznym |
| `--pin` | przypina wiadomość wstępną (domyślnie bez przypięć) |

Ustawienia w `.env` (opcjonalne): `DIRECTORY_ROOM_ALIAS`, `DIRECTORY_ROOM_NAME`, `DIRECTORY_ROOM_TOPIC`, `DIRECTORY_EXCLUDE`,
`DIRECTORY_WRITERS` (loginy osób, które mogą pisać w pokoju, po przecinku; puste = tylko administrator; domyślnie
`MAIN_ROOM_WRITERS`), `DIRECTORY_JOIN_RULE` (`public` lub `invite`; domyślnie `public` – pokój publiczny, bez banera o braku
szyfrowania; ✅ sprawdzone).

**Kolejność pierwszego użycia** (✅ pełny przebieg uruchomiony 2026-10-20; nie puszczaj skryptów logujących administratora wiele
razy pod rząd – HTTP 429, [Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4):

```powershell
cd "<KATALOG_PROJEKTU>\scripts"
venv\Scripts\activate
python setup_directory.py --write-extra-template      # szablon CSV
python setup_directory.py --dry-run                   # rozmiary wiadomości, podział na działy
python setup_directory.py --fake-extra --alias test-ksiazka-pelna --limit 20   # próba na pokoju próbnym
# obejrzyj pokój próbny kontem zwykłego pracownika (druga instancja Elementa, patrz niżej) ORAZ na telefonie
python setup_directory.py                             # dopiero potem właściwy przebieg
```

Druga, niezależna sesja Elementa na tym samym komputerze (flaga `--profile`):
[README – Drugie konto w Elemencie](../README.md#drugie-konto-w-elemencie-bez-zamykania-pierwszego-przydatne-w-testach).

**Znane ograniczenia i otwarte pytania:**

- Zwijane działy (`<details>`) działają w Element Desktop, **nie działają na telefonie** (świadoma decyzja: układ zostaje).
- Wyszukiwanie w treści pokoju nie działa (stwierdzone w teście); osoby szuka się przez „Rozpocznij rozmowę”
  (patrz [Przygotowanie, A](#przygotowanie-jednorazowo)).
- ⚠️ Pigułka osoby otwiera jej profil. Czy z profilu da się wygodnie zacząć rozmowę 1:1 bez dodatkowych zgód
  (wymaganie z [Założeń](#założenia)) – niesprawdzone.
- Nowy dział ląduje na **dole** osi czasu (nie alfabetycznie); kolejność naprawia `--rebuild`.
- Limit zdarzenia Matrix to ok. 64 KB, a edycja zawiera treść dwa razy – dlatego jedna wiadomość ma maks. ok. 28 KB
  i większy dział jest dzielony na części.
- Dane kontaktowe (telefon, pokój, piętro) są widoczne dla wszystkich członków pokoju.
- **Nie włączaj szyfrowania w pokoju książki.** Skrypt wysyła wiadomości jawnym tekstem, więc w pokoju szyfrowanym każda
  dostaje czerwoną ikonę „niezaszyfrowana”. Szyfrowania nie da się wyłączyć – trzeba usunąć pokój (panel Synapse Admin,
  z opcją purge) i uruchomić `setup_directory.py` ponownie.
- Szerokość „banieczek” zwiniętych działów wyrównuje stała `SUMMARY_PX` w `setup_directory.py` (dopełnienie spacjami
  nierozdzielającymi); dokładnej szerokości Element nie pozwala ustawić.

🏭 Produkcja: [produkcja.md](produkcja.md); źródło danych z AD zamiast CSV, aktualizacja cykliczna i dane osobowe w pokoju:
[integracja-ad.md](integracja-ad.md#ksiazka-adresowa-zrodlo-danych-z-ad-zamiast-csv).

#### 2.2 Dane dodatkowe i pola własne (telefon, pokój, piętro, stanowisko…)

Te dane nie istnieją w LLDAP, więc trzyma je plik **`scripts/directory_extra.csv`** (na PC, nie w repozytorium – to dane
osobowe). Bez niego książka działa, ale pokazuje tylko imię, nazwisko i dział.

1. **Szablon:** `python setup_directory.py --write-extra-template` tworzy plik ze wszystkimi loginami. Przy ponownym
   uruchomieniu **dopisuje nowe osoby** i nie kasuje wpisanych wartości.
2. **Uzupełnij** kolumny `stanowisko`, `telefon`, `pokoj`, `pietro` (separator `;`, UTF-8 z BOM; w Excelu zapisz jako CSV UTF-8).
   Kolumny `login`, `imie_nazwisko`, `dzial` są tylko pomocnicze. Puste pola się nie wyświetlają.
3. **Sprawdź i wyślij:** `python setup_directory.py --dry-run`, potem `python setup_directory.py`. Skrypt edytuje tylko te
   wiadomości, które się zmieniły.

**Pole własne** (np. numer wewnętrzny, adres e-mail działu): w `scripts/setup_directory.py`, w górnej części pliku, dopisz
pozycję do listy `EXTRA_FIELDS` (nazwa kolumny + przedrostek wyświetlany przed wartością) oraz **tę samą nazwę kolumny
w tym samym miejscu** w `TEMPLATE_COLUMNS`. Nazwa kolumny: małe litery, bez polskich znaków i spacji (zamiast spacji `_`).
Kolejność w `EXTRA_FIELDS` to kolejność w wiadomości. Potem: `--write-extra-template` (doda nową kolumnę do CSV, istniejące
wartości zostają), uzupełnij ją i uruchom `setup_directory.py`.

#### 2.3 Aktualizacja książki

| Co się zmieniło | Co zrobić |
|---|---|
| Telefon, pokój, piętro, stanowisko | edytuj `directory_extra.csv` → `setup_directory.py` |
| Nowy pracownik, zmiana działu lub nazwiska, odejście | [Typowe zadania administratora](#typowe-zadania-administratora-kolejność-skryptów) (kolejność skryptów) |
| Nowy dział | grupa w LLDAP + `DEPARTMENTS` w `provision_synapse_users.py` → `provision_synapse_users.py` → `setup_directory.py --rebuild` |
| Ukryć konto z książki (techniczne, testowe) | `DIRECTORY_EXCLUDE` w `.env` albo `--exclude login1,login2` |
| Nazwa lub temat pokoju | `DIRECTORY_ROOM_NAME`, `DIRECTORY_ROOM_TOPIC` w `.env` |
| Nazwa, temat lub autorzy ogłoszeń | `ANNOUNCE_ROOM_NAME`, `ANNOUNCE_ROOM_TOPIC`, `ANNOUNCE_WRITERS` w `.env` → `setup_announcements.py` |
| Kolejność wiadomości się rozjechała | `setup_directory.py --rebuild` (wysyła wiadomości od nowa) |

#### 2.4 Pokój „Ogłoszenia”

✅ *Skrypt uruchomiony przez użytkownika 2026-10-20 (szczegółów przebiegu nie zapisano).*

**Po co:** jedno miejsce na ogłoszenia firmowe, które widzą wszyscy, a piszą tylko wskazane osoby. Zastępuje stary pokój
„Firma-Ogłoszenia”.

**Plik:** `scripts/setup_announcements.py` (uruchamiany na PC; korzysta z biblioteki `setup_main_room.py` i funkcji
z `setup_directory.py`).

**Jak wygląda wynik:** pokój `#ogloszenia:matrix.local` (alias domyślny `ogloszenia`), **publiczny** (każdy z serwera może
dołączyć przez alias, ale pokoju nie ma w publicznym katalogu), **tylko do odczytu** (piszą administrator i osoby
z `ANNOUNCE_WRITERS`; reakcje emoji zablokowane, chyba że `--reactions`), bez szyfrowania. Skrypt **nie wysyła żadnych
wiadomości** – ogłoszenia piszesz ręcznie w Elemencie.

**Co robi** (każdy krok idempotentny – można puszczać wielokrotnie, np. po dodaniu pracowników):

1. Loguje się do Synapse jako administrator i pobiera wszystkie aktywne konta lokalne.
2. Znajduje pokój po aliasie albo go tworzy (od razu publiczny); ustawia nazwę, temat, uprawnienia „tylko do odczytu”
   i regułę dołączania.
3. Dołącza do pokoju wszystkich z listy (pomija tych, którzy sami wyszli – chyba że `--rejoin`).

| Opcja | Co robi |
|---|---|
| `--dry-run` | pokazuje plan, bez zapisu |
| `--alias NAZWA` | inny alias pokoju (do prób) |
| `--skip-join` / `--rejoin` | bez dołączania osób / dołączanie także tych, którzy sami wyszli |
| `--reactions` | pozwala na reakcje emoji (domyślnie zablokowane) |
| `--exclude login1,login2` | pomija wskazane loginy (np. konta techniczne) |

Ustawienia w `.env` (opcjonalne): `ANNOUNCE_ROOM_ALIAS` (domyślnie `ogloszenia`), `ANNOUNCE_ROOM_NAME`, `ANNOUNCE_ROOM_TOPIC`,
`ANNOUNCE_WRITERS` (loginy autorów, po przecinku; domyślnie `DIRECTORY_WRITERS`, potem `MAIN_ROOM_WRITERS`),
`ANNOUNCE_JOIN_RULE` (`public` lub `invite`; domyślnie `public`), `ANNOUNCE_EXCLUDE` (loginy po przecinku).

**Uwagi:**

- **Nowi pracownicy:** po `provision_synapse_users.py` uruchom skrypt ponownie (dołączy nowych). Alternatywa: `auto_join_rooms`
  w `homeserver.yaml` Synapse (wymaga restartu) – ⚠️ nie sprawdzone, skrypt tego nie robi.
- **Stary pokój „Firma-Ogłoszenia”** skrypt **nie usuwa** – usuń go ręcznie w panelu Synapse Admin (z opcją purge), gdy ogłoszenia
  się przeniosą.
- Nie puszczaj skryptu pod rząd z innymi skryptami logującymi administratora (HTTP 429, patrz
  [Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4).

<a id="etap-d--klienci-do-sprawdzenia-przy-produkcji"></a>
### Wdrożenie klientów (D, do sprawdzenia przy produkcji)

- `config.json` Element Desktop z domyślnym serwerem `matrix.local`, żeby pracownik nie wpisywał adresu – ⚠️ w Element Desktop 1.12.32
  kopiowanie do `%APPDATA%\Element\` **nie działa** (klient bierze `config.json` z `webapp.asar`); patrz
  [wyglad-element.md](wyglad-element.md) (teraz: ręczne ustawienia konta, wersja b; podmiana w `webapp.asar` – na kiedyś, wersja a),
- `rootCA.pem` na stanowiskach (docelowo przez GPO),
- DNS zamiast wpisów w pliku `hosts`,
- dołączanie do pokoi „Książka adresowa” i „Ogłoszenia” robią dziś `setup_directory.py` i `setup_announcements.py`; czy zadziała `auto_join_rooms` dla
  kont zakładanych przez LDAP / Admin API – **niesprawdzone**.

---

<a id="bieżąca-praca-etap-3"></a>
## Bieżąca praca (Etap 3)

Codzienna obsługa serwera po wdrożeniu: konto administratora, Admin API, pokoje, baza, logi, kopie, panel Synapse Admin, skrypty i przydatne komendy.

### Konto administratora ✅

Administrator to zwykłe konto Matrix z flagą `admin`. W PoC jest to `<LOGIN_ADMINA>` (konto testowe z LLDAP,
flaga ustawiona w bazie – patrz [Etap 0](#etap-0)).
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
  identifier = @{ type = "m.id.user"; user = "<LOGIN_ADMINA>" }
  password = (Read-Host "Hasło administratora")
} | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "$base/_matrix/client/v3/login" -ContentType "application/json" -Body $login).access_token
$h = @{ Authorization = "Bearer $token" }
```

Token działa jak hasło – nie zapisuj go w plikach ani w repozytorium. Każde logowanie administratora wlicza się
do limitu prób (HTTP 429 – patrz [Rozwiązywanie problemów](rozwiazywanie-problemow.md), punkt 4).

> `/_synapse/admin` musi być przepuszczone przez nginx – patrz [Etap 0](#etap-0), punkt 2.
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
| **Podejrzeć katalog użytkowników** | zapytanie SQL z [Przygotowanie, A](#przygotowanie-jednorazowo) | ✅ |

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
administratora (w PoC `<LOGIN_ADMINA>`, hasło z LLDAP). Konto bez flagi `admin` nie wejdzie do panelu.

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
| 2 | Logowanie `<LOGIN_ADMINA>` (pole serwera `http://localhost:8080`) | ✅ |
| 3 | Lista użytkowników (ok. 204), wyszukiwanie, szczegóły konta, urządzenia | ✅ |
| 4 | Lista pokoi i ich członkowie (wtedy: „Firma” + 7 działów, Spaces wycofane 2026-10-19) | ✅ |
| 5 | Konto bez flagi `admin` (np. `a.nowak`) nie wejdzie do panelu | ✅ |
| 6 | Zapis na koncie/pokoju **testowym**: dezaktywacja konta, usunięcie pokoju z `purge` (zamyka też niesprawdzony punkt w tabeli „Typowe operacje” wyżej) | ✅ |
| 7 | Regresja: logowanie w Elemencie oraz `provision_synapse_users.py` (skrypt nie ma trybu `--dry-run`; uruchomienie jest idempotentne) (nie pod rząd – HTTP 429) | ✅ |
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

Pełny opis, wymagania wstępne i wyniki testów – wyżej w tym pliku: `seed_test_employees.py` – [Przygotowanie, B0](#etap-b0--testowa-struktura-firmy-w-lldap);
`provision_synapse_users.py` – [Etap 1](#etap-1); `setup_directory.py` – [Etap 2.1](#etap-g--książka-adresowa-jako-pokój-z-wiadomościami);
`setup_announcements.py` – [Etap 2.4](#24-pokój-ogłoszenia).

### Typowe zadania administratora (kolejność skryptów)

⚠️ Poniższe sekwencje wynikają z opisu skryptów i z testów Etapów 1 i 2; nie wszystkie były przećwiczone od początku
do końca.

| Zadanie | Kroki |
|---|---|
| **Nowy pracownik** | LLDAP: utwórz konto i wpisz do grupy-działu → `provision_synapse_users.py` → `setup_directory.py` + `setup_announcements.py` (żeby nowe konto dołączyło do obu pokoi) |
| **Numery telefonów (i inne dane) nowym osobom** | patrz [niżej](#dodanie-numerów-telefonów-nowym-osobom) |
| **Przeniesienie do innego działu** | LLDAP: zmień grupę → `provision_synapse_users.py` (nowa nazwa wyświetlana) → `setup_directory.py` |
| **Konto bez działu** (w książce trafia do „Bez działu”) | LLDAP: dodaj do grupy-działu → jak przy nowym pracowniku |
| **Zmiana nazwiska lub poprawa nazwy** | LLDAP: edytuj imię i nazwisko → `provision_synapse_users.py` → `setup_directory.py` |
| **Odejście pracownika** | LLDAP: usuń/zablokuj konto → `deactivate_orphans.py --dry-run`, potem bez `--dry-run` (albo ręcznie: Admin API / panel Synapse Admin) → `setup_directory.py` |
| **Nowy dział** | LLDAP: utwórz grupę → dopisz ją do `DEPARTMENTS` w `provision_synapse_users.py` → `provision_synapse_users.py` → `setup_directory.py --rebuild` |

#### Dodanie numerów telefonów nowym osobom

Dane kontaktowe (telefon, stanowisko, pokój, piętro) nie są w LLDAP, tylko w `scripts\directory_extra.csv`
(plik w `.gitignore` – dane osobowe, nie trafia do repozytorium). Opis pliku i pól: [2.2](#22-dane-dodatkowe-i-pola-własne-telefon-pokój-piętro-stanowisko).

🪟 **PC**, PowerShell, w `scripts` z aktywnym `venv`:

1. LLDAP: utwórz konto i dodaj do grupy-działu, potem `python provision_synapse_users.py`.
2. Odczekaj ok. 4 minuty (HTTP 429 – skrypty logują administratora), potem
   `python setup_directory.py --write-extra-template` – dopisuje **tylko nowe loginy** do `directory_extra.csv`,
   wpisanych wartości nie rusza.
3. Otwórz `directory_extra.csv` w Excelu, uzupełnij `telefon` (opcjonalnie `stanowisko`, `pokoj`, `pietro`).
   Numer wpisz jako tekst, np. `+48 600 123 456`. Zapisz jako **CSV UTF-8** (średniki), **zamknij plik** w Excelu.
4. Odczekaj kilka minut, `python setup_directory.py --dry-run` (sprawdź, które wiadomości działów się zmienią),
   potem `python setup_directory.py` – wysyła nowe i edytuje zmienione wiadomości.

Jeśli zmieniasz numery tylko istniejącym osobom, kroki 1–2 pomiń.

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
