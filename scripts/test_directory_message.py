#!/usr/bin/env python3
"""
test_directory_message.py -- EKSPERYMENT ZAKONCZONY (historia): sprawdzal ksiazke adresowa jako WIADOMOSC
z linkami matrix.to. Wyniki (README, 2.1): <details> dziala w Element Desktop, nie na telefonie; wyszukiwanie
w tresci pokoju nie dziala; pigulka otwiera profil osoby (czy stamtad wygodnie zaczac DM -- niesprawdzone).
PRODUKCYJNIE sluzy do tego setup_directory.py (Etap 2.1); ten plik zostaje do prob ukladu i pomiaru rozmiaru
(--measure). Wymaga SYNAPSE_ADMIN_PASSWORD w .env na PC i konta administratora (README, Etap 0).

CO SPRAWDZAL (checklista, na DRUGIM koncie zwyklego pracownika):
  1. Czy linki do osob renderuja sie jako "pigulki" z nazwa osoby (a nie surowy URL).
  2. Co robi klik w pigulke: karta osoby z przyciskiem "Wyslij wiadomosc" czy od razu DM,
     i czy w ogole nie otwiera przegladarki (matrix.to ma byc przechwycony lokalnie).
  3. Czy <details>/<summary> sie rozwija (wiadomosc A) -- Element ma biala liste znacznikow HTML,
     tego nie da sie zgadnac z dokumentacji, trzeba zobaczyc.
  4. To samo na telefonie (Element Android / Element X) -- renderowanie moze sie roznic.
  5. Wyszukiwanie w pokoju (lupa / Ctrl+F): wpisz imie lub nazwisko osoby z listy.
  6. Rozmiar: --measure pokazuje, ile bajtow miałaby wiadomosc dla WSZYSTKICH kont
     (limit zdarzenia Matrix ~65 536 B).

WIADOMOSCI:
  A -- ze zwijanymi sekcjami (<details>) per dzial
  B -- bez zwijania: naglowek <h4> per dzial i lista osob (wersja zapasowa, gdy A nie dziala)

Pokoj testowy: #test-ksiazka-adresowa:matrix.local, BEZ szyfrowania (wyszukiwanie po stronie
serwera dziala tylko w pokojach nieszyfrowanych -- pokoj tworzony przez API taki jest).
Do pokoju dolaczane sa tylko osoby uzyte w tescie (+ opcjonalnie --join login1,login2),
zeby mozna bylo zalogowac sie na jedno z tych kont i obejrzec wiadomosc oczami zwyklego usera.

Uzycie (PC, cd scripts, Tailscale/hosts jak przy setup_directory.py):
  .\\venv\\Scripts\\python.exe test_directory_message.py --dry-run
  .\\venv\\Scripts\\python.exe test_directory_message.py
  .\\venv\\Scripts\\python.exe test_directory_message.py --limit 20 --join j.kowalski
  .\\venv\\Scripts\\python.exe test_directory_message.py --measure
Kazde uruchomienie wysyla NOWE wiadomosci A i B (pokoj jest ponownie uzywany). Stare wiadomosci
mozna zignorowac albo usunac pokoj przez panel Synapse Admin (purge).

Format nazwy wyswietlanej (provision_synapse_users.py): "Imie Nazwisko – Dzial"
(opcjonalnie "Imie Nazwisko – Dzial, Lokalizacja"). Z niej ten skrypt (i produkcyjnie
setup_directory.py) grupuje osoby po dziale.
UWAGA: wyniki testow i decyzje -- patrz README, 2.2 (setup_directory.py).
"""

import argparse
import html
import sys
import time

import requests

# Biblioteka: setup_main_room.py ma na poziomie modulu tylko definicje (main() jest za guardem).
from setup_main_room import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    HOMESERVER_DOMAIN,
    MATRIX_BASE_URL,
    ROOT_CA_PATH,
    Synapse,
    q,
)

