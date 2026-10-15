#!/usr/bin/env python3
"""
UWAGA (2026-10-14): POKOJE I WIDGET WYCOFANE. Decyzja uzytkownika: ksiazka adresowa = space 'Firma'
+ podprzestrzenie-dzialy (scripts/setup_spaces.py); widget okazal sie slepym zaulkiem, a pokoje
'Firma-Ogloszenia' i 'Struktura organizacyjna' zostaly usuniete (w razie potrzeby admin zaklada
pokoj recznie w Elemencie). NIE URUCHAMIAJ tego pliku jako skryptu -- zalozylby usuniete pokoje
od nowa. Plik ZOSTAJE wylacznie jako biblioteka: setup_spaces.py importuje z niego klase Synapse,
cfg(), ensure_name_topic() i stale. TODO: wydzielic te elementy do wspolnego modulu
(np. matrix_common.py) i dopiero wtedy usunac ten plik.

setup_main_room.py -- (HISTORIA) pokoje glowne dla calej firmy (oba tylko do odczytu): zaklada je
(jesli trzeba), dolacza do nich wszystkich uzytkownikow Synapse i ustawia w jednym z nich
widget-sciage (widget/index.html) na cale okno pokoju.

DWA POKOJE (te same zasady uprawnien i ta sama lista piszacych):
  1. "Firma-Ogloszenia"        -- tablica ogloszen, BEZ widgetu
  2. "Struktura organizacyjna" -- widget-sciaga przypiety u gory na 100% wysokosci pokoju

DLACZEGO TAK: widget w Matrixie jest przypisany do POKOJU (to zdarzenie stanu
pokoju), a nie do uzytkownika ani do calego serwera. Nie ma ustawienia "widget
dla wszystkich". Zeby kazdy pracownik go mial, musi byc w pokoju, w ktorym admin
(ten skrypt) ustawil widget i jego uklad. Klient (Element) nie pozwala serwerowi
ustawic szerokosci panelu bocznego ani otworzyc go automatycznie -- stad osobny pokoj,
w ktorym widget zajmuje cale okno, zamiast widgetu obok ogloszen.

CO ROBI (kazdy krok jest idempotentny -- skrypt mozna puszczac wielokrotnie), dla kazdego pokoju:
  1. Loguje sie do Synapse jako administrator (to samo konto co provision_synapse_users.py).
  2. Znajduje pokoj po aliasie; jesli go nie ma -- tworzy.
     Przy uzyciu --only mozna tez wskazac istniejacy pokoj przez --room-id.
  3. Ustawia nazwe i temat pokoju oraz poziomy uprawnien: tylko administrator moze zmieniac
     widget, jego uklad, nazwe, temat i uprawnienia pokoju. Przy MAIN_ROOM_READONLY=true pokoje
     sa "tablicami" -- czytaja wszyscy, pisza tylko admin i osoby z MAIN_ROOM_WRITERS
     (reakcje emoji zostaja dozwolone dla wszystkich). Lista w .env jest zrodlem prawdy.
  4. Dolacza do pokoju wszystkie lokalne konta (Admin API, bez zaproszen i klikania).
     Pomija osoby, ktore juz sa w pokoju, oraz te, ktore swiadomie z niego wyszly
     (zeby ich nie "wciagac" z powrotem) -- chyba ze podasz --rejoin.
  5. Pokoj ze widgetem: ustawia widget (adres z WIDGET_URL w .env) i przypina go u gory
     (zdarzenie io.element.widgets.layout) na 100% wysokosci.
     Pokoj bez widgetu: usuwa widget i jego przypiecie, jesli wczesniej tam byly.

UWAGA -- NIESPRAWDZONE W PRAKTYCE: formaty zdarzen stanu (im.vector.modular.widgets,
io.element.widgets.layout) sa napisane na podstawie tego, jak dziala Element, nie na
podstawie dzialajacego testu. Zwlaszcza wysokosc 100% -- Element moze ja ograniczyc.
Gdyby widget nie zajal calego okna, mozna go rozwinac przyciskiem "powieksz" w jego
naglowku. Zanim zaufasz skryptowi: dodaj widget raz recznie (/addwidget <adres> w pokoju),
obejrzyj zapisane zdarzenie w Elemencie (/devtools -> Eksploruj stan pokoju ->
im.vector.modular.widgets) i porownaj z tym, co zapisuje skrypt.

WYMAGANIA WSTEPNE:
  - Konta w Synapse istnieja (provision_synapse_users.py) i dziala konto administratora
    Synapse (README, Etap B + C), a nginx przepuszcza /_synapse/admin.
  - W .env (wzor: .env.example): WIDGET_URL (adres, ktory MUSI dzialac na KAZDYM kliencie --
    patrz README) oraz opcjonalnie MAIN_ROOM_NAME, MAIN_ROOM_ALIAS, MAIN_ROOM_TOPIC
    (pokoj ogloszen), ORG_ROOM_NAME, ORG_ROOM_ALIAS, ORG_ROOM_TOPIC (pokoj ze struktura),
    MAIN_ROOM_READONLY (true/false), MAIN_ROOM_WRITERS (loginy po przecinku).
  - PC ma dostep do https://matrix.local jak Element Desktop (hosts + rootCA).

Wymaga: pip install requests
Uzycie:
  python setup_main_room.py --dry-run                    # tylko pokaz, co by zrobil (oba pokoje)
  python setup_main_room.py                              # wykonaj dla obu pokoi
  python setup_main_room.py --only struktura             # tylko jeden pokoj (ogloszenia | struktura)
  python setup_main_room.py --only struktura --skip-join # bez dolaczania uzytkownikow
  python setup_main_room.py --only ogloszenia --room-id '!abc:matrix.local'   # istniejacy pokoj
"""

