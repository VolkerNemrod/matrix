#!/usr/bin/env python3
"""
setup_spaces.py -- drzewo Matrix Spaces odwzorowujace strukture firmy z LLDAP (wariant B, plaski).

STRUKTURA (decyzja 2026-10-15):
  Firma                       <- WSZYSCY (kazdy widzi wszystkich ~300 osob; z listy czlonkow mozna otworzyc DM)
   |- Ksiegowosc               <- grupa LLDAP "Księgowość"
   |- Wydzial EFS              <- grupa "Wydział EFS"
   |- Dyrekcja                 <- grupa "Dyrekcja"
   |- IT                       <- grupa "IT"
   |- Sprzedaz                 <- grupa "Sprzedaż"
   |- Bydgoszcz Poradnictwo    <- grupa "Bydgoszcz Poradnictwo"
   '- Wloclawek Poradnictwo    <- grupa "Włocławek Poradnictwo"
Kazde konto ma dokladnie jedna grupe-dzial, wiec kazdy subspace = jedna grupa (zadnych przeciec).
Nazwa glownego space'u ('Firma') jest ustawialna: SPACES_ROOT_NAME w .env (domyslnie "Firma").
'id' wezlow (np. "firma", "ksiegowosc") sa STALE -- z nich powstaja aliasy pokoi (#space-<id>:domena),
po aliasie skrypt rozpoznaje space przy kolejnych uruchomieniach. Nazwe wyswietlana mozna zmieniac
swobodnie; zmiana 'id' utworzy NOWY space (tak samo jak w AIM).

DRZEWO JEST REKURENCYJNE (SPACE_TREE nizej): wezel = id, name, topic, groups, children.
  groups = lista nazw grup LLDAP albo None (= wszyscy). Czlonkowie space'u = czlonkowie jego grup
  + czlonkowie wszystkich jego subspace'ow (semantyka jak w AIM). Partnerow (20 firm) mozna pozniej dodac
  jako kolejne poddrzewa w "children" -- na razie NIE sa podlaczeni (decyzja 2026-10-14).

TYLKO DO ODCZYTU: nikt poza adminem i osobami z SPACES_WRITERS (domyslnie MAIN_ROOM_WRITERS z .env)
nie moze pisac w space'ach ani zmieniac ich ustawien/dzieci. Space w Elemencie to kontener (nie ma
okna pisania); pokoi dyskusyjnych w space'ach NIE tworzymy. DM-y 1:1 sa osobnymi pokojami -- dzialaja.

CO ROBI (kazdy krok idempotentny -- mozna puszczac wielokrotnie):
  1. Loguje sie do LLDAP i do Synapse (jak seed_test_employees.py i setup_main_room.py).
  2. Sprawdza, czy wszystkie grupy z drzewa istnieja w LLDAP (jesli nie -- konczy bledem, nic nie zmieniajac).
  3. Dla kazdego wezla: znajduje space po aliasie albo tworzy (typ m.space), ustawia nazwe, temat
     i uprawnienia (tylko do odczytu).
  4. Laczy hierarchie: m.space.child w rodzicu i m.space.parent w dziecku. Dzieci, ktorych nie ma
     w konfiguracji, sa tylko ZGLASZANE (skrypt ich nie usuwa).
  5. Dolacza do kazdego space'u wlasciwych czlonkow (Admin API, bez zaproszen). Pomija osoby, ktore
     same wyszly lub zostaly zbanowane (chyba ze --rejoin); osoby WYRZUCONE przez skrypt (--prune)
     wracaja automatycznie, gdy znow trafia do grupy.
  6. Z --prune: wyrzuca ze space'u osoby, ktore juz nie naleza do zadnej z jego grup (np. po przeniesieniu
     do innego dzialu). Bez --prune tylko je wypisuje.

WIDOCZNOSC DZIALOW (join_rule 'knock'):
  Space glowny ('Firma') jest invite-only (wszyscy sa do niego dolaczeni skryptem). Subspace'y (dzialy)
  dostaja join_rule 'knock' (SPACES_SUBSPACE_JOIN_RULE w .env: knock | invite, domyslnie INVITE):
  czlonkowie 'Firma' WIDZA dzialy w drzewie space'u, ale nie moga do nich dolaczyc sami -- moga tylko
  poprosic o dolaczenie (admin akceptuje albo ignoruje). Listy czlonkow dzialow widza tylko ich czlonkowie.
  Wartosc 'invite' = poprzednie zachowanie (dzialy niewidoczne dla osob spoza dzialu).
  WYNIK TESTU 2026-10-14: 'knock' pokazuje dzialy (nazwa, liczba czlonkow), ale NIE pokazuje ludzi z dzialu
  -- decyzja uzytkownika: wracamy do 'invite' (domyslne), szukanie ludzi po nazwie dzialu w space'ie 'Firma'.

NIESPRAWDZONE W PRAKTYCE (do przetestowania w Elemencie):
  - czy zwykly uzytkownik widzi dzialy na stronie glownej 'Firma' i moze o nie tylko poprosic (knock),
  - czy zwykly uzytkownik nie moze pisac w space ani podpiac wlasnego pokoju (m.space.child na poziomie 100),
  - czy klik osoby na liscie czlonkow space'u 'Firma' otwiera DM,
  - czy Element pokazuje space'y bez dodatkowych zaproszen po force-join.

WYMAGANIA WSTEPNE: konta w Synapse istnieja (provision_synapse_users.py), LLDAP dziala, w .env sa
TS_IP i LLDAP_ADMIN_PASSWORD, dziala konto admina Synapse (jak w setup_main_room.py). Importuje klasy
z setup_main_room.py i seed_test_employees.py -- oba pliki musza lezec w tym samym katalogu.

Wymaga: pip install requests
Uzycie:
  python setup_spaces.py --dry-run          # tylko pokaz, co by zrobil
  python setup_spaces.py                    # wykonaj
  python setup_spaces.py --prune            # + wyrzuc z space'ow osoby spoza ich grup
  python setup_spaces.py --skip-join        # tylko struktura, bez dolaczania ludzi
  python setup_spaces.py --rejoin           # dolacz tez tych, co sami wyszli
"""