ROOM_ALIAS = "test-ksiazka-adresowa"
ROOM_NAME = "TEST: Książka adresowa"
ROOM_TOPIC = "Eksperyment: struktura firmy jako wiadomość z linkami matrix.to (do usunięcia)"
EVENT_SIZE_LIMIT = 65536  # bajty; limit rozmiaru zdarzenia w Matrix


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def list_users_with_names(syn: Synapse):
    """[(mxid, displayname)] dla lokalnych, aktywnych kont."""
    users, token = [], None
    while True:
        params = {"limit": 100, "deactivated": "false", "guests": "false"}
        if token:
            params["from"] = token
        data = syn.call("GET", "/_synapse/admin/v2/users", params=params).json()
        for u in data.get("users", []):
            if u["name"].endswith(f":{HOMESERVER_DOMAIN}"):
                users.append((u["name"], u.get("displayname") or u["name"]))
        token = data.get("next_token")
        if not token:
            break
    return users


def split_displayname(displayname: str):
    """'Imie Nazwisko – Dzial[, Lokalizacja]' -> (imie_nazwisko, dzial, lokalizacja)."""
    for sep in (" – ", " - "):
        if sep in displayname:
            name, rest = displayname.split(sep, 1)
            dept, _, loc = rest.partition(",")
            return name.strip(), dept.strip() or "Bez działu", loc.strip()
    return displayname.strip(), "Bez działu", ""


def build_tree(people):
    """{dzial: {lokalizacja: [(mxid, imie_nazwisko), ...]}}"""
    tree = {}
    for mxid, dn in people:
        name, dept, loc = split_displayname(dn)
        tree.setdefault(dept, {}).setdefault(loc, []).append((mxid, name))
    return tree


def pill(mxid: str, name: str) -> str:
    return f'<a href="https://matrix.to/#/{esc(mxid)}">{esc(name)}</a>'


def build_message(tree: dict, collapsible: bool, title: str):
    """Zwraca tresc m.room.message: body (zwykly tekst -- po nim szuka serwer!) + formatted_body."""
    parts = [f"<h3>{esc(title)}</h3>"]
    lines = [title]
    for dept in sorted(tree, key=str.casefold):
        locs = tree[dept]
        count = sum(len(v) for v in locs.values())
        lines.append("")
        lines.append(f"{dept} ({count})")
        if collapsible:
            parts.append(f"<details><summary><b>{esc(dept)}</b> ({count})</summary>")
        else:
            parts.append(f"<h4>{esc(dept)} ({count})</h4>")
        for loc in sorted(locs, key=str.casefold):
            people = sorted(locs[loc], key=lambda p: p[1].casefold())
            if loc:
                parts.append(f"<p><i>{esc(loc)}</i></p>")
                lines.append(f"  {loc}")
            parts.append("<ul>" + "".join(f"<li>{pill(m, n)}</li>" for m, n in people) + "</ul>")
            for m, n in people:
                lines.append(f"  - {n} ({m})")
        if collapsible:
            parts.append("</details>")
    return {
        "msgtype": "m.text",
        "body": "\n".join(lines),
        "format": "org.matrix.custom.html",
        "formatted_body": "".join(parts),
    }


def event_size(content: dict) -> int:
    import json
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8"))


def pick_sample(people, limit: int):
    """Probka rozrzucona po dzialach (round-robin), zeby test mial kilka sekcji."""
    by_dept = {}
    for mxid, dn in people:
        by_dept.setdefault(split_displayname(dn)[1], []).append((mxid, dn))
    chosen, i = [], 0
    depts = sorted(by_dept, key=str.casefold)
    while len(chosen) < limit and any(i < len(by_dept[d]) for d in depts):
        for d in depts:
            if i < len(by_dept[d]) and len(chosen) < limit:
                chosen.append(by_dept[d][i])
        i += 1
    return chosen


def ensure_room(syn: Synapse, dry_run: bool):
    alias = f"#{ROOM_ALIAS}:{HOMESERVER_DOMAIN}"
    room_id = syn.find_room_by_alias(alias)
    if room_id:
        print(f"Pokój testowy istnieje: {alias} -> {room_id}")
        return room_id
    if dry_run:
        print(f"Pokój testowy {alias} nie istnieje -- zostałby utworzony.")
        return None
    r = syn.call("POST", "/_matrix/client/v3/createRoom", json={
        "room_alias_name": ROOM_ALIAS,
        "name": ROOM_NAME,
        "topic": ROOM_TOPIC,
        "preset": "private_chat",   # bez szyfrowania (szyfruje dopiero klient)
        "visibility": "private",
    })
    room_id = r.json()["room_id"]
    print(f"Pokój testowy utworzony: {alias} -> {room_id}")
    return room_id