import argparse
import copy
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

# ============================================================
# KONFIGURACJA
# ============================================================

MATRIX_BASE_URL = "https://matrix.local"
ROOT_CA_PATH = Path(__file__).resolve().parent.parent / "rootCA.pem"

# Konto administratora Synapse -- to samo co w provision_synapse_users.py (PoC).
ADMIN_LOGIN = "s.lewandowski"
ADMIN_PASSWORD = "TestHaslo123!"
HOMESERVER_DOMAIN = "matrix.local"

# Pokoje -- WARTOSCI DOMYSLNE; nadpisywane z .env (MAIN_ROOM_* dla ogloszen, ORG_ROOM_* dla struktury).
DEFAULT_ROOMS = {
    "ogloszenia": {
        "env": "MAIN_ROOM",
        "alias": "firma-ogloszenia",  # alias: #firma-ogloszenia:<domena>
        "name": "Firma-Ogłoszenia",
        "topic": "Ogłoszenia dla wszystkich pracowników (tylko do odczytu)",
        "widget": False,
    },
    "struktura": {
        "env": "ORG_ROOM",
        "alias": "struktura-organizacyjna",
        "name": "Struktura organizacyjna",
        "topic": "Ściąga: kto jest kim w firmie (tylko do odczytu)",
        "widget": True,
    },
}

WRITER_LEVEL = 50   # poziom uprawnien osob z MAIN_ROOM_WRITERS (moga pisac w pokojach tylko do odczytu)

# Widget
WIDGET_ID = "firma-sciaga"                 # stały identyfikator (dzieki temu skrypt jest idempotentny)
WIDGET_NAME = "Struktura firmy"
WIDGET_EVENT_TYPE = "im.vector.modular.widgets"
LAYOUT_EVENT_TYPE = "io.element.widgets.layout"

# Gdzie w pokoju pokazac widget: "top" (pasek u gory pokoju, widoczny od razu),
# "right" (panel Rozszerzenia -- NIE otwiera sie sam) albo "center".
LAYOUT_CONTAINER = "top"
LAYOUT_HEIGHT = 100   # procent wysokosci okna pokoju (dla "top"); 100 = widget na cale okno

# Zdarzenia, ktore moze zmieniac tylko administrator (poziom 100).
ADMIN_ONLY_EVENTS = [
    WIDGET_EVENT_TYPE, "m.widget", LAYOUT_EVENT_TYPE,
    "m.room.name", "m.room.topic", "m.room.avatar",
    "m.room.power_levels", "m.room.join_rules", "m.room.history_visibility",
]

# ============================================================


def load_dotenv_value(key: str) -> str:
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


def cfg(key: str, default: str = "") -> str:
    """Wartosc ze zmiennej srodowiskowej albo z .env (w tej kolejnosci), inaczej domyslna."""
    return os.environ.get(key) or load_dotenv_value(key) or default