import argparse
import copy
import sys

import requests

from setup_main_room import (
    ADMIN_LOGIN,
    ADMIN_ONLY_EVENTS,
    ADMIN_PASSWORD,
    HOMESERVER_DOMAIN,
    MATRIX_BASE_URL,
    ROOT_CA_PATH,
    WRITER_LEVEL,
    Synapse,
    cfg,
    ensure_name_topic,
    q,
)
from seed_test_employees import ADMIN_USERNAME as LLDAP_ADMIN_USER
from seed_test_employees import LldapAdmin, resolve_lldap_url

# ============================================================
# KONFIGURACJA
# ============================================================

ALIAS_PREFIX = "space-"     # alias space'u: #space-<id>:<domena>
ROOT_NAME = cfg("SPACES_ROOT_NAME", "Firma")

# join_rule subspace'ow: "knock" = widoczne dla czlonkow rodzica, wejscie tylko po akceptacji admina;
# "invite" = niewidoczne dla osob spoza dzialu. Glowny space (root) jest zawsze invite-only.
SUBSPACE_JOIN_RULE = (cfg("SPACES_SUBSPACE_JOIN_RULE", "invite") or "invite").strip().lower()
if SUBSPACE_JOIN_RULE not in ("knock", "invite"):
    print(f"BLAD: SPACES_SUBSPACE_JOIN_RULE musi byc 'knock' albo 'invite' (jest: '{SUBSPACE_JOIN_RULE}').")
    sys.exit(1)

