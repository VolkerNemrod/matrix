#!/usr/bin/env python3
"""
provision_synapse_users.py -- Etap 1 (README; w nazewnictwie skryptow B + C): zaklada/aktualizuje
konta w Synapse na podstawie uzytkownikow juz istniejacych w LLDAP (w PoC: scripts/seed_test_employees.py,
Etap B0), z nazwa wyswietlana w formacie "Imie Nazwisko – Dzial" (bez lokalizacji:
Oddzial A Obsluga i Oddzial B Obsluga to zwykle dzialy). Konta bez grupy-dzialu
dostaja sama nazwe "Imie Nazwisko" (w ksiazce adresowej trafiaja do "Bez dzialu").

CEL: bez tego skryptu konto w Synapse (i wpis w katalogu user_directory, z ktorego
korzysta wyszukiwarka w Elemencie) powstaje dopiero przy PIERWSZYM LOGOWANIU danej
osoby. Dla ~200-300 osob oznacza to, ze katalog buduje sie tygodniami. Ten skrypt
zaklada konta z WYPRZEDZENIEM, przez Admin API Synapse, bez potrzeby logowania
kazdej osoby osobno.

WYMAGANIA WSTEPNE (jednorazowe, patrz README, "Etap 0 – Konto administratora Synapse"):
  1. Jeden z istniejacych, dzialajacych kont (w PoC: konto testowe z Etapu B0) musi byc
     oznaczony jako administrator Synapse -- przez bezposredni UPDATE w bazie
     (na VM): patrz README, Etap 0. Domyslnie ten skrypt zaklada, ze to konto
     SYNAPSE_ADMIN_LOGIN z .env. Nginx musi przepuszczac /_synapse/admin (README, Etap 0, pkt 2).
  2. W .env na PC: SYNAPSE_ADMIN_LOGIN i SYNAPSE_ADMIN_PASSWORD (konto i haslo administratora Synapse), TS_IP oraz
     LLDAP_ADMIN_PASSWORD (wzor: .env.example).
  3. PC, na ktorym uruchamiasz ten skrypt, musi miec dzialajacy dostep do
     https://matrix.local (wpis w hosts + zaufany rootCA) -- dokladnie to
     samo, czego wymaga Element Desktop. Jesli Element u Ciebie dziala,
     ten skrypt tez powinien.

KOLEJNOSC (README, "Zmienilem X – co uruchomic"): po tym skrypcie uruchom setup_directory.py
(przy zmianie dzialu wystarczy uruchomic go ponownie -- bez dodatkowego kroku). Nie puszczaj
skryptow pod rzad bez przerw -- kazdy loguje administratora (HTTP 429, README, Rozwiazywanie problemow, pkt 4).

Wymaga: pip install requests (scripts/requirements.txt)
Uzycie (PC, katalog scripts, venv aktywny): python provision_synapse_users.py
Przed pelnym przebiegiem sprawdz stala LIMIT ponizej (pelny przebieg: None).
"""

import os
import sys
from pathlib import Path

import requests

# ============================================================
# KONFIGURACJA -- edytuj wedle potrzeb
# ============================================================

# Adres, pod ktorym klienci (i ten skrypt) rozmawiaja z Synapse -- ten sam,
# ktorego uzywa Element Desktop (wymaga wpisu w hosts + zaufanego rootCA).
MATRIX_BASE_URL = "https://matrix.local"

# Sciezka do certyfikatu CA projektu (do poprawnej weryfikacji TLS, bez -k/verify=False).
ROOT_CA_PATH = Path(__file__).resolve().parent.parent / "rootCA.pem"

# Konto podniesione do roli administratora Synapse (patrz README, Etap 0 --
# jednorazowy UPDATE w bazie na VM). Haslo NIE jest w kodzie: SYNAPSE_ADMIN_PASSWORD
# z .env (albo zmiennej srodowiskowej) -- patrz ADMIN_PASSWORD nizej, za load_dotenv_value().
# ADMIN_LOGIN (SYNAPSE_ADMIN_LOGIN z .env) jest wczytywany nizej, za load_dotenv_value().

HOMESERVER_DOMAIN = "matrix.local"  # czesc MXID po dwukropku, np. @login:matrix.local