def q(s: str) -> str:
    """Kodowanie fragmentu sciezki URL (room_id i alias maja ! # : )."""
    return quote(s, safe="")


def build_room_specs() -> dict:
    """Specyfikacje pokoi: wartosci domyslne nadpisane z .env / zmiennych srodowiskowych."""
    specs = {}
    for key, d in DEFAULT_ROOMS.items():
        prefix = d["env"]
        specs[key] = {
            "key": key,
            "alias": cfg(f"{prefix}_ALIAS", d["alias"]).lstrip("#").split(":")[0],
            "name": cfg(f"{prefix}_NAME", d["name"]),
            "topic": cfg(f"{prefix}_TOPIC", d["topic"]),
            "widget": d["widget"],
        }
    return specs


class Synapse:
    def __init__(self, base_url: str, verify, domain: str):
        self.base_url = base_url.rstrip("/")
        self.verify = verify
        self.domain = domain
        self.session = requests.Session()
        self.admin_mxid = ""

    def login(self, username: str, password: str):
        for attempt in range(6):
            r = self.session.post(
                f"{self.base_url}/_matrix/client/v3/login",
                json={
                    "type": "m.login.password",
                    "identifier": {"type": "m.id.user", "user": username},
                    "password": password,
                },
                verify=self.verify,
                timeout=10,
            )
            if r.status_code != 429:
                break
            wait = 15.0
            try:
                wait = r.json().get("retry_after_ms", 15000) / 1000 + 0.5
            except ValueError:
                pass
            print(f"  (limit prob logowania, czekam {wait:.0f}s)")
            time.sleep(wait)
        if r.status_code >= 400:
            raise RuntimeError(
                f"Logowanie admina '{username}' nie powiodlo sie: HTTP {r.status_code} - {r.text[:300]}"
            )
        data = r.json()
        self.session.headers["Authorization"] = f"Bearer {data['access_token']}"
        self.admin_mxid = data["user_id"]

    def call(self, method: str, path: str, ok_statuses=(), **kwargs):
        """Wywolanie API z ponawianiem przy 429 (limiter zapytan Synapse)."""
        for attempt in range(6):
            r = self.session.request(
                method, f"{self.base_url}{path}", verify=self.verify, timeout=30, **kwargs
            )
            if r.status_code == 429:
                wait = 2.0
                try:
                    wait = r.json().get("retry_after_ms", 2000) / 1000 + 0.2
                except ValueError:
                    pass
                print(f"    (limit zapytan, czekam {wait:.1f}s)")
                time.sleep(wait)
                continue
            if r.status_code >= 400 and r.status_code not in ok_statuses:
                raise RuntimeError(f"HTTP {r.status_code} - {r.text[:300]}")
            return r
        raise RuntimeError("Zbyt wiele odpowiedzi 429 (limit zapytan) -- sprobuj ponownie pozniej.")

    # --- pokoj ---

    def find_room_by_alias(self, alias: str):
        r = self.call("GET", f"/_matrix/client/v3/directory/room/{q(alias)}", ok_statuses=(404,))
        if r.status_code == 404:
            return None
        return r.json()["room_id"]

    def create_room(self, spec: dict) -> str:
        body = {
            "room_alias_name": spec["alias"],
            "name": spec["name"],
            "topic": spec["topic"],
            "preset": "private_chat",
            "visibility": "private",
            "power_level_content_override": {
                "events": {ev: 100 for ev in ADMIN_ONLY_EVENTS},
            },
        }
        r = self.call("POST", "/_matrix/client/v3/createRoom", json=body)
        return r.json()["room_id"]

    def get_state(self, room_id: str, event_type: str, state_key: str = ""):
        path = f"/_matrix/client/v3/rooms/{q(room_id)}/state/{q(event_type)}/{q(state_key)}"
        r = self.call("GET", path, ok_statuses=(404,))
        return None if r.status_code == 404 else r.json()

    def put_state(self, room_id: str, event_type: str, content: dict, state_key: str = ""):
        path = f"/_matrix/client/v3/rooms/{q(room_id)}/state/{q(event_type)}/{q(state_key)}"
        self.call("PUT", path, json=content)

    def room_memberships(self, room_id: str) -> dict:
        """mxid -> membership (join / leave / invite / ban)."""
        r = self.call("GET", f"/_matrix/client/v3/rooms/{q(room_id)}/members")
        return {e["state_key"]: e["content"].get("membership") for e in r.json().get("chunk", [])}

    # --- uzytkownicy ---

    def list_local_users(self):
        users, token = [], None
        while True:
            params = {"limit": 100, "deactivated": "false", "guests": "false"}
            if token:
                params["from"] = token
            r = self.call("GET", "/_synapse/admin/v2/users", params=params)
            data = r.json()
            users.extend(u["name"] for u in data.get("users", []))
            token = data.get("next_token")
            if not token:
                break
        return [u for u in users if u.endswith(f":{self.domain}")]

    def force_join(self, room_id: str, mxid: str):
        self.call("POST", f"/_synapse/admin/v1/join/{q(room_id)}", json={"user_id": mxid})


