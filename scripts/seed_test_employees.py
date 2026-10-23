#!/usr/bin/env python3
"""
seed_test_employees.py -- Przygotowanie, B0 (README): generuje testowa strukture firmy w LLDAP.

CEL: utworzyc ~200 fikcyjnych kont pracownikow w LLDAP (przez GraphQL API),
przypisanych do grup-dzialow, z jednym wspolnym haslem
testowym -- zeby sprawdzic w praktyce, jak dziala wbudowany katalog
uzytkownikow Synapse i drzewo Spaces na realnej liczbie kont.

WYLACZNIE DO TESTOW PoC. Nigdy nie uzywac wspolnego hasla na produkcji
z prawdziwymi ludzmi.

=====================================================================
JAK TO DZIALA (dwa kroki, bo LLDAP nie ma prostego REST do hasel)
=====================================================================
KROK 1 (ten skrypt, uruchamiany TUTAJ na Twoim PC):
  Tworzy uzytkownikow i grupy-dzialy przez GraphQL API
  LLDAP -- to dziala bezposrednio przez HTTP, bez problemu z PC.

KROK 2 (plik wygenerowany przez ten skrypt, uruchamiany NA VM):
  Ustawianie hasel w LLDAP korzysta ze wzgledow bezpieczenstwa z protokolu
  PAKE (Opaque), wiec NIE da sie tego zrobic prostym zapytaniem REST z PC
  (sprawdzone empirycznie 2026-10-11 -- endpoint faktycznie "przyjmowal"
  zadanie ze statusem sukcesu, ale hasla NIE dzialaly). Poprawne narzedzie
  do tego to oficjalny binarny `lldap_set_password`, ktory siedzi WEWNATRZ
  kontenera LLDAP na serwerze (sciezka /app/lldap_set_password, NIE jest
  w $PATH -- trzeba wywolywac pelna sciezka). Dlatego ten skrypt generuje
  plik `set_test_passwords.sh`, ktory trzeba skopiowac na VM i uruchomic
  tam (docker compose exec) -- instrukcja wypisuje sie na koncu.

Wymaga: pip install requests
Uzycie:
  python seed_test_employees.py                        # tworzy brakujace grupy i konta
  python seed_test_employees.py --reassign --dry-run   # POKAZ, kogo przepieto by do nowych grup
  python seed_test_employees.py --reassign             # przepnij ISTNIEJACE konta (bez kasowania, bez hasel)

STRUKTURA (README, B0): kazde konto ma DOKLADNIE JEDNA grupe-dzial (7 grup): Ksiegowosc, Projekty,
Dyrekcja, IT, Sprzedaz (siedziba) albo Oddzial A Obsluga / Oddzial B Obsluga
(te dwa to zwykle dzialy, na tym samym poziomie co Ksiegowosc).
Ksiazke adresowa (wszystkie dzialy, jeden plaski pokoj) buduje setup_directory.py (Etap 2).

HASLO TESTOWE: TEST_PASSWORD w .env NA VM (README, krok 5.1) -- czyta je wygenerowany set_test_passwords.sh.
DALEJ: konta w Synapse -- provision_synapse_users.py (README, Etap 1); wymaga Etapu 0 (konto administratora).
"""

import argparse
import os
import random
import sys
import unicodedata
from pathlib import Path

import requests

# ============================================================
# KONFIGURACJA -- edytuj wedle potrzeb
# ============================================================

# Adres panelu/API LLDAP. Domyslnie puste -- skrypt sam zbuduje go z TS_IP
# w Twoim .env (http://<TS_IP>:17170). Wpisz tu cos recznie TYLKO jesli
# chcesz uzyc innego adresu (np. LAN zamiast Tailscale) -- ale wtedy NIE
# commituj tej zmiany do gita (to pole celowo zostaje puste w repozytorium).
LLDAP_URL = ""

ADMIN_USERNAME = "admin"
# Haslo NIE jest tu wpisane na sztywno (zeby nie trafilo do gita).
# Wczytywane automatycznie z pliku .env w katalogu projektu (LLDAP_ADMIN_PASSWORD),
# albo ze zmiennej srodowiskowej o tej samej nazwie, jesli wolisz ja ustawic recznie.

# WSPOLNE haslo testowe kont (TYLKO PoC, nigdy na produkcji) NIE jest w kodzie ani w wygenerowanym
# set_test_passwords.sh: skrypt na VM czyta je z TEST_PASSWORD w .env NA VM (patrz .env.example).
EMAIL_DOMAIN = "matrix.local"