# Ilu userow z LLDAP przetworzyc w TYM uruchomieniu. USTAW MALA WARTOSC NA TEST.
LIMIT = None     # np. 3 na start -> sprawdz czy dziala -> potem None = wszyscy

# Ta sama lista co w seed_test_employees.py -- musi sie zgadzac, zeby skrypt
# wiedzial, ktora grupa usera to dzial (nowy dzial: dopisz go tez tutaj). Lokalizacji juz nie ma.
DEPARTMENTS = ["Księgowość", "Projekty", "Dyrekcja", "IT", "Sprzedaż",
               "Oddział A Obsługa", "Oddział B Obsługa"]

# ============================================================


def load_dotenv_value(key: str) -> str:
    """Czyta pojedynczy klucz z pliku .env w katalogu nadrzednym (bez dodatkowej zaleznosci)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return ""


# Haslo administratora Synapse (SYNAPSE_ADMIN_PASSWORD w .env); brak/placeholder wykrywa SynapseAdmin._login().
ADMIN_PASSWORD = os.environ.get("SYNAPSE_ADMIN_PASSWORD") or load_dotenv_value("SYNAPSE_ADMIN_PASSWORD")

# Login konta administratora Synapse (SYNAPSE_ADMIN_LOGIN w .env) -- dowolne konto z LLDAP podniesione do admina (README, Etap 0).
ADMIN_LOGIN = os.environ.get("SYNAPSE_ADMIN_LOGIN") or load_dotenv_value("SYNAPSE_ADMIN_LOGIN")
if not ADMIN_LOGIN or ADMIN_LOGIN.startswith("CHANGE_ME"):
    sys.exit("Brak SYNAPSE_ADMIN_LOGIN w .env (login konta administratora Synapse, patrz README, Etap 0).")


def resolve_lldap_url() -> str:
    ts_ip = os.environ.get("TS_IP") or load_dotenv_value("TS_IP")
    if not ts_ip or "x.x" in ts_ip:
        print("BLAD: nie udalo sie ustalic adresu LLDAP (brak TS_IP w .env).")
        sys.exit(1)
    return f"http://{ts_ip}:17170"


class LldapReader:
    """Tylko odczyt -- lista userow z LLDAP wraz z ich grupami (dzialami)."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        token = self._login(username, password)
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _login(self, username: str, password: str) -> str:
        r = self.session.post(
            f"{self.base_url}/auth/simple/login",
            json={"username": username, "password": password},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["token"]

    def graphql(self, query: str, variables: dict | None = None):
        r = self.session.post(
            f"{self.base_url}/api/graphql",
            json={"query": query, "variables": variables or {}},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"Blad GraphQL: {data['errors']}")
        return data["data"]

    def list_users_with_groups(self):
        """Zwraca liste userow z ich grupami. Jesli pole 'users' na poziomie query
        nie istnieje w tej wersji LLDAP, wypisuje dostepne pola query do diagnostyki."""
        q = """
        query {
          users {
            id
            email
            firstName
            lastName
            displayName
            groups { displayName }
          }
        }
        """
        try:
            data = self.graphql(q)
            return data["users"]
        except RuntimeError as e:
            print(f"BLAD pobierania listy userow: {e}")
            print("Diagnostyka -- dostepne pola 'query' w tej wersji LLDAP:")
            try:
                schema = self.graphql("query { __schema { queryType { fields { name } } } }")
                for f in schema["__schema"]["queryType"]["fields"]:
                    print(f"  - {f['name']}")
            except Exception as e2:
                print(f"  (nie udalo sie pobrac schematu: {e2})")
            sys.exit(1)


class SynapseAdmin:
    def __init__(self, base_url: str, verify, admin_login: str, admin_password: str, domain: str):
        self.base_url = base_url.rstrip("/")
        self.verify = verify
        self.domain = domain
        self.session = requests.Session()
        token = self._login(admin_login, admin_password)
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _login(self, username: str, password: str) -> str:
        if not password or password.startswith("CHANGE_ME"):
            raise RuntimeError(
                "Brak hasla administratora Synapse -- ustaw SYNAPSE_ADMIN_PASSWORD w .env "
                "(wzor: .env.example) albo w zmiennej srodowiskowej."
            )
        r = self.session.post(
            f"{self.base_url}/_matrix/client/r0/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": username},
                "password": password,
            },
            verify=self.verify,
            timeout=10,
        )
        if r.status_code >= 400:
            raise RuntimeError(
                f"Logowanie admina '{username}' nie powiodlo sie: HTTP {r.status_code} - {r.text[:300]}"
            )
        return r.json()["access_token"]

    def upsert_user(self, login: str, displayname: str):
        mxid = f"@{login}:{self.domain}"
        r = self.session.put(
            f"{self.base_url}/_synapse/admin/v2/users/{mxid}",
            json={"displayname": displayname},
            verify=self.verify,
            timeout=10,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} - {r.text[:300]}")
        return r.json()