def send_message(syn: Synapse, room_id: str, content: dict, label: str):
    txn = f"testdir-{label}-{int(time.time() * 1000)}"
    r = syn.call("PUT", f"/_matrix/client/v3/rooms/{q(room_id)}/send/m.room.message/{txn}", json=content)
    print(f"  Wiadomość {label}: wysłana ({r.json().get('event_id')})")


def main():
    ap = argparse.ArgumentParser(description="TEST: książka adresowa jako wiadomość z linkami matrix.to")
    ap.add_argument("--dry-run", action="store_true", help="nic nie zapisuj; pokaż rozmiary i skład próbki")
    ap.add_argument("--limit", type=int, default=12, help="ile osób w teście (domyślnie 12, rozrzucone po działach)")
    ap.add_argument("--join", default="", help="dodatkowe loginy do dołączenia do pokoju, po przecinku")
    ap.add_argument("--measure", action="store_true",
                    help="tylko policz rozmiar wiadomości dla WSZYSTKICH kont (nic nie wysyła)")
    args = ap.parse_args()

    if not ROOT_CA_PATH.exists():
        print(f"BŁĄD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)

    print(f"Loguję się do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BŁĄD połączenia/logowania: {e}")
        sys.exit(1)
    print("Zalogowano.\n")

    everyone = list_users_with_names(syn)
    print(f"Konta lokalne: {len(everyone)}")

    if args.measure:
        tree = build_tree(everyone)
        print(f"Działów w drzewie: {len(tree)}")
        total_a = event_size(build_message(tree, True, "Książka adresowa"))
        total_b = event_size(build_message(tree, False, "Książka adresowa"))
        print(f"\nJEDNA wiadomość ze WSZYSTKIMI osobami: A (details) = {total_a} B, B (nagłówki) = {total_b} B "
              f"(limit {EVENT_SIZE_LIMIT} B) -> {'MIEŚCI SIĘ' if max(total_a, total_b) < EVENT_SIZE_LIMIT else 'ZA DUŻA'}")
        print("\nRozmiar wiadomości per dział (A):")
        for dept in sorted(tree, key=str.casefold):
            one = event_size(build_message({dept: tree[dept]}, True, dept))
            print(f"  {dept}: {sum(len(v) for v in tree[dept].values())} os., {one} B")
        return

    sample = pick_sample(everyone, args.limit)
    tree = build_tree(sample)
    print(f"Próbka testowa: {len(sample)} osób w {len(tree)} działach:")
    for dept in sorted(tree, key=str.casefold):
        names = ", ".join(n for locs in tree[dept].values() for _, n in locs)
        print(f"  - {dept}: {names}")

    msg_a = build_message(tree, True, "TEST A: rozwijane działy")
    msg_b = build_message(tree, False, "TEST B: działy bez rozwijania")
    print(f"\nRozmiar: A = {event_size(msg_a)} B, B = {event_size(msg_b)} B (limit {EVENT_SIZE_LIMIT} B)")

    room_id = ensure_room(syn, args.dry_run)
    extra = [f"@{w.strip().lstrip('@')}:{HOMESERVER_DOMAIN}" for w in args.join.split(",") if w.strip()]
    to_join = [m for m, _ in sample] + [m for m in extra if m not in {m2 for m2, _ in sample}]

    if args.dry_run:
        print(f"\n(tryb próbny) Dołączyłbym do pokoju {len(to_join)} kont i wysłał wiadomości A i B.")
        return

    members = syn.room_memberships(room_id)
    todo = [m for m in to_join if members.get(m) != "join" and m != syn.admin_mxid]
    print(f"\nDołączam do pokoju {len(todo)} kont...")
    for m in todo:
        try:
            syn.force_join(room_id, m)
        except RuntimeError as e:
            print(f"  {m} -> BŁĄD: {e}")

    print("Wysyłam wiadomości:")
    send_message(syn, room_id, msg_a, "A")
    send_message(syn, room_id, msg_b, "B")

    print("\n=== GOTOWE ===")
    print(f"Otwórz w Elemencie pokój \"{ROOM_NAME}\" (#{ROOM_ALIAS}:{HOMESERVER_DOMAIN}), najlepiej na DRUGIM koncie")
    print("(np. jednym z dołączonych, Element z --profile). Checklista jest na górze pliku.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBŁĄD: {e}")
        sys.exit(1)