# Ile kont utworzyc w TYM uruchomieniu. USTAW MALA WARTOSC NA PIERWSZY TEST.
LIMIT = None            # np. 3 na start -> sprawdz czy dziala -> potem None = wszyscy
TOTAL_TARGET = 200   # docelowa liczba kont przy LIMIT = None

# Kazde konto ma jedna grupe-dzial. Oddzialy (A, B) to zwykle dzialy, na tym samym poziomie co pozostale.
DEPARTMENTS = ["Księgowość", "Projekty", "Dyrekcja", "IT", "Sprzedaż",
               "Oddział A Obsługa", "Oddział B Obsługa"]
# Rozklad kont miedzy dzialy (siedziba = 5 pierwszych ~70%, po ~15% na kazdy Oddzial).
# To zalozenie TESTOWE, nie dane firmy.
DEPARTMENT_WEIGHTS = [14, 14, 14, 14, 14, 15, 15]
# Stare grupy lokalizacji z poprzednich seedow -- --reassign wyjmuje z nich konta (grup nie kasuje).
LEGACY_LOCATIONS = ["Warszawa", "Kraków", "Poznań"]

# Plik wynikowy ze skryptem do uruchomienia NA VM (ustawia hasla).
PASSWORD_SCRIPT_PATH = Path(__file__).resolve().parent / "set_test_passwords.sh"

# ============================================================

FIRST_NAMES_M = [
    "Jan", "Piotr", "Krzysztof", "Andrzej", "Tomasz", "Paweł", "Marcin", "Michał",
    "Grzegorz", "Tadeusz", "Jerzy", "Marek", "Łukasz", "Adam", "Zbigniew", "Rafał",
    "Dariusz", "Wojciech", "Stanisław", "Kamil", "Jacek", "Mariusz", "Sławomir",
    "Artur", "Robert", "Damian", "Bartosz", "Mateusz", "Przemysław", "Konrad",
    "Wiesław", "Ryszard", "Henryk", "Daniel", "Sebastian", "Patryk", "Kacper",
    "Dawid", "Filip", "Maciej", "Norbert", "Ireneusz", "Zdzisław", "Leszek",
    "Waldemar", "Czesław", "Edward", "Kazimierz", "Józef", "Roman",
]
FIRST_NAMES_F = [
    "Anna", "Maria", "Katarzyna", "Małgorzata", "Agnieszka", "Barbara", "Ewa",
    "Elżbieta", "Krystyna", "Magdalena", "Joanna", "Teresa", "Danuta", "Monika",
    "Aleksandra", "Urszula", "Dorota", "Halina", "Beata", "Jadwiga", "Marta",
    "Renata", "Grażyna", "Jolanta", "Iwona", "Natalia", "Karolina", "Justyna",
    "Paulina", "Marzena", "Izabela", "Edyta", "Violetta", "Bożena", "Irena",
    "Wioletta", "Sylwia", "Ewelina", "Patrycja", "Klaudia", "Dominika", "Zofia",
    "Helena", "Janina", "Stanisława", "Wanda", "Alicja", "Weronika", "Oliwia", "Julia",
]
LAST_NAMES = [
    "Kowalski", "Nowak", "Wiśniewski", "Wójcik", "Kowalczyk", "Kamiński",
    "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski",
    "Jankowski", "Mazur", "Kwiatkowski", "Krawczyk", "Piotrowski", "Grabowski",
    "Nowakowski", "Pawłowski", "Michalski", "Nowicki", "Adamczyk", "Dudek",
    "Zając", "Wieczorek", "Jabłoński", "Król", "Majewski", "Olszewski",
    "Jaworski", "Malinowski", "Stępień", "Górski", "Rutkowski", "Michalak",
    "Sikora", "Baran", "Walczak", "Szewczyk", "Tomaszewski", "Wróbel",
    "Pietrzak", "Marciniak", "Wróblewski", "Zalewski", "Witkowski", "Sadowski",
    "Chmielewski", "Cieślak",
]


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