def build_displayname(user: dict) -> str:
    first = user.get("firstName") or ""
    last = user.get("lastName") or ""
    base = f"{first} {last}".strip() or user["id"]

    group_names = {g["displayName"] for g in (user.get("groups") or [])}
    dept = next((d for d in DEPARTMENTS if d in group_names), None)

    if dept:
        return f"{base} – {dept}"
    # brak dzialu (np. konta zalozone recznie w LLDAP w kroku 8 README) -- samo imie i nazwisko
    return base


def main():
    if not ROOT_CA_PATH.exists():
        print(f"BLAD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)

    lldap_url = resolve_lldap_url()
    lldap_admin_password = os.environ.get("LLDAP_ADMIN_PASSWORD") or load_dotenv_value("LLDAP_ADMIN_PASSWORD")
    if not lldap_admin_password or lldap_admin_password.startswith("CHANGE_ME"):
        print("BLAD: nie znaleziono LLDAP_ADMIN_PASSWORD w .env.")
        sys.exit(1)

    print(f"Lacze sie z LLDAP ({lldap_url})...")
    lldap = LldapReader(lldap_url, "admin", lldap_admin_password)
    all_users = lldap.list_users_with_groups()
    all_users = [u for u in all_users if u["id"] != "admin"]  # pomin konto admina LLDAP
    print(f"Znaleziono {len(all_users)} userow w LLDAP (bez konta 'admin').\n")

    users_to_process = all_users if LIMIT is None else all_users[:LIMIT]
    print(f"Przetworze {len(users_to_process)} z nich w tym uruchomieniu (LIMIT={LIMIT}).\n")

    print(f"Lacze sie z Synapse ({MATRIX_BASE_URL}) jako administrator '{ADMIN_LOGIN}'...")
    try:
        synapse = SynapseAdmin(
            MATRIX_BASE_URL, str(ROOT_CA_PATH), ADMIN_LOGIN, ADMIN_PASSWORD, HOMESERVER_DOMAIN
        )
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia/logowania do Synapse: {e}")
        print("Sprawdz: czy konto ADMIN_LOGIN ma ustawione admin=1 w bazie (README, Etap 0),")
        print("czy haslo sie zgadza, i czy ten PC ma dzialajacy dostep do matrix.local (jak Element).")
        sys.exit(1)
    print("Zalogowano jako administrator Synapse.\n")

    ok, failed = [], []
    for i, user in enumerate(users_to_process, 1):
        login = user["id"]
        displayname = build_displayname(user)
        print(f"[{i}/{len(users_to_process)}] @{login}:{HOMESERVER_DOMAIN} -> \"{displayname}\"")
        try:
            synapse.upsert_user(login, displayname)
            ok.append(login)
        except RuntimeError as e:
            print(f"    BLAD: {e}")
            failed.append(login)

    print("\n=== PODSUMOWANIE ===")
    print(f"Zalozone/zaktualizowane konta: {len(ok)}")
    print(f"Bledy:                         {len(failed)}")
    if failed:
        print("  " + ", ".join(failed))

    if LIMIT is not None:
        print(f"\nTo bylo uruchomienie testowe (LIMIT={LIMIT}).")
        print("Sprawdz w Elemencie: wyszukaj jednego z przetworzonych userow (np. po dziale)")
        print("BEZ logowania sie na jego konto -- jesli go znajdziesz, konto istnieje juz w")
        print("katalogu Synapse mimo braku logowania, czyli dokladnie to co mial zrobic Etap 1.")
        print("Jesli dziala -- ustaw LIMIT = None u gory pliku i uruchom ponownie dla wszystkich.")


if __name__ == "__main__":
    main()