def ensure_name_topic(syn: Synapse, room_id: str, spec: dict, dry_run: bool):
    for event_type, key, value in (
        ("m.room.name", "name", spec["name"]),
        ("m.room.topic", "topic", spec["topic"]),
    ):
        current = syn.get_state(room_id, event_type) or {}
        if current.get(key) == value:
            continue
        print(f"  {key}: ustawiam \"{value}\".")
        if not dry_run:
            syn.put_state(room_id, event_type, {key: value})


def ensure_power_levels(syn: Synapse, room_id: str, readonly: bool, writers: list, dry_run: bool):
    """Uprawnienia pokoju. Lista 'writers' z .env jest zrodlem prawdy dla poziomu WRITER_LEVEL:
    osoby z tym poziomem, ktorych na liscie nie ma, wracaja do zwyklych uzytkownikow."""
    old = syn.get_state(room_id, "m.room.power_levels") or {}
    new = copy.deepcopy(old)
    events = new.setdefault("events", {})
    users = new.setdefault("users", {})

    for ev in ADMIN_ONLY_EVENTS:
        if events.get(ev, 0) < 100:
            events[ev] = 100

    if readonly:
        new["events_default"] = WRITER_LEVEL   # pisanie wymaga poziomu piszacego
        events["m.reaction"] = 0               # ale reakcje (emoji) moga dawac wszyscy
        new["kick"] = 100
        new["ban"] = 100
        new["invite"] = 100
        wanted = set(writers)
    else:
        new["events_default"] = 0
        events.pop("m.reaction", None)
        new["kick"] = 50
        new["ban"] = 50
        new["invite"] = 0
        wanted = set()

    for mxid in wanted:
        if users.get(mxid, 0) < WRITER_LEVEL:
            users[mxid] = WRITER_LEVEL
    for mxid, level in list(users.items()):
        if level == WRITER_LEVEL and mxid not in wanted:
            del users[mxid]

    if new == old:
        print("  Uprawnienia: juz poprawne.")
        return
    mode = "tylko do odczytu" if readonly else "zwykly pokoj"
    print(f"  Uprawnienia: ustawiam tryb '{mode}', piszacych z .env: {len(wanted)}.")
    if not dry_run:
        syn.put_state(room_id, "m.room.power_levels", new)


def ensure_widget(syn: Synapse, room_id: str, widget_url: str, dry_run: bool):
    desired = {
        "type": "m.custom",
        "url": widget_url,
        "name": WIDGET_NAME,
        "data": {},
        "creatorUserId": syn.admin_mxid,
    }
    current = syn.get_state(room_id, WIDGET_EVENT_TYPE, WIDGET_ID)
    if current and current.get("url") == widget_url and current.get("name") == WIDGET_NAME:
        print("  Widget: juz ustawiony z tym samym adresem.")
    else:
        print(f"  Widget: {'aktualizuje' if current else 'dodaje'} ({widget_url}).")
        if not dry_run:
            syn.put_state(room_id, WIDGET_EVENT_TYPE, desired, WIDGET_ID)

    layout = {
        "widgets": {
            WIDGET_ID: {"container": LAYOUT_CONTAINER, "index": 0, "height": LAYOUT_HEIGHT}
        }
    }
    current_layout = syn.get_state(room_id, LAYOUT_EVENT_TYPE)
    if current_layout == layout:
        print(f"  Uklad: widget juz przypiety ({LAYOUT_CONTAINER}, wysokosc {LAYOUT_HEIGHT}%).")
    else:
        print(f"  Uklad: przypinam widget ({LAYOUT_CONTAINER}, wysokosc {LAYOUT_HEIGHT}%).")
        if not dry_run:
            syn.put_state(room_id, LAYOUT_EVENT_TYPE, layout)