SPACE_TREE = {
    "id": "firma",
    "name": ROOT_NAME,
    "topic": "Wszyscy pracownicy firmy (tylko do odczytu)",
    "groups": None,   # None = wszystkie konta
    "children": [
        {"id": "ksiegowosc", "name": "Księgowość", "groups": ["Księgowość"]},
        {"id": "wydzial-efs", "name": "Wydział EFS", "groups": ["Wydział EFS"]},
        {"id": "dyrekcja", "name": "Dyrekcja", "groups": ["Dyrekcja"]},
        {"id": "it", "name": "IT", "groups": ["IT"]},
        {"id": "sprzedaz", "name": "Sprzedaż", "groups": ["Sprzedaż"]},
        {"id": "bydgoszcz-poradnictwo", "name": "Bydgoszcz Poradnictwo", "groups": ["Bydgoszcz Poradnictwo"]},
        {"id": "wloclawek-poradnictwo", "name": "Włocławek Poradnictwo", "groups": ["Włocławek Poradnictwo"]},
    ],
}

# Zdarzenia zmieniane wylacznie przez administratora (poziom 100).
SPACE_ADMIN_ONLY_EVENTS = list(ADMIN_ONLY_EVENTS) + ["m.space.child", "m.space.parent"]

# ============================================================


def walk(node, parent=None):
    """Przechodzi drzewo wszerz-w-glab: (wezel, rodzic)."""
    yield node, parent
    for child in node.get("children", []):
        yield from walk(child, node)


def tree_groups(node) -> set:
    """Wszystkie nazwy grup uzyte w poddrzewie."""
    names = set(node.get("groups") or [])
    for c in node.get("children", []):
        names |= tree_groups(c)
    return names


def mxid(uid: str) -> str:
    return f"@{uid.lower()}:{HOMESERVER_DOMAIN}"


def desired_members(node, group_users: dict, all_users: set) -> set:
    """Czlonkowie space'u = jego grupy + czlonkowie wszystkich subspace'ow (groups=None -> wszyscy)."""
    if node.get("groups") is None:
        return set(all_users)
    members = set()
    for g in node["groups"]:
        members |= group_users.get(g, set())
    for c in node.get("children", []):
        members |= desired_members(c, group_users, all_users)
    return members & all_users


def node_topic(node) -> str:
    return node.get("topic") or f"Dział: {node['name']} (tylko do odczytu)"


def full_alias(node) -> str:
    return f"#{ALIAS_PREFIX}{node['id']}:{HOMESERVER_DOMAIN}"


# --- Synapse: pomocnicze ---


def create_space(syn: Synapse, node) -> str:
    body = {
        "room_alias_name": f"{ALIAS_PREFIX}{node['id']}",
        "name": node["name"],
        "topic": node_topic(node),
        "preset": "private_chat",
        "visibility": "private",
        "creation_content": {"type": "m.space"},
        "power_level_content_override": {
            "events": {ev: 100 for ev in SPACE_ADMIN_ONLY_EVENTS},
            "events_default": WRITER_LEVEL,
            "state_default": 100,
        },
    }
    return syn.call("POST", "/_matrix/client/v3/createRoom", json=body).json()["room_id"]


def ensure_space_power_levels(syn: Synapse, room_id: str, writers: list, dry_run: bool):
    """Tylko do odczytu: pisze admin i 'writers' (poziom WRITER_LEVEL); stan zmienia tylko admin."""
    old = syn.get_state(room_id, "m.room.power_levels") or {}
    new = copy.deepcopy(old)
    events = new.setdefault("events", {})
    users = new.setdefault("users", {})

    for ev in SPACE_ADMIN_ONLY_EVENTS:
        if events.get(ev, 0) < 100:
            events[ev] = 100
    new["events_default"] = WRITER_LEVEL
    new["state_default"] = 100
    new["kick"] = 100
    new["ban"] = 100
    new["invite"] = 100

    wanted = set(writers)
    for m in wanted:
        if users.get(m, 0) < WRITER_LEVEL:
            users[m] = WRITER_LEVEL
    for m, level in list(users.items()):
        if level == WRITER_LEVEL and m not in wanted:
            del users[m]

    if new == old:
        print("  Uprawnienia: juz poprawne (tylko do odczytu).")
        return
    print(f"  Uprawnienia: ustawiam tryb 'tylko do odczytu', piszacych z .env: {len(wanted)}.")
    if not dry_run:
        syn.put_state(room_id, "m.room.power_levels", new)