def strip_pl(s: str) -> str:
    """Usuwa polskie znaki diakrytyczne (ł/Ł obslugiwane recznie, reszta przez NFKD)."""
    s = s.replace("ł", "l").replace("Ł", "L")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def generate_employees(n: int):
    """Losuje n unikalnych pracownikow (login w formacie i.nazwisko, jak j.kowalski)."""
    random.seed(42)  # powtarzalnosc miedzy uruchomieniami (ten sam zestaw dla tego samego n)
    assign_rng = random.Random(7)  # OSOBNY generator: przydzial do lokalizacji/dzialu (nie rusza loginow)
    pool = FIRST_NAMES_M + FIRST_NAMES_F
    employees = []
    seen_logins = set()
    attempts = 0
    while len(employees) < n and attempts < n * 30:
        attempts += 1
        first = random.choice(pool)
        last = random.choice(LAST_NAMES)
        # UWAGA: dwa ponizsze losowania sa celowo zachowane (wynik wyrzucany). Dzieki nim strumien
        # losowy (seed 42) daje TE SAME loginy co przy pierwszym seedzie, wiec --reassign trafia
        # w istniejace konta. NIE usuwac i NIE zmieniac kolejnosci.
        random.randrange(5)   # dawniej choice(DEPARTMENTS), 5 elementow
        random.randrange(3)   # dawniej choice(LOCATIONS), 3 elementy
        department = assign_rng.choices(DEPARTMENTS, weights=DEPARTMENT_WEIGHTS)[0]
        base_login = f"{strip_pl(first[0]).lower()}.{strip_pl(last).lower()}"
        login = base_login
        suffix = 1
        while login in seen_logins:
            suffix += 1
            login = f"{base_login}{suffix}"
        seen_logins.add(login)
        employees.append({
            "login": login,
            "first_name": first,
            "last_name": last,
            "display_name": f"{first} {last}",
            "email": f"{login}@{EMAIL_DOMAIN}",
            "department": department,
        })
    return employees


class LldapAdmin:
    def __init__(self, base_url: str, username: str, password: str, dry_run: bool = False):
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
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

    def list_groups(self) -> dict:
        data = self.graphql("query { groups { id displayName } }")
        return {g["displayName"]: g["id"] for g in data["groups"]}

    def ensure_group(self, name: str, existing: dict) -> int:
        if name in existing:
            return existing[name]
        if self.dry_run:
            print(f"  [dry-run] utworzylbym grupe {name}")
            existing[name] = -1
            return -1
        q = "mutation($name: String!) { createGroup(name: $name) { id } }"
        data = self.graphql(q, {"name": name})
        gid = data["createGroup"]["id"]
        existing[name] = gid
        print(f"  [grupa utworzona] {name} (id={gid})")
        return gid

    def user_exists(self, user_id: str) -> bool:
        q = "query($id: String!) { user(userId: $id) { id } }"
        try:
            self.graphql(q, {"id": user_id})
            return True
        except RuntimeError:
            return False

    def create_user(self, emp: dict):
        if self.dry_run:
            return
        q = """
        mutation($user: CreateUserInput!) {
          createUser(user: $user) { id }
        }
        """
        variables = {
            "user": {
                "id": emp["login"],
                "email": emp["email"],
                "displayName": emp["display_name"],
                "firstName": emp["first_name"],
                "lastName": emp["last_name"],
            }
        }
        self.graphql(q, variables)

    def add_user_to_group(self, user_id: str, group_id: int):
        if self.dry_run:
            return
        q = """
        mutation($userId: String!, $groupId: Int!) {
          addUserToGroup(userId: $userId, groupId: $groupId) { ok }
        }
        """
        self.graphql(q, {"userId": user_id, "groupId": group_id})

    def user_groups(self, user_id: str) -> list:
        q = "query($id: String!) { user(userId: $id) { groups { id displayName } } }"
        return self.graphql(q, {"id": user_id})["user"]["groups"]

    def remove_user_from_group(self, user_id: str, group_id: int):
        if self.dry_run:
            return
        q = """
        mutation($userId: String!, $groupId: Int!) {
          removeUserFromGroup(userId: $userId, groupId: $groupId) { ok }
        }
        """
        self.graphql(q, {"userId": user_id, "groupId": group_id})


def reassign_user(admin: "LldapAdmin", emp: dict, group_ids: dict) -> bool:
    """Przepina ISTNIEJACE konto do grupy-dzialu wynikajacej z emp.
    Rusza tylko grupy 'zarzadzane' (DEPARTMENTS, LEGACY_LOCATIONS) -- inne zostawia.
    Zwraca True, jesli cos sie zmienilo (albo by sie zmienilo w --dry-run)."""
    managed = set(DEPARTMENTS) | set(LEGACY_LOCATIONS)
    wanted = {emp["department"]}
    current = {g["displayName"]: g["id"] for g in admin.user_groups(emp["login"])}
    to_remove = [n for n in current if n in managed and n not in wanted]
    to_add = [n for n in wanted if n not in current]
    for name in to_remove:
        print(f"    - wyjmuje z grupy {name}")
        admin.remove_user_from_group(emp["login"], current[name])
    for name in to_add:
        print(f"    + dodaje do grupy {name}")
        admin.add_user_to_group(emp["login"], group_ids[name])
    return bool(to_remove or to_add)


