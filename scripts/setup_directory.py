#!/usr/bin/env python3
"""
setup_directory.py -- ksiazka adresowa firmy jako WIADOMOSCI z linkami matrix.to w pokoju
"Ksiazka adresowa" (tylko do odczytu, podpiety pod space "Firma"). Zastepuje porzucony widget.

WYNIK: w pokoju jest jedna wiadomosc wstepna i po jednej wiadomosci na dzial. Dzial rozwija sie
kliknieciem (<details>, dziala w Element Desktop, NIE na telefonie), osoby sa "pigulkami" Elementa
(klik = profil osoby), a obok nazwiska stoja opcjonalne dane: stanowisko, telefon, pokoj, pietro.

SKAD DANE:
  - kto, jaki dzial, jaka lokalizacja: konta Synapse i ich nazwa wyswietlana
    "Imie Nazwisko – Dzial[, Lokalizacja]" (tak ja ustawia provision_synapse_users.py z LLDAP);
  - stanowisko / telefon / pokoj / pietro: plik CSV (domyslnie scripts/directory_extra.csv),
    edytowany w Excelu. Szablon z wszystkimi loginami: --write-extra-template (nie nadpisuje
    wpisanych wartosci, dopisuje tylko nowe osoby). W wersji produkcyjnej zrodlem moze byc AD
    (telephoneNumber, physicalDeliveryOfficeName, title) -- wtedy ten plik zastapi odczyt z AD.
  - --fake-extra: SZTUCZNE dane do ogladania ukladu (wiadomosc dostaje dopisek "dane demonstracyjne").

CO ROBI (kazdy krok idempotentny -- mozna puszczac wielokrotnie, np. po dodaniu pracownika):
  1. Loguje sie do Synapse jako admin, pobiera wszystkie aktywne konta lokalne.
  2. Buduje wiadomosci: wstep + po jednej na dzial (zbyt duzy dzial dzieli sie na czesci).
  3. Pokoj: znajduje po aliasie albo tworzy; nazwa, temat, uprawnienia "tylko do odczytu"
     (pisza admin i SPACES_WRITERS); podpina pod space "Firma" (m.space.child / m.space.parent).
  4. Dolacza do pokoju WSZYSTKICH z listy PRZED wyslaniem wiadomosci (inaczej pigulki mogly by
     pokazac sam identyfikator zamiast nazwy; wpisy "X dolaczyl" Element zwija w jedna linie).
  5. Wysyla NOWE wiadomosci, EDYTUJE te, ktorych tresc sie zmienila (dopisek "(edited)"),
     NIE rusza niezmienionych, USUWA wiadomosci dzialow, ktorych juz nie ma.
     Stan (id wiadomosci + skrot tresci) trzyma w pokoju, w zdarzeniu stanu local.matrix.directory
     -- dzieki temu dziala z kazdego komputera i konta, bez plikow lokalnych.
  6. Domyslnie NIE przypina wiadomosci (stare przypiecia zdejmuje); --pin przypina wiadomosc wstepna.

OGRANICZENIA:
  - Limit zdarzenia Matrix to ~64 KB, a EDYCJA zawiera tresc dwa razy -- dlatego wiadomosc ma
    maks. ~28 KB (MSG_LIMIT) i wiekszy dzial jest dzielony na czesci.
  - Nowy dzial pojawi sie na DOLE osi czasu (nie alfabetycznie). Kolejnosc naprawia --rebuild
    (usuwa stare wiadomosci i wysyla wszystko od nowa, w porzadku alfabetycznym).
  - Wyszukiwanie w pokoju nie dziala (stwierdzone w tescie); osoby szuka sie w "Rozpocznij rozmowe".
  - NIEPRZETESTOWANE na pelnych danych w Synapse: pierwszy raz uruchom z --dry-run, potem na
    pokoju probnym: --alias test-ksiazka-pelna --limit 20 (pokoj probny NIE jest podpinany pod Firme).

Uzycie (PC, katalog scripts, jak setup_spaces.py):
  python setup_directory.py --write-extra-template      # utworz/uzupelnij directory_extra.csv
  python setup_directory.py --dry-run                   # co by zrobil, rozmiary wiadomosci
  python setup_directory.py                             # wykonaj (pokoj "Ksiazka adresowa")
  python setup_directory.py --fake-extra --alias test-ksiazka-pelna --limit 20   # proba
  python setup_directory.py --rebuild                   # wyslij wszystko od nowa (kolejnosc)
Inne opcje: --extra-file SCIEZKA, --exclude login1,login2, --skip-join, --rejoin.
Ustawienia w .env (opcjonalne): DIRECTORY_ROOM_ALIAS, DIRECTORY_ROOM_NAME, DIRECTORY_ROOM_TOPIC,
DIRECTORY_EXCLUDE (loginy po przecinku), SPACES_WRITERS.

Wymaga: pip install requests. Importuje setup_main_room.py (musi lezec w tym samym katalogu).
"""

