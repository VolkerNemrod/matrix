# Wdrożenie produkcyjne – co zmienić

> Część dokumentacji projektu Matrix PoC. To środowisko testowe (PoC) ma szereg uproszczeń celowych dla testów.
> Ten plik zbiera w jednym miejscu wszystko, co trzeba przejrzeć/zmienić przed wdrożeniem produkcyjnym –
> wcześniej było rozsiane po README jako zwijane ramki 🏭.

## Lista kontrolna przed wdrożeniem produkcyjnym

1. **Własne, losowe hasła** w `.env` i `synapse/homeserver.yaml` (`openssl rand -hex 24`) – nigdy wartości
   z przykładów ani z dokumentacji.
2. **Wpisz je w OBU plikach** (patrz [README – krok 5.1](../README.md#51-hasła)): `POSTGRES_PASSWORD`, `TURN_SECRET`, `LLDAP_ADMIN_PASSWORD`.
3. **Ustaw hasła PRZED pierwszym uruchomieniem.** *(Niesprawdzone u nas, ale to typowe zachowanie
   kontenerów:)* PostgreSQL i LLDAP zapisują hasło w wolumenie przy pierwszym starcie, więc późniejsza
   zmiana samego `.env` może go nie zmienić. Jeśli trzeba zmienić po fakcie – zmień hasło w samej bazie /
   w panelu LLDAP albo odtwórz wolumeny (`docker compose down -v` **kasuje dane!**).
4. Panel LLDAP (port 17170) jest w `docker-compose.yml` otwarty na wszystkich interfejsach VM – rozważ
   ograniczenie go do adresu Tailscale (*niesprawdzone*).
5. Po zmianach przetestuj ponownie: logowanie kontem z LLDAP (Synapse → LDAP) i rozmowę A/V
   (Synapse ↔ Coturn).
6. Rozmiar VM (4 GB / 2 vCPU) dla kilkuset użytkowników jest **niesprawdzony**.
7. **Domena i `server_name`:** wybierz docelową domenę przed założeniem kont – `server_name` jest wpisany
   w każdy identyfikator użytkownika i nie da się go zmienić (szczegóły: sekcja „Domena, konto administratora, limity skryptów” niżej).
8. **Konto administratora Synapse:** osobne konto serwisowe zamiast testowego, hasło poza kodem skryptów;
   `/_synapse/admin` ograniczone po IP.
9. **Słabe hasła PoC** w danych testowych i w historii gita (hasło administratora – od 2026-10-17 w `.env`, ale stara wartość jest w commitach; wspólne hasło testowe
   kont z Etapu B0) – zmień przed udostępnieniem środowiska komukolwiek. Checklista:
   [docs/rotacja-hasel-poc.md](rotacja-hasel-poc.md) (⚠️ nieprzećwiczona).
10. **Kopie zapasowe** (baza, wolumen LLDAP, `synapse/`, media) – opisane, ale nieprzetestowane (patrz
    [docs/administrowanie.md](administrowanie.md)).
11. **Książka adresowa:** źródło danych (AD zamiast CSV) i cykliczne uruchamianie skryptów – sekcja niżej.
12. **Synapse Admin (panel):** zostaw port 8080 tylko na loopbacku VM (nie otwieraj go w zaporze), użyj osobnego konta
    administratora zamiast testowego i ustal procedurę aktualizacji przypiętego obrazu (sekcja niżej).

## Znane ograniczenia PoC

- Książka adresowa nie synchronizuje się sama – zmiany w LLDAP wymagają ponownego uruchomienia skryptów.
- Pokój „Książka adresowa” (Etap 2.1): zwijane działy nie działają na telefonie, a wyszukiwanie w treści pokoju
  nie działa. Z prawdziwymi danymi kontaktowymi nie był jeszcze sprawdzany.
- Kto sam wyjdzie z pokoju książki, nie wróci automatycznie (świadoma decyzja skryptu, `--rejoin` to zmienia).
- Konto trafia do katalogu wyszukiwania dopiero po założeniu w Synapse (`provision_synapse_users.py`) albo
  pierwszym logowaniu.
- Certyfikat serwera jest ważny 825 dni, Root CA 10 lat; certyfikat z Tailscale ok. 90 dni.
- Federacja jest wyłączona (`federation_domain_whitelist: []`) – serwer nie łączy się z innymi serwerami Matrix.
- Panel Synapse Admin jest dostępny tylko z VM albo przez tunel SSH z PC (świadoma decyzja – brak wygodnego adresu dla
  innych administratorów). Konta i hasła nadal prowadzi LLDAP, nie panel.

## Domena, konto administratora, limity skryptów

- **Domena i `server_name`.** `server_name` (`matrix.local`) jest wpisany w każdy identyfikator użytkownika
  (`@login:matrix.local`) i Synapse nie pozwala go zmienić po fakcie. Docelową domenę wybierz **przed** założeniem
  kont produkcyjnych. `matrix.local` odpada (`.local` jest zarezerwowane dla mDNS, na PoC wymaga wpisu w `hosts`
  i ręcznie zainstalowanego rootCA); na produkcji prawdziwa domena i certyfikat zaufany bez ręcznej instalacji.
- **Konto administratora.** W PoC: dowolne konto testowe (`SYNAPSE_ADMIN_LOGIN` w `.env`), hasło w `.env` (`SYNAPSE_ADMIN_PASSWORD`) i flaga `admin` ustawiona
  `UPDATE`-em w bazie. Na produkcji: osobne konto serwisowe (nie osoba z działu), założone przez
  `register_new_matrix_user -a` (wymaga `registration_shared_secret`), z hasłem lub tokenem poza kodem
  (`.env` albo menedżer sekretów).
- **Admin API.** `/_synapse/admin` jest w PoC wystawione przez to samo proxy co klienci. Na produkcji ogranicz je
  po adresie IP albo uruchamiaj skrypty na serwerze przez localhost.
- **Limit logowania (`rc_login`).** Każde uruchomienie skryptu loguje konto administratora, a Synapse ogranicza
  liczbę prób. Na produkcji uruchamiaj skrypt rzadko albo użyj tokenu zamiast logowania hasłem; limit można też
  poluzować w `homeserver.yaml` dla konta serwisowego.
- **Partnerzy zewnętrzni.** Sposób importu kont i widoczność książki adresowej dla partnerów zewnętrznych –
  [docs/integracja-ad.md](integracja-ad.md#partnerzy-firmy-zewnętrzne).

## Książka adresowa w pokoju (Etap 2.1)

- **Źródło danych: AD zamiast CSV i cykliczna aktualizacja** – opisane w
  [docs/integracja-ad.md](integracja-ad.md#książka-adresowa-źródło-danych-z-ad-zamiast-csv).
- **Nowy dział.** Pojawi się na dole listy; do uporządkowania kolejności potrzebny jest `--rebuild`.
- **Dane osobowe w pokoju.** Telefony i lokalizacje są widoczne dla każdego członka pokoju (i zostają w historii
  zdarzeń Synapse po edycji) – zdecyduj, które pola publikować.
- **Hasła i konto administratora** – jak wyżej (sekcja „Domena, konto administratora, limity skryptów”).

## Synapse Admin (panel)

- **Dostęp.** Albo nadal tylko loopback + tunel SSH/VPN (najprostsze), albo panel pod własną nazwą (np.
  `admin.<domena>`) z prawdziwym certyfikatem i ograniczeniem po adresie IP / VPN. Nie wystawiaj panelu publicznie.
- **Osobne konto administratora** (`register_new_matrix_user -a`, wymaga `registration_shared_secret`) zamiast konta
  testowego `<LOGIN_ADMINA>`; hasło poza kodem.
- **Aktualizacje.** Tag obrazu jest przypięty – ustal, kto i jak często go podnosi, oraz sprawdzaj zgodność panelu
  z wersją Synapse.
- **Kopia zapasowa** (baza, wolumen LLDAP, `synapse/`, media) **przed** operacjami destrukcyjnymi.
- **Admin API w bloku 443.** Rozważ ograniczenie `/_synapse/admin` (po IP albo skrypty uruchamiane na serwerze przez
  localhost); panel działa na osobnym porcie i go nie potrzebuje.

## Jeden serwer dla całej firmy (decyzja architektoniczna)

Na produkcji działa **jeden serwer Synapse dla wszystkich trzech lokalizacji**. Dzięki temu wbudowany katalog
użytkowników wystarcza (jedna lista wszystkich pracowników) i nie jest potrzebna osobna, centralna książka
adresowa. Opcja „osobny serwer na każdą lokalizację z federacją” odpada – tam katalog obejmowałby tylko
użytkowników własnego serwera.

Skutek: federacja pozostaje wyłączona (`federation_domain_whitelist: []`), a rozmiar jednej maszyny
(obecnie 4 GB / 2 vCPU) trzeba oceniać pod kilkuset użytkowników naraz – niesprawdzone.