def write_password_script(logins: list[str]):
    """
    Generuje plik bash do uruchomienia NA VM -- ustawia hasla przez oficjalne
    narzedzie /app/lldap_set_password WEWNATRZ kontenera lldap (jedyna
    potwierdzona dzialajaca droga -- patrz naglowek pliku).
    """
    users_block = " ".join(f'"{login}"' for login in logins)
    script = f"""#!/usr/bin/env bash
# Wygenerowano automatycznie przez seed_test_employees.py -- NIE edytuj recznie.
# Uruchom NA VM, w katalogu /opt/matrix (tam gdzie jest docker-compose.yml):
#   bash scripts/set_test_passwords.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "BLAD: nie znaleziono .env w $(pwd) -- uruchom ten skrypt z katalogu /opt/matrix"
  exit 1
fi
source .env

if [ -z "${{LLDAP_ADMIN_PASSWORD:-}}" ]; then
  echo "BLAD: LLDAP_ADMIN_PASSWORD nie jest ustawione w .env"
  exit 1
fi
if [ -z "${{TEST_PASSWORD:-}}" ] || [[ "$TEST_PASSWORD" == CHANGE_ME* ]]; then
  echo "BLAD: TEST_PASSWORD nie jest ustawione w .env (wspolne haslo kont testowych, tylko PoC)"
  exit 1
fi

USERS=({users_block})
PASSWORD="$TEST_PASSWORD"

echo "Ustawiam haslo testowe dla ${{#USERS[@]}} kont..."
for u in "${{USERS[@]}}"; do
  echo "  -> $u"
  docker compose exec -T lldap /app/lldap_set_password \\
    --base-url http://localhost:17170 \\
    --admin-username admin \\
    --admin-password "$LLDAP_ADMIN_PASSWORD" \\
    --username "$u" \\
    --password "$PASSWORD" \\
    --bypass-password-policy
done
echo "Gotowe. Sprobuj zalogowac sie do Elementa jednym z tych kont haslem z TEST_PASSWORD (.env na VM)."
"""
    PASSWORD_SCRIPT_PATH.write_text(script, encoding="utf-8", newline="\n")


def resolve_lldap_url() -> str:
    """LLDAP_URL recznie wpisany u gory pliku ma pierwszenstwo; w przeciwnym razie
    budujemy adres automatycznie z TS_IP w .env (ten sam wzorzec co haslo admina)."""
    if LLDAP_URL.strip():
        return LLDAP_URL.strip()
    ts_ip = os.environ.get("TS_IP") or load_dotenv_value("TS_IP")
    if not ts_ip or "x.x" in ts_ip:
        print("BLAD: nie udalo sie ustalic adresu LLDAP.")
        print("Uzupelnij TS_IP w pliku .env (adres Tailscale VM), albo wpisz adres")
        print("recznie w zmiennej LLDAP_URL u gory tego pliku (wtedy NIE commituj tej zmiany).")
        sys.exit(1)
    return f"http://{ts_ip}:17170"