def ensure_join_rule(syn: Synapse, room_id: str, rule: str, dry_run: bool):
    """Ustawia m.room.join_rules (invite albo knock), jesli jest inaczej."""
    old = syn.get_state(room_id, "m.room.join_rules") or {}
    if old.get("join_rule") == rule:
        print(f"  Regula dolaczania: juz '{rule}'.")
        return
    print(f"  Regula dolaczania: '{old.get('join_rule')}' -> '{rule}'.")
    if not dry_run:
        syn.put_state(room_id, "m.room.join_rules", {"join_rule": rule})


def link_child(syn: Synapse, parent_id: str, child_id: str, order: int, dry_run: bool):
    via = [HOMESERVER_DOMAIN]
    child_content = {"via": via, "order": f"{order:02d}"}
    if syn.get_state(parent_id, "m.space.child", child_id) == child_content:
        print("  Hierarchia: m.space.child w rodzicu juz poprawne.")
    else:
        print("  Hierarchia: dodaje/aktualizuje m.space.child w rodzicu.")
        if not dry_run:
            syn.put_state(parent_id, "m.space.child", child_content, child_id)

    parent_content = {"via": via, "canonical": True}
    if syn.get_state(child_id, "m.space.parent", parent_id) == parent_content:
        print("  Hierarchia: m.space.parent w dziecku juz poprawne.")
    else:
        print("  Hierarchia: dodaje/aktualizuje m.space.parent w dziecku.")
        if not dry_run:
            syn.put_state(child_id, "m.space.parent", parent_content, parent_id)


def report_stale_children(syn: Synapse, room_id: str, expected_child_ids: set):
    """Dzieci space'u, ktorych nie ma w konfiguracji -- tylko zglasza, nie usuwa."""
    events = syn.call("GET", f"/_matrix/client/v3/rooms/{q(room_id)}/state").json()
    stale = [
        e["state_key"] for e in events
        if e.get("type") == "m.space.child" and e.get("content") and e["state_key"] not in expected_child_ids
    ]
    if stale:
        print(f"  UWAGA: {len(stale)} dzieci spoza konfiguracji (nie usuwam): {', '.join(stale)}")


def memberships(syn: Synapse, room_id: str) -> dict:
    """mxid -> (membership, sender). sender != mxid przy 'leave' oznacza wyrzucenie przez kogos."""
    r = syn.call("GET", f"/_matrix/client/v3/rooms/{q(room_id)}/members")
    return {
        e["state_key"]: (e["content"].get("membership"), e.get("sender"))
        for e in r.json().get("chunk", [])
    }


def sync_members(syn: Synapse, room_id, wanted: set, protected: set, args):
    if room_id is None:
        print(f"  Czlonkowie: space jeszcze nie istnieje -- do dolaczenia byloby {len(wanted)} kont.")
        return
    current = memberships(syn, room_id)
    to_join, already, left, banned = [], 0, 0, 0
    for m in sorted(wanted):
        state, sender = current.get(m, (None, None))
        if state == "join":
            already += 1
        elif state == "ban":
            banned += 1
        elif state == "leave" and sender == m and not args.rejoin:
            left += 1   # wyszedl sam -- szanujemy
        else:
            to_join.append(m)   # brak / zaproszony / wyrzucony przez admina

    extras = sorted(
        m for m, (state, _) in current.items()
        if state == "join" and m not in wanted and m not in protected
    )
    print(f"  Czlonkowie: powinno byc {len(wanted)} | juz sa: {already} | do dolaczenia: {len(to_join)} "
          f"| wyszli sami (pomijam): {left} | zbanowani (pomijam): {banned} | nadmiarowi: {len(extras)}")

    if not args.skip_join and to_join and not args.dry_run:
        failed = 0
        for i, m in enumerate(to_join, 1):
            try:
                syn.force_join(room_id, m)
            except RuntimeError as e:
                failed += 1
                print(f"    [{i}/{len(to_join)}] {m} -> BLAD: {e}")
        print(f"  Dolaczono: {len(to_join) - failed}, bledy: {failed}")

    if extras:
        if args.prune and not args.dry_run:
            for m in extras:
                try:
                    syn.call("POST", f"/_matrix/client/v3/rooms/{q(room_id)}/kick",
                             json={"user_id": m, "reason": "Nie nalezy juz do grupy tego dzialu (LLDAP)"})
                    print(f"    wyrzucony: {m}")
                except RuntimeError as e:
                    print(f"    BLAD wyrzucania {m}: {e}")
        else:
            shown = ", ".join(extras[:10]) + (" ..." if len(extras) > 10 else "")
            hint = "(dry-run)" if args.dry_run and args.prune else "(uzyj --prune, zeby wyrzucic)"
            print(f"  Nadmiarowi {hint}: {shown}")