import argparse
import csv
import datetime
import hashlib
import html
import json
import sys
import time
from pathlib import Path

import requests

from setup_main_room import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    HOMESERVER_DOMAIN,
    MATRIX_BASE_URL,
    ROOT_CA_PATH,
    Synapse,
    cfg,
    ensure_name_topic,
    ensure_power_levels,
    q,
)

# ============================================================
# KONFIGURACJA
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EXTRA_FILE = SCRIPT_DIR / "directory_extra.csv"

DEFAULT_ALIAS = "ksiazka-adresowa"                      # alias pokoju: #ksiazka-adresowa:<domena>
STATE_TYPE = "local.matrix.directory"                   # zdarzenie stanu z id wiadomosci (stan skryptu)
SPACE_ALIAS = f"#space-firma:{HOMESERVER_DOMAIN}"       # glowny space (setup_spaces.py: ALIAS_PREFIX + id 'firma')
MSG_LIMIT = 28000                                       # bajty; edycja = ~2x tresc, a limit zdarzenia to ~64 KB
INTRO_KEY = "00 Wstęp"
NO_DEPT = "Bez działu"

# Dodatkowe pola z CSV: (nazwa kolumny, przedrostek przed wartoscia). Kolejnosc = kolejnosc w wiadomosci.
EXTRA_FIELDS = [("stanowisko", ""), ("telefon", "tel. "), ("pokoj", "pok. "), ("pietro", "piętro ")]
TEMPLATE_COLUMNS = ["login", "imie_nazwisko", "dzial", "stanowisko", "telefon", "pokoj", "pietro"]

# ============================================================
# POMOCNICZE
# ============================================================

_PL_ORDER = "aąbcćdeęfghijklłmnńoóprsśtuwyzźż"
_DIACRITICS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def pl_key(s: str) -> list:
    """Klucz sortowania z polskim alfabetem (ą po a, ł po l, ś po s...)."""
    return [(_PL_ORDER.find(c) if c in _PL_ORDER else 100 + ord(c)) for c in s.casefold()]


def norm_header(h: str) -> str:
    return h.strip().lower().translate(_DIACRITICS).replace(" ", "_")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def event_size(content: dict) -> int:
    return len(json.dumps(content, ensure_ascii=False).encode("utf-8"))


def split_displayname(displayname: str):
    """'Imie Nazwisko – Dzial[, Lokalizacja]' -> (imie_nazwisko, dzial, lokalizacja)."""
    for sep in (" – ", " - "):
        if sep in displayname:
            name, rest = displayname.split(sep, 1)
            dept, _, loc = rest.partition(",")
            return name.strip(), dept.strip() or NO_DEPT, loc.strip()
    return displayname.strip(), NO_DEPT, ""


def list_people(syn: Synapse, excluded: set) -> list:
    """Wszystkie aktywne konta lokalne: [{mxid, login, name, dept, loc}]."""
    people, token = [], None
    while True:
        params = {"limit": 100, "deactivated": "false", "guests": "false"}
        if token:
            params["from"] = token
        data = syn.call("GET", "/_synapse/admin/v2/users", params=params).json()
        for u in data.get("users", []):
            mxid = u["name"]
            if not mxid.endswith(f":{HOMESERVER_DOMAIN}"):
                continue
            login = mxid[1:].split(":")[0].lower()
            if login in excluded:
                continue
            name, dept, loc = split_displayname(u.get("displayname") or login)
            people.append({"mxid": mxid, "login": login, "name": name, "dept": dept, "loc": loc})
        token = data.get("next_token")
        if not token:
            break
    return people