def main():
    parser = argparse.ArgumentParser(description="Testowa struktura firmy w LLDAP.")
    parser.add_argument("--reassign", action="store_true",
                        help="przepnij ISTNIEJACE konta do grup z aktualnej konfiguracji (bez kasowania kont)")
    parser.add_argument("--dry-run", action="store_true", help="nic nie zapisuj, tylko pokaz co by sie stalo")
    args = parser.parse_args()
    if args.dry_run:
        print("*** TRYB PROBNY (--dry-run): nic nie zostanie zapisane ***\n")

    lldap_url = resolve_lldap_url()
    print(f"Adres LLDAP: {lldap_url}\n")

    admin_password = os.environ.get("LLDAP_ADMIN_PASSWORD") or load_dotenv_value("LLDAP_ADMIN_PASSWORD")
    if not admin_password or admin_password.startswith("CHANGE_ME"):
        print("BLAD: nie znaleziono LLDAP_ADMIN_PASSWORD.")
        print("Uzupelnij plik .env w katalogu projektu (LLDAP_ADMIN_PASSWORD=...),")
        print("albo ustaw zmienna srodowiskowa LLDAP_ADMIN_PASSWORD przed uruchomieniem.")
        sys.exit(1)

    n = LIMIT if LIMIT is not None else TOTAL_TARGET
    employees = generate_employees(n)
    print(f"Wygenerowano {len(employees)} fikcyjnych pracownikow (LIMIT={LIMIT}).\n")

    try:
        admin = LldapAdmin(lldap_url, ADMIN_USERNAME, admin_password, dry_run=args.dry_run)
    except requests.RequestException as e:
        print(f"BLAD polaczenia/logowania do LLDAP ({lldap_url}): {e}")
        sys.exit(1)
    print("Zalogowano do LLDAP jako admin.\n")

    existing_groups = admin.list_groups()
    print(f"Istniejace grupy w LLDAP: {list(existing_groups.keys())}\n")

    print("Tworze/sprawdzam grupy dzialow...")
    for dept in DEPARTMENTS:
        admin.ensure_group(dept, existing_groups)
    print()

    created, skipped = [], []
    reassigned, unchanged = [], []
    all_logins = []

    for i, emp in enumerate(employees, 1):
        login = emp["login"]
        all_logins.append(login)
        print(f"[{i}/{len(employees)}] {emp['display_name']} ({login}) - {emp['department']}")

        if admin.user_exists(login):
            if args.reassign:
                if reassign_user(admin, emp, existing_groups):
                    reassigned.append(login)
                else:
                    print("    grupy juz poprawne")
                    unchanged.append(login)
            else:
                print("    juz istnieje - pomijam tworzenie konta (haslo i tak zostanie ustawione ponownie)")
            skipped.append(login)
        else:
            try:
                admin.create_user(emp)
            except RuntimeError as e:
                print(f"    BLAD tworzenia konta: {e}")
                all_logins.remove(login)
                continue
            admin.add_user_to_group(login, existing_groups[emp["department"]])
            created.append(login)

    if args.reassign:
        # Istniejace konta maja juz hasla -- skrypt hasel tylko dla nowo utworzonych.
        if created and not args.dry_run:
            write_password_script(created)
        print("\n=== PODSUMOWANIE (--reassign) ===" + (" [dry-run]" if args.dry_run else ""))
        print(f"Przepiete konta:         {len(reassigned)}")
        print(f"Bez zmian:               {len(unchanged)}")
        print(f"Nowo utworzone:          {len(created)}")
        by_dep = {}
        for e in employees:
            by_dep[e["department"]] = by_dep.get(e["department"], 0) + 1
        print("Rozklad dzialow:         " + ", ".join(f"{k}: {v}" for k, v in by_dep.items()))
        legacy = [g for g in LEGACY_LOCATIONS if g in existing_groups]
        if legacy:
            print(f"Stare grupy zostaja w LLDAP (puste po przepieciu, usun recznie w panelu): {', '.join(legacy)}")
        if created:
            print("Nowe konta wymagaja ustawienia hasel -- uzyj wygenerowanego set_test_passwords.sh na VM.")
        return

    if not args.dry_run:
        write_password_script(all_logins)

    print("\n=== PODSUMOWANIE ===")
    print(f"Utworzone konta:           {len(created)}")
    print(f"Pominiete (juz istnialy):  {len(skipped)}")
    print(f"Konta do ustawienia hasla: {len(all_logins)} (wszystkie z tego uruchomienia)")

    print(f"\n>>> KOLEJNY KROK (obowiazkowy, inaczej hasla NIE beda dzialac) <<<")
    print(f"Wygenerowano plik: {PASSWORD_SCRIPT_PATH}")
    print("Skopiuj go na VM i uruchom tam (haslo ustawia sie WYLACZNIE przez narzedzie")
    print("wewnatrz kontenera LLDAP, nie da sie tego zrobic zdalnym REST-em z PC):\n")
    print(f"  scp \"{PASSWORD_SCRIPT_PATH}\" <UZYTKOWNIK>@<IP_VM>:/opt/matrix/scripts/")
    print("  ssh <UZYTKOWNIK>@<IP_VM>")
    print("  cd /opt/matrix")
    print("  bash scripts/set_test_passwords.sh")
    print("\nPotem (PC): provision_synapse_users.py -- konta w Synapse z dzialem w nazwie wyswietlanej (README, Etap 1).")

    if LIMIT is not None:
        print(f"\nTo bylo uruchomienie testowe (LIMIT={LIMIT}).")
        print("Po uruchomieniu skryptu z haslami NA VM, sprobuj zalogowac sie do Elementa.")
        print("Jesli zadziala -- ustaw LIMIT = None u gory pliku i uruchom ponownie dla")
        print(f"pelnej puli ({TOTAL_TARGET} kont), a potem powtorz krok ze skryptem hasel na VM")
        print("(nowy plik set_test_passwords.sh bedzie zawieral wszystkich, w tym juz istniejacych)")


if __name__ == "__main__":
    main()