# --- LLDAP ---


def fetch_group_users(lldap: LldapAdmin) -> dict:
    """nazwa grupy -> zbior mxid-ow jej czlonkow."""
    data = lldap.graphql("query { groups { displayName users { id } } }")
    return {g["displayName"]: {mxid(u["id"]) for u in g["users"]} for g in data["groups"]}


def main():
    parser = argparse.ArgumentParser(description="Drzewo Matrix Spaces wg grup LLDAP (tylko do odczytu).")
    parser.add_argument("--dry-run", action="store_true", help="tylko pokaz, co by zrobil (bez zapisu)")
    parser.add_argument("--prune", action="store_true", help="wyrzucaj ze space'ow osoby spoza ich grup")
    parser.add_argument("--skip-join", action="store_true", help="nie dolaczaj uzytkownikow")
    parser.add_argument("--rejoin", action="store_true", help="dolacz tez osoby, ktore same wyszly")
    args = parser.parse_args()

    if not ROOT_CA_PATH.exists():
        print(f"BLAD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)
    if args.dry_run:
        print("*** TRYB PROBNY (--dry-run): nic nie zostanie zapisane ***\n")

    nodes = list(walk(SPACE_TREE))
    ids = [n["id"] for n, _ in nodes]
    if len(ids) != len(set(ids)):
        print("BLAD: 'id' wezlow w SPACE_TREE musza byc unikalne.")
        sys.exit(1)

    writers = []
    for w in (cfg("SPACES_WRITERS") or cfg("MAIN_ROOM_WRITERS")).split(","):
        w = w.strip().lstrip("@")
        if w:
            writers.append(f"@{w}" if ":" in w else f"@{w}:{HOMESERVER_DOMAIN}")

    print(f"Drzewo space'ow ({len(nodes)} wezlow), glowny: \"{SPACE_TREE['name']}\":")
    for n, parent in nodes:
        grp = "wszyscy" if n.get("groups") is None else ", ".join(n["groups"])
        print(f"  {'  ' if parent else ''}- \"{n['name']}\" ({full_alias(n)}) -- {grp}")
    print(f"Tryb: TYLKO DO ODCZYTU -- pisza admin i {len(writers)} wskazanych osob.\n")

    # --- LLDAP ---
    lldap_password = cfg("LLDAP_ADMIN_PASSWORD")
    if not lldap_password or lldap_password.startswith("CHANGE_ME"):
        print("BLAD: nie znaleziono LLDAP_ADMIN_PASSWORD (.env albo zmienna srodowiskowa).")
        sys.exit(1)
    lldap_url = resolve_lldap_url()
    print(f"Loguje sie do LLDAP ({lldap_url})...")
    try:
        lldap = LldapAdmin(lldap_url, LLDAP_ADMIN_USER, lldap_password, dry_run=True)  # tylko odczyt
        group_users = fetch_group_users(lldap)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia z LLDAP: {e}")
        sys.exit(1)

    missing = sorted(tree_groups(SPACE_TREE) - set(group_users))
    if missing:
        print(f"BLAD: w LLDAP brakuje grup uzytych w drzewie: {', '.join(missing)}")
        print("Utworz je (seed_test_employees.py) albo popraw SPACE_TREE. Nic nie zmieniono.")
        sys.exit(1)
    print("LLDAP OK -- wszystkie grupy z drzewa istnieja:")
    for g in sorted(tree_groups(SPACE_TREE)):
        print(f"  {g}: {len(group_users[g])} kont")
    print()

    # --- Synapse ---
    print(f"Loguje sie do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
        all_users = set(syn.list_local_users())
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia/logowania do Synapse: {e}")
        sys.exit(1)
    print(f"Zalogowano. Konta lokalne w Synapse: {len(all_users)}\n")

    in_any_group = set()
    for g in tree_groups(SPACE_TREE):
        in_any_group |= group_users[g]
    no_synapse = in_any_group - all_users
    no_group = all_users - in_any_group - {syn.admin_mxid}
    if no_synapse:
        print(f"UWAGA: {len(no_synapse)} kont z LLDAP nie ma jeszcze konta w Synapse "
              f"(provision_synapse_users.py / pierwsze logowanie) -- zostana pominiete.")
    if no_group:
        print(f"UWAGA: {len(no_group)} kont Synapse nie nalezy do zadnej grupy-dzialu "
              f"(trafia tylko do \"{SPACE_TREE['name']}\").")
    print()

    protected = {syn.admin_mxid} | set(writers)
    room_ids = {}

    # --- 1. space'y: istnienie, nazwa/temat, uprawnienia ---
    print("######## [1/3] Space'y: utworzenie, nazwa, uprawnienia ########")
    for node, parent in nodes:
        alias = full_alias(node)
        print(f"=== \"{node['name']}\" ({alias}) ===")
        room_id = syn.find_room_by_alias(alias)
        if room_id:
            print(f"  Space: istnieje ({room_id})")
        elif args.dry_run:
            print("  Space: nie istnieje -- zostalby utworzony.")
        else:
            room_id = create_space(syn, node)
            print(f"  Space: utworzony ({room_id})")
        room_ids[node["id"]] = room_id
        if room_id:
            ensure_name_topic(syn, room_id, {"name": node["name"], "topic": node_topic(node)}, args.dry_run)
            ensure_space_power_levels(syn, room_id, writers, args.dry_run)
            ensure_join_rule(syn, room_id, node.get("join_rule") or (SUBSPACE_JOIN_RULE if parent else "invite"),
                             args.dry_run)
        print()

    # --- 2. hierarchia ---
    print("######## [2/3] Hierarchia (m.space.child / m.space.parent) ########")
    for node, _ in nodes:
        children = node.get("children", [])
        if not children:
            continue
        parent_id = room_ids[node["id"]]
        print(f"=== \"{node['name']}\" -> {len(children)} subspace'ow ===")
        if not parent_id:
            print("  (rodzic jeszcze nie istnieje -- w trybie probnym pomijam)\n")
            continue
        expected = set()
        for i, child in enumerate(children, 1):
            child_id = room_ids[child["id"]]
            print(f" - \"{child['name']}\"")
            if not child_id:
                print("  (subspace jeszcze nie istnieje -- w trybie probnym pomijam)")
                continue
            expected.add(child_id)
            link_child(syn, parent_id, child_id, i, args.dry_run)
        report_stale_children(syn, parent_id, expected)
        print()

    # --- 3. czlonkowie ---
    print("######## [3/3] Czlonkowie ########")
    for node, _ in nodes:
        print(f"=== \"{node['name']}\" ===")
        wanted = desired_members(node, group_users, all_users)
        sync_members(syn, room_ids[node["id"]], wanted, protected, args)
        print()

    print("=== GOTOWE ===" if not args.dry_run else "=== KONIEC TRYBU PROBNEGO ===")
    if not args.dry_run:
        print("Test w Elemencie (najlepiej na koncie zwyklego pracownika, np. --profile):")
        print(f"  1. Czy w pasku bocznym jest space \"{SPACE_TREE['name']}\" z 7 subspace'ami?")
        print("  2. Czy klik osoby na liscie czlonkow space'u otwiera DM?")
        print("  3. Czy zwykly uzytkownik nie moze pisac w space ani dodac do niego swojego pokoju?")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBLAD: {e}")
        sys.exit(1)
