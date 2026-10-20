# Wymiana słabych haseł PoC – checklista

> ⚠️ **Status: dokument przygotowany 2026-10-17, NIEPRZEĆWICZONY.** Żadna z poniższych operacji nie była
> wykonana na VM. Zrób najpierw kopię zapasową (punkt 0) i próbuj po jednej zmianie, sprawdzając wynik.
> Dotyczy środowiska PoC; produkcja ma własną listę (README, „Przed wdrożeniem produkcyjnym”).

## Gdzie są słabe hasła

| # | Co | Gdzie jest wpisane | Uwagi |
|---|---|---|---|
| 1 | Hasło administratora Synapse (`s.lewandowski`) = wspólne hasło testowe | `SYNAPSE_ADMIN_PASSWORD` w `.env` na PC (od 2026-10-17 nie jest już wpisane w kodzie; czytają je `setup_main_room.py` jako biblioteka – importują ją `setup_directory.py`, `setup_announcements.py`, `cleanup_spaces.py`, `deactivate_orphans.py`, `test_directory_message.py` – oraz `provision_synapse_users.py`) | Konto loguje się przez LDAP, więc hasło zmienia się w **LLDAP**, nie w Synapse. ⚠️ Stara wartość `TestHaslo123!` zostaje w historii gita (commity sprzed zmiany) |
| 2 | Wspólne hasło ok. 200 kont testowych (Etap B0) | `TEST_PASSWORD` w `.env` **na VM** (od 2026-10-17 nie jest już w `seed_test_employees.py` ani w wygenerowanym `set_test_passwords.sh`; skrypt czyta je po `source .env`); wg README dotychczasowa wartość to `TestHaslo123!` | `set_test_passwords.sh` jest generowany i ignorowany przez git; nie zawiera już hasła, tylko loginy |
| 3 | `POSTGRES_PASSWORD` | `.env` **oraz** `synapse/homeserver.yaml` (`database.args.password`) | Postgres zapisuje hasło w wolumenie przy pierwszym starcie |
| 4 | `TURN_SECRET` | `.env` **oraz** `synapse/homeserver.yaml` (`turn_shared_secret`) | |
| 5 | `LLDAP_ADMIN_PASSWORD` (admin panelu LLDAP :17170) | `.env` **oraz** `synapse/homeserver.yaml` (`modules[].config.bind_password`) | Skrypty czytają je z `.env` |
| 6 | `LLDAP_JWT_SECRET`, `LLDAP_KEY_SEED` | tylko `.env` | ⚠️ Zmiana `LLDAP_KEY_SEED` prawdopodobnie unieważnia zapisane hasła użytkowników (do potwierdzenia w dokumentacji LLDAP) – nie zmieniaj bez potrzeby. Zmiana `LLDAP_JWT_SECRET` zwykle tylko wylogowuje sesje |

Wartości z punktów 3–6 mają być losowe (`openssl rand -hex 24`) i niepowtarzalne; w README i `.env.example` są tylko
placeholdery `CHANGE_ME_...`. Sprawdź, czy prawdziwe `.env` i `homeserver.yaml` nie zostały skopiowane z wartościami
z dokumentacji.

## Kolejność

0. **Kopia zapasowa** (patrz README, „Kopie zapasowe”): zrzut bazy (`pg_dump`), wolumen `lldap_data`, katalog `synapse/`,
   `.env`. Zapisz, gdzie leży kopia – przywracanie nie było testowane.
1. **Nowe hasło administratora (punkt 1)**
   1. Zmień hasło konta w LLDAP (panel LLDAP albo narzędzie `lldap_set_password` – wzór wywołania jest w
      wygenerowanym `set_test_passwords.sh`).
   2. Zaktualizuj `SYNAPSE_ADMIN_PASSWORD` w `.env` na PC (kod skryptów nie wymaga zmian).
   3. Sprawdź **jednym** skryptem z `--dry-run` (np. `setup_directory.py --dry-run`); nie uruchamiaj skryptów logujących
      admina wiele razy pod rząd (HTTP 429, czekanie ok. 4 min).
   - 💡 Hasło jest czytane z `.env` (zmiana w kodzie wykonana 2026-10-17, **nieprzetestowana** – patrz README). Stare
     hasło zostaje w historii gita – dla PoC do przyjęcia, dla produkcji nowe repozytorium albo przepisanie historii.
2. **Hasła kont testowych (punkt 2):** albo nowe wspólne hasło (zmiana `TEST_PASSWORD` w `.env` na VM i ponowne
   uruchomienie `set_test_passwords.sh` na VM; skrypt nie zawiera już hasła, więc nie trzeba go regenerować), albo – przed udostępnieniem środowiska – dezaktywacja kont testowych
   (panel Synapse Admin + usunięcie/zablokowanie w LLDAP, inaczej logowanie przez LDAP założy konto znowu).
3. **Sekrety infrastruktury (punkty 3–5):** po jednym, w tej kolejności, po każdym `docker compose ps`, logi i test
   logowania w Elemencie:
   1. `TURN_SECRET` – `.env` i `homeserver.yaml`, potem restart `coturn` i `synapse`.
   2. `LLDAP_ADMIN_PASSWORD` – zmiana w LLDAP, potem `.env` i `bind_password` w `homeserver.yaml`, restart `synapse`.
   3. `POSTGRES_PASSWORD` – zmiana hasła w samej bazie (⚠️ niesprawdzone: `ALTER USER ... PASSWORD` przez `psql`
      w kontenerze), potem `.env` i `homeserver.yaml`, restart `synapse`. Sama zmiana `.env` nie zmienia hasła w
      istniejącym wolumenie.
4. **Weryfikacja końcowa:** logowanie kontem z LLDAP w Elemencie (Synapse → LDAP), jeden `--dry-run` skryptu,
   rozmowa A/V 1:1 (Synapse ↔ Coturn, test A/V wciąż niepotwierdzony), panel Synapse Admin (logowanie nowym hasłem).
5. **Zapis:** zaktualizuj README („Przed wdrożeniem produkcyjnym”, punkty 1–3 i 10) i oznacz wykonane pozycje.

## Czego ta checklista nie obejmuje

- Konto serwisowe administratora zamiast konta osoby z działu (`register_new_matrix_user -a`, wymaga
  `registration_shared_secret`) – ramka 🏭 przy Etapie E.
- Ograniczenia dostępu do `/_synapse/admin` po adresie IP.
- Hasła użytkowników z prawdziwego AD – na produkcji zarządza nimi AD, nie LLDAP.