def pick_sample(people: list, limit: int) -> list:
    """Probka rozrzucona po dzialach (round-robin) -- do prob z --limit."""
    by_dept = {}
    for p in people:
        by_dept.setdefault(p["dept"], []).append(p)
    depts = sorted(by_dept, key=pl_key)
    chosen, i = [], 0
    while len(chosen) < limit and any(i < len(by_dept[d]) for d in depts):
        for d in depts:
            if i < len(by_dept[d]) and len(chosen) < limit:
                chosen.append(by_dept[d][i])
        i += 1
    return chosen


# ============================================================
# DANE DODATKOWE (CSV)
# ============================================================


def read_csv_rows(path: Path) -> list:
    """Wiersze CSV jako slowniki ze znormalizowanymi nazwami kolumn (separator ; lub , wykrywany)."""
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        return []
    delim = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    rows = []
    for r in csv.DictReader(lines, delimiter=delim):
        rows.append({norm_header(k): (v or "").strip() for k, v in r.items() if k})
    return rows


def load_extra(path: Path) -> dict:
    """login -> {stanowisko, telefon, pokoj, pietro} (tylko niepuste, tylko znane kolumny)."""
    extras = {}
    for row in read_csv_rows(path):
        login = row.get("login", "").lower().lstrip("@").split(":")[0]
        if not login:
            continue
        vals = {k: row[k] for k, _ in EXTRA_FIELDS if row.get(k)}
        if vals:
            extras[login] = vals
    return extras


def demo_extra(login: str) -> dict:
    """SZTUCZNE dane (stale dla danego loginu) -- tylko do ogladania ukladu."""
    h = int(hashlib.md5(login.encode()).hexdigest(), 16)
    floor = h % 4 + 1
    return {"telefon": str(100 + h % 900), "pokoj": f"{floor}.{(h // 7) % 30 + 1:02d}", "pietro": str(floor)}


def write_template(path: Path, people: list, dry_run: bool):
    """Tworzy/uzupelnia CSV: wszystkie loginy z Synapse; wpisane wartosci zostaja, nowe osoby dochodza."""
    old = {}
    if path.exists():
        for row in read_csv_rows(path):
            if row.get("login"):
                old[row["login"].lower()] = row
    current = {p["login"] for p in people}
    rows = []
    for p in sorted(people, key=lambda p: (pl_key(p["dept"]), pl_key(p["name"]))):
        prev = old.get(p["login"], {})
        rows.append([p["login"], p["name"], p["dept"]] + [prev.get(k, "") for k, _ in EXTRA_FIELDS])
    gone = sorted(set(old) - current)
    for login in gone:   # nie kasujemy cudzej pracy -- osoby spoza Synapse zostaja na koncu pliku
        prev = old[login]
        rows.append([login, prev.get("imie_nazwisko", ""), "(brak w Synapse)"] + [prev.get(k, "") for k, _ in EXTRA_FIELDS])
    new_count = len(current - set(old))
    print(f"Plik: {path}")
    print(f"  osób w Synapse: {len(current)} | już były w pliku: {len(current & set(old))} | nowe: {new_count} "
          f"| w pliku, ale bez konta (zostają na końcu): {len(gone)}")
    if dry_run:
        print("  (tryb próbny: nic nie zapisano)")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(TEMPLATE_COLUMNS)
        w.writerows(rows)
    print("  Zapisano (separator ';', kodowanie UTF-8 z BOM -- otwiera się w Excelu). Kolumny login/imie_nazwisko/dzial")
    print("  są tylko do orientacji (dane bierzemy z kont), wpisuj: stanowisko, telefon, pokoj, pietro.")


# ============================================================
# BUDOWA WIADOMOSCI
# ============================================================


def make_content(html_body: str, lines: list) -> dict:
    return {
        "msgtype": "m.text",
        "body": "\n".join(lines),   # zwykly tekst: po nim szuka serwer i pokazuja go klienty bez HTML
        "format": "org.matrix.custom.html",
        "formatted_body": html_body,
    }


def footer_notes(date: str, demo: bool) -> list:
    notes = []
    if date:
        notes.append(f"aktualizacja: {date}")
    if demo:
        notes.append("DANE DEMONSTRACYJNE (sztuczne telefony i pokoje)")
    return notes