def ensure_no_widget(syn: Synapse, room_id: str, dry_run: bool):
    """Pokoj bez widgetu: usuwa widget i jego przypiecie, jesli wczesniej zostaly ustawione."""
    current = syn.get_state(room_id, WIDGET_EVENT_TYPE, WIDGET_ID)
    if current:
        print("  Widget: usuwam (ten pokoj ma byc bez widgetu).")
        if not dry_run:
            syn.put_state(room_id, WIDGET_EVENT_TYPE, {}, WIDGET_ID)
    else:
        print("  Widget: brak (tak ma byc).")

    current_layout = syn.get_state(room_id, LAYOUT_EVENT_TYPE)
    if current_layout and current_layout.get("widgets"):
        print("  Uklad: czyszcze przypiecie widgetu.")
        if not dry_run:
            syn.put_state(room_id, LAYOUT_EVENT_TYPE, {"widgets": {}})
    else:
        print("  Uklad: brak przypietych widgetow (tak ma byc).")


def join_everyone(syn: Synapse, room_id: str, rejoin: bool, dry_run: bool):
    users = syn.list_local_users()
    members = syn.room_memberships(room_id) if room_id else {}
    to_join, already, left = [], 0, 0
    for mxid in users:
        m = members.get(mxid)
        if m == "join":
            already += 1
        elif m in ("leave", "ban") and not rejoin:
            left += 1
        else:
            to_join.append(mxid)

    print(f"  Konta lokalne w Synapse: {len(users)}")
    print(f"  Juz w pokoju: {already} | wyszli/wyrzuceni (pomijam): {left} | do dolaczenia: {len(to_join)}")
    if dry_run or not to_join:
        return

    failed = []
    for i, mxid in enumerate(to_join, 1):
        try:
            syn.force_join(room_id, mxid)
            print(f"  [{i}/{len(to_join)}] {mxid} -> dolaczony")
        except RuntimeError as e:
            print(f"  [{i}/{len(to_join)}] {mxid} -> BLAD: {e}")
            failed.append(mxid)
    print(f"  Dolaczono: {len(to_join) - len(failed)}, bledy: {len(failed)}")
    if failed:
        print("  Bledy: " + ", ".join(failed))


def setup_room(syn: Synapse, spec: dict, args, readonly: bool, writers: list, widget_url: str):
    alias = f"#{spec['alias']}:{HOMESERVER_DOMAIN}"
    kind = "ze widgetem" if spec["widget"] else "bez widgetu"
    print(f"=================== \"{spec['name']}\" ({alias}) -- {kind} ===================")

    # --- 1. pokoj ---
    if args.room_id:
        room_id = args.room_id
        print(f"[1/4] Pokoj: uzywam wskazanego {room_id}")
    else:
        room_id = syn.find_room_by_alias(alias)
        if room_id:
            print(f"[1/4] Pokoj: istnieje ({alias} -> {room_id})")
        elif args.dry_run:
            print(f"[1/4] Pokoj: {alias} nie istnieje -- zostalby utworzony.")
        else:
            room_id = syn.create_room(spec)
            print(f"[1/4] Pokoj: utworzony ({alias} -> {room_id})")

    if not room_id:
        print("  (tryb probny: pokoj jeszcze nie istnieje, wiec dalsze kroki pominiete)\n")
        return

    # --- 2. uprawnienia ---
    print("[2/4] Nazwa, temat i uprawnienia")
    ensure_name_topic(syn, room_id, spec, args.dry_run)
    ensure_power_levels(syn, room_id, readonly, writers, args.dry_run)

    # --- 3. dolaczenie uzytkownikow ---
    print("[3/4] Dolaczanie uzytkownikow")
    if args.skip_join:
        print("  Pominieto (--skip-join).")
    else:
        join_everyone(syn, room_id, args.rejoin, args.dry_run)

    # --- 4. widget ---
    print("[4/4] Widget")
    if spec["widget"]:
        ensure_widget(syn, room_id, widget_url, args.dry_run)
    else:
        ensure_no_widget(syn, room_id, args.dry_run)
    print()