def build_intro(n_people: int, date: str, demo: bool) -> dict:
    h = ("<h3>Książka adresowa firmy</h3><p>Kliknij nazwę działu, żeby rozwinąć listę osób, "
         f"a potem nazwisko, żeby otworzyć profil osoby. Osób na liście: {n_people}.</p>")
    lines = ["Książka adresowa firmy", f"Osób na liście: {n_people}."]
    notes = footer_notes(date, demo)
    if notes:
        h += f"<p><sub>{esc(' · '.join(notes))}</sub></p>"
        lines.append(" · ".join(notes))
    return make_content(h, lines)


def person_line(p: dict, extra: dict):
    parts = [f"{prefix}{extra[k]}" for k, prefix in EXTRA_FIELDS if extra.get(k)]
    suffix = " – " + " · ".join(parts) if parts else ""
    li = f'<li><a href="https://matrix.to/#/{esc(p["mxid"])}">{esc(p["name"])}</a>{esc(suffix)}</li>'
    return li, f'- {p["name"]} ({p["mxid"]}){suffix}'


def build_dept_content(title: str, items: list, extras: dict, date: str, demo: bool) -> dict:
    h = [f"<details><summary><b>{esc(title)}</b> ({len(items)})</summary>"]
    lines = [f"{title} ({len(items)})"]
    by_loc = {}
    for p in items:
        by_loc.setdefault(p["loc"], []).append(p)
    for loc in sorted(by_loc, key=lambda l: (l != "", pl_key(l))):
        if loc:
            h.append(f"<p><i>{esc(loc)}</i></p>")
            lines.append(f"  {loc}")
        lis = []
        for p in sorted(by_loc[loc], key=lambda p: pl_key(p["name"])):
            li, line = person_line(p, extras.get(p["login"], {}))
            lis.append(li)
            lines.append("  " + line)
        h.append("<ul>" + "".join(lis) + "</ul>")
    # bez stopki z datą/dopiskiem demo: te informacje są tylko we wiadomości wstępnej (mniej szumu)
    h.append("</details>")
    return make_content("".join(h), lines)


def split_dept(dept: str, items: list, extras: dict, demo: bool) -> list:
    """Dzieli dzial na czesci, az kazda miesci sie w MSG_LIMIT (podzial po lokalizacji/nazwisku)."""
    items = sorted(items, key=lambda p: (p["loc"] != "", pl_key(p["loc"]), pl_key(p["name"])))

    def rec(chunk):
        if len(chunk) == 1 or event_size(build_dept_content(dept, chunk, extras, "", demo)) <= MSG_LIMIT:
            return [chunk]
        mid = len(chunk) // 2
        return rec(chunk[:mid]) + rec(chunk[mid:])

    return rec(items)


def content_sha(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def plan_messages(people: list, extras: dict, date: str, demo: bool) -> list:
    """Lista wiadomosci w kolejnosci wyswietlania: {key, final, sha, n}. sha liczone BEZ daty,
    zeby sama zmiana daty nie wywolywala edycji niezmienionych wiadomosci."""
    out = [{
        "key": INTRO_KEY,
        "final": build_intro(len(people), date, demo),
        "sha": content_sha(build_intro(len(people), "", demo)),
        "n": 0,
    }]
    by_dept = {}
    for p in people:
        by_dept.setdefault(p["dept"], []).append(p)
    for dept in sorted(by_dept, key=pl_key):
        chunks = split_dept(dept, by_dept[dept], extras, demo)
        for i, chunk in enumerate(chunks, 1):
            if len(chunks) == 1:
                key, title = dept, dept
            else:
                key, title = f"{dept} [{i}/{len(chunks)}]", f"{dept} – część {i}/{len(chunks)}"
            out.append({
                "key": key,
                "final": build_dept_content(title, chunk, extras, date, demo),
                "sha": content_sha(build_dept_content(title, chunk, extras, "", demo)),
                "n": len(chunk),
            })
    return out


# ============================================================
# SYNAPSE: POKOJ, CZLONKOWIE, WIADOMOSCI
# ============================================================


def memberships(syn: Synapse, room_id: str) -> dict:
    """mxid -> (membership, sender). Przy 'leave' sender == mxid oznacza, ze osoba wyszla sama."""
    r = syn.call("GET", f"/_matrix/client/v3/rooms/{q(room_id)}/members")
    return {e["state_key"]: (e["content"].get("membership"), e.get("sender")) for e in r.json().get("chunk", [])}


def ensure_room(syn: Synapse, spec: dict, dry_run: bool):
    alias = f"#{spec['alias']}:{HOMESERVER_DOMAIN}"
    room_id = syn.find_room_by_alias(alias)
    if room_id:
        print(f"Pokój: istnieje ({alias} -> {room_id})")
    elif dry_run:
        print(f"Pokój: {alias} nie istnieje -- zostałby utworzony.")
    else:
        room_id = syn.create_room(spec)
        print(f"Pokój: utworzony ({alias} -> {room_id})")
    return room_id


def link_to_space(syn: Synapse, room_id: str, dry_run: bool):
    space_id = syn.find_room_by_alias(SPACE_ALIAS)
    if not space_id:
        print(f"  Space: nie znaleziono {SPACE_ALIAS} (uruchom najpierw setup_spaces.py) -- pomijam podpięcie.")
        return
    via = [HOMESERVER_DOMAIN]
    child = {"via": via, "order": "00"}      # "00" = przed działami (01..07)
    parent = {"via": via, "canonical": True}
    if syn.get_state(space_id, "m.space.child", room_id) == child:
        print("  Space: pokój już podpięty pod Firmę.")
    else:
        print("  Space: podpinam pokój pod Firmę (m.space.child).")
        if not dry_run:
            syn.put_state(space_id, "m.space.child", child, room_id)
    if syn.get_state(room_id, "m.space.parent", space_id) != parent:
        if not dry_run:
            syn.put_state(room_id, "m.space.parent", parent, space_id)


def join_all(syn: Synapse, room_id, mxids: list, rejoin: bool, dry_run: bool):
    current = memberships(syn, room_id) if room_id else {}
    to_join, already, left, banned = [], 0, 0, 0
    for m in mxids:
        state, sender = current.get(m, (None, None))
        if state == "join":
            already += 1
        elif state == "ban":
            banned += 1
        elif state == "leave" and sender == m and not rejoin:
            left += 1
        else:
            to_join.append(m)
    print(f"  Członkowie: na liście {len(mxids)} | już w pokoju: {already} | do dołączenia: {len(to_join)} "
          f"| wyszli sami (pomijam): {left} | zbanowani (pomijam): {banned}")
    if dry_run or not to_join:
        return
    failed = 0
    for i, m in enumerate(to_join, 1):
        try:
            syn.force_join(room_id, m)
        except RuntimeError as e:
            failed += 1
            print(f"    [{i}/{len(to_join)}] {m} -> BŁĄD: {e}")
    print(f"  Dołączono: {len(to_join) - failed}, błędy: {failed}")


def _txn(content: dict) -> str:
    return f"dir-{int(time.time() * 1000)}-{hashlib.md5(json.dumps(content, sort_keys=True).encode()).hexdigest()[:6]}"


def send_text(syn: Synapse, room_id: str, content: dict) -> str:
    r = syn.call("PUT", f"/_matrix/client/v3/rooms/{q(room_id)}/send/m.room.message/{_txn(content)}", json=content)
    return r.json()["event_id"]


def edit_text(syn: Synapse, room_id: str, event_id: str, content: dict) -> str:
    new_content = {k: content[k] for k in ("msgtype", "body", "format", "formatted_body")}
    edit = {
        "msgtype": "m.text",
        "body": "* " + content["body"],
        "format": content["format"],
        "formatted_body": "* " + content["formatted_body"],
        "m.new_content": new_content,
        "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
    }
    return send_text(syn, room_id, edit)


def redact(syn: Synapse, room_id: str, event_id: str):
    body = {"reason": "Aktualizacja książki adresowej"}
    syn.call("PUT", f"/_matrix/client/v3/rooms/{q(room_id)}/redact/{q(event_id)}/{_txn(body)}", json=body)


# ============================================================
# GLOWNA LOGIKA
# ============================================================


def main():
    ap = argparse.ArgumentParser(description="Książka adresowa firmy jako wiadomości z linkami matrix.to.")
    ap.add_argument("--dry-run", action="store_true", help="nic nie zapisuj; pokaż plan i rozmiary")
    ap.add_argument("--alias", help="inny alias pokoju (np. do prób); pokój próbny NIE jest podpinany pod Firmę")
    ap.add_argument("--limit", type=int, help="tylko N osób (próbka z różnych działów) -- do prób")
    ap.add_argument("--extra-file", help=f"CSV z danymi dodatkowymi (domyślnie {DEFAULT_EXTRA_FILE.name})")
    ap.add_argument("--fake-extra", action="store_true", help="SZTUCZNE telefony/pokoje (tylko do oglądania układu)")
    ap.add_argument("--write-extra-template", action="store_true",
                    help="utwórz/uzupełnij plik CSV loginami z Synapse i zakończ")
    ap.add_argument("--exclude", default="", help="loginy pominięte na liście, po przecinku (np. konta techniczne)")
    ap.add_argument("--skip-join", action="store_true", help="nie dołączaj osób do pokoju")
    ap.add_argument("--rejoin", action="store_true", help="dołącz też osoby, które same wyszły z pokoju")
    ap.add_argument("--rebuild", action="store_true", help="usuń stare wiadomości i wyślij wszystko od nowa (kolejność)")
    ap.add_argument("--pin", action="store_true", help="przypnij wiadomość wstępną (domyślnie bez przypięć)")
    args = ap.parse_args()

    if (args.limit or args.fake_extra) and not args.alias and not args.dry_run and not args.write_extra_template:
        print("BŁĄD: --limit i --fake-extra służą tylko do prób -- użyj ich z --alias (pokój próbny). Bez --alias "
              "zmieniłyby właściwy pokój (usunęłyby wiadomości działów spoza próbki albo opublikowały dane sztuczne).")
        sys.exit(1)

    if not ROOT_CA_PATH.exists():
        print(f"BŁĄD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)
    if args.dry_run:
        print("*** TRYB PRÓBNY (--dry-run): nic nie zostanie zapisane ***\n")

    alias = (args.alias or cfg("DIRECTORY_ROOM_ALIAS", DEFAULT_ALIAS)).lstrip("#").split(":")[0]
    spec = {
        "alias": alias,
        "name": cfg("DIRECTORY_ROOM_NAME", "Książka adresowa") + (" (PRÓBA)" if args.alias else ""),
        "topic": cfg("DIRECTORY_ROOM_TOPIC", "Kto jest kim w firmie: rozwiń dział i kliknij osobę (tylko do odczytu)"),
    }
    writers = []
    for w in (cfg("SPACES_WRITERS") or cfg("MAIN_ROOM_WRITERS")).split(","):
        w = w.strip().lstrip("@")
        if w:
            writers.append(f"@{w}" if ":" in w else f"@{w}:{HOMESERVER_DOMAIN}")
    excluded = {x.strip().lower().lstrip("@").split(":")[0]
                for x in (args.exclude or cfg("DIRECTORY_EXCLUDE")).split(",") if x.strip()}

    print(f"Loguję się do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
        people = list_people(syn, excluded)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BŁĄD połączenia/logowania do Synapse: {e}")
        sys.exit(1)
    print(f"Zalogowano. Aktywne konta lokalne: {len(people)}"
          + (f" (pominięto loginy: {', '.join(sorted(excluded))})" if excluded else ""))
    no_dept = [p for p in people if p["dept"] == NO_DEPT]
    if no_dept:
        print(f"UWAGA: {len(no_dept)} kont bez działu w nazwie wyświetlanej (trafią do \"{NO_DEPT}\"): "
              + ", ".join(p["login"] for p in no_dept[:8]) + (" ..." if len(no_dept) > 8 else ""))
    print()

    extra_path = Path(args.extra_file) if args.extra_file else DEFAULT_EXTRA_FILE
    if args.write_extra_template:
        write_template(extra_path, people, args.dry_run)
        return

    if args.limit:
        people = pick_sample(people, args.limit)
        print(f"Próbka (--limit): {len(people)} osób.\n")

    demo = args.fake_extra
    if demo:
        extras = {p["login"]: demo_extra(p["login"]) for p in people}
        print("DANE DODATKOWE: SZTUCZNE (--fake-extra).")
    elif extra_path.exists():
        extras = load_extra(extra_path)
        unknown = sorted(set(extras) - {p["login"] for p in people})
        print(f"DANE DODATKOWE: {extra_path.name} -- wpisy dla {len(set(extras) & {p['login'] for p in people})} osób.")
        if unknown:
            print(f"  UWAGA: loginy z pliku bez konta w Synapse (literówka?): {', '.join(unknown[:10])}")
    else:
        extras = {}
        print(f"DANE DODATKOWE: brak pliku {extra_path.name} (bez telefonów/pokoi). "
              f"Utwórz szablon: python setup_directory.py --write-extra-template")
    print()

    today = datetime.date.today().isoformat()
    plan = plan_messages(people, extras, today, demo)

    # --- pokoj ---
    room_id = ensure_room(syn, spec, args.dry_run)
    if room_id:
        ensure_name_topic(syn, room_id, spec, args.dry_run)
        ensure_power_levels(syn, room_id, True, writers, args.dry_run)
        if args.alias:
            print("  Space: pokój próbny (--alias) -- nie podpinam pod Firmę.")
        else:
            link_to_space(syn, room_id, args.dry_run)
        if args.skip_join:
            print("  Członkowie: pominięto (--skip-join).")
        else:
            join_all(syn, room_id, [p["mxid"] for p in people], args.rejoin, args.dry_run)
    print()

    # --- porownanie z tym, co juz jest w pokoju ---
    existing = {}
    if room_id:
        existing = dict((syn.get_state(room_id, STATE_TYPE) or {}).get("messages") or {})
    keys = {it["key"] for it in plan}
    if args.rebuild:
        removals, base = list(existing), {}
    else:
        removals, base = [k for k in existing if k not in keys], existing
    for it in plan:
        old = base.get(it["key"])
        it["action"] = "NOWA" if old is None else ("EDYCJA" if old.get("sha") != it["sha"] else "bez zmian")

    print(f"{'Wiadomość':<44}{'osób':>5}{'rozmiar B':>11}   akcja")
    for it in plan:
        print(f"{it['key']:<44}{it['n']:>5}{event_size(it['final']):>11}   {it['action']}")
    for k in removals:
        print(f"{k:<44}{'':>5}{'':>11}   USUNIĘCIE")
    biggest = max(event_size(it["final"]) for it in plan)
    print(f"Największa wiadomość: {biggest} B (limit roboczy {MSG_LIMIT} B; edycja ~2x).")
    new_keys = [it["key"] for it in plan if it["action"] == "NOWA"]
    if new_keys and existing and not args.rebuild:
        print("UWAGA: nowe wiadomości trafią na DÓŁ osi czasu (kolejność alfabetyczną przywróci --rebuild).")
    print()

    if args.dry_run:
        print("=== KONIEC TRYBU PRÓBNEGO ===")
        return

    # --- wykonanie ---
    mapping = {k: v for k, v in base.items() if k not in removals}
    try:
        for k in removals:
            try:
                redact(syn, room_id, existing[k]["event_id"])
                print(f"  usunięto: {k}")
            except RuntimeError as e:
                print(f"  BŁĄD usuwania '{k}': {e}")
        for it in plan:
            if it["action"] == "bez zmian":
                continue
            if it["action"] == "EDYCJA":
                eid = base[it["key"]]["event_id"]
                edit_text(syn, room_id, eid, it["final"])
                print(f"  zedytowano: {it['key']}")
            else:
                eid = send_text(syn, room_id, it["final"])
                print(f"  wysłano: {it['key']}")
            mapping[it["key"]] = {"event_id": eid, "sha": it["sha"]}
    finally:
        syn.put_state(room_id, STATE_TYPE, {"messages": mapping})

    if args.pin:
        wanted_pins = [mapping[INTRO_KEY]["event_id"]] if INTRO_KEY in mapping else []
    else:
        wanted_pins = []   # domyślnie bez przypięć (pasek u góry skleja tekst); stare przypięcia są zdejmowane
    current_pins = (syn.get_state(room_id, "m.room.pinned_events") or {}).get("pinned") or []
    if current_pins != wanted_pins:
        syn.put_state(room_id, "m.room.pinned_events", {"pinned": wanted_pins})
        print(f"  Przypięte wiadomości: {len(wanted_pins)}")

    print("\n=== GOTOWE ===")
    print(f"Pokój: \"{spec['name']}\" (#{alias}:{HOMESERVER_DOMAIN}). Sprawdź na koncie zwykłego pracownika:")
    print("  1. czy pokój jest na liście (dla właściwego pokoju: w space Firma),")
    print("  2. czy działy się rozwijają, a nazwiska są pigułkami z danymi obok,")
    print("  3. co robi klik w pigułkę, 4. czy wpisy 'X dołączył' są zwinięte w jedną linię.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBŁĄD: {e}")
        sys.exit(1)