def main():
    parser = argparse.ArgumentParser(description="Pokoje glowne (tylko do odczytu) z widgetem dla wszystkich.")
    parser.add_argument("--dry-run", action="store_true", help="tylko pokaz, co by zrobil (bez zapisu)")
    parser.add_argument("--only", choices=list(DEFAULT_ROOMS), help="obsluz tylko jeden pokoj (domyslnie oba)")
    parser.add_argument("--room-id", help="uzyj istniejacego pokoju zamiast aliasu (wymaga --only; np. '!abc:matrix.local')")
    parser.add_argument("--skip-join", action="store_true", help="nie dolaczaj uzytkownikow")
    parser.add_argument("--rejoin", action="store_true",
                        help="dolacz tez osoby, ktore wczesniej same wyszly z pokoju")
    args = parser.parse_args()

    if args.room_id and not args.only:
        print("BLAD: --room-id wymaga wskazania pokoju przez --only (ogloszenia | struktura).")
        sys.exit(1)

    specs = build_room_specs()
    selected = [specs[args.only]] if args.only else list(specs.values())
    need_widget = any(s["widget"] for s in selected)

    widget_url = os.environ.get("WIDGET_URL") or load_dotenv_value("WIDGET_URL")
    if need_widget:
        if not widget_url or "<" in widget_url:
            print("BLAD: brak WIDGET_URL w .env. Dopisz np.:")
            print("  WIDGET_URL=https://<PELNA-NAZWA-TS>/widget/")
            print("(adres widgetu, ktory dziala na KAZDYM kliencie -- patrz README)")
            sys.exit(1)
        if not widget_url.startswith("https://"):
            print("BLAD: WIDGET_URL musi zaczynac sie od https:// (Element zablokuje http jako mixed content).")
            sys.exit(1)
        if "matrix.local" in widget_url:
            print("UWAGA: WIDGET_URL wskazuje na matrix.local -- ten adres rozwiaza tylko komputer z wpisem")
            print("       w hosts i zaufanym rootCA (nie telefon). Szczegoly w README.\n")

    if not ROOT_CA_PATH.exists():
        print(f"BLAD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)

    if args.dry_run:
        print("*** TRYB PROBNY (--dry-run): nic nie zostanie zapisane ***\n")

    readonly = cfg("MAIN_ROOM_READONLY", "true").strip().lower() in ("1", "true", "yes", "tak")
    writers = []
    for w in cfg("MAIN_ROOM_WRITERS").split(","):
        w = w.strip().lstrip("@")
        if w:
            writers.append(f"@{w}" if ":" in w else f"@{w}:{HOMESERVER_DOMAIN}")

    print("Pokoje do obsluzenia:")
    for s in selected:
        print(f"  - \"{s['name']}\" (#{s['alias']}:{HOMESERVER_DOMAIN}) -- {'ze widgetem' if s['widget'] else 'bez widgetu'}")
    if readonly:
        print(f"Tryb: TYLKO DO ODCZYTU -- pisza admin i {len(writers)} wskazanych osob (MAIN_ROOM_WRITERS).")
    else:
        print("Tryb: zwykle pokoje -- pisza wszyscy.")
    print()

    print(f"Loguje sie do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia/logowania do Synapse: {e}")
        print("Sprawdz: czy konto ma admin=1 (README, Etap B), haslo, i dostep do matrix.local jak w Elemencie.")
        sys.exit(1)
    print("Zalogowano.\n")

    for spec in selected:
        setup_room(syn, spec, args, readonly, writers, widget_url)

    print("=== GOTOWE ===" if not args.dry_run else "=== KONIEC TRYBU PROBNEGO ===")
    if not args.dry_run:
        print("Sprawdz w Elemencie (najlepiej na DRUGIM koncie, np. --profile): czy oba pokoje sa na liscie,")
        print("czy w pokoju ze struktura widget zajmuje okno, a w pokoju ogloszen widgetu nie ma.")
        print("Jesli widget sie nie wyswietla -- porownaj zdarzenie widgetu z tym, co zapisuje Element")
        print("po /addwidget (patrz opis na gorze pliku).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBLAD: {e}")
        print("Jesli to 403/404 przy --room-id: konto administratora musi byc czlonkiem tego pokoju")
        print("z uprawnieniami moderatora (poziom 50+) -- albo pozwol skryptowi utworzyc nowy pokoj.")
        sys.exit(1)
