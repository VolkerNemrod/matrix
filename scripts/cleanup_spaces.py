#!/usr/bin/env python3
"""
cleanup_spaces.py -- JEDNORAZOWE sprzatanie serwera po wycofaniu Matrix Spaces (README, Etap 2).

Usuwa przez Admin API (purge = skasowanie tez danych pokoju z bazy):
  - wszystkie pokoje-przestrzenie dawnego drzewa (Firma + dzialy): alias #space-* albo typ pokoju m.space,
  - obecny pokoj "Ksiazka adresowa" (#ksiazka-adresowa): ma wlaczone szyfrowanie, ktorego nie da sie
    wylaczyc -- setup_directory.py zaklada go od nowa (juz bez szyfrowania).
Nie rusza zadnych innych pokoi (testowych, prywatnych rozmow itp.). Po usunieciu sprawdza, czy aliasy
sie zwolnily. Nie wymaga tunelu SSH ani panelu Synapse Admin -- laczy sie jak pozostale skrypty
(https://matrix.local, konto administratora z .env).

Uzycie (PC, katalog scripts, venv aktywny):
  python cleanup_spaces.py --dry-run     # tylko lista: co zostaloby usuniete (nic nie zapisuje)
  python cleanup_spaces.py               # pokaze liste i zapyta o potwierdzenie (wpisz TAK)
  python cleanup_spaces.py --yes         # bez pytania
  python cleanup_spaces.py --keep-book   # nie usuwaj pokoju "Ksiazka adresowa"

Potem (przerwa ok. 4 min miedzy skryptami -- limit logowania, HTTP 429):
  python provision_synapse_users.py
  python setup_directory.py --dry-run
  python setup_directory.py

UWAGA: usuniecie jest NIEODWRACALNE.
"""

import argparse
import sys
import time

import requests

from setup_main_room import (
    ADMIN_LOGIN, ADMIN_PASSWORD, HOMESERVER_DOMAIN, MATRIX_BASE_URL, ROOT_CA_PATH, Synapse, q,
)

SPACE_ALIAS_PREFIX = "#space-"
BOOK_ALIAS = f"#ksiazka-adresowa:{HOMESERVER_DOMAIN}"


def safe(text) -> str:
    """Tekst bezpieczny dla konsoli Windows (bez znakow spoza ASCII)."""
    return str(text or "").encode("ascii", "replace").decode("ascii")


def list_rooms(syn: Synapse) -> list:
    rooms, token = [], None
    while True:
        params = {"limit": 100}
        if token is not None:
            params["from"] = token
        data = syn.call("GET", "/_synapse/admin/v1/rooms", params=params).json()
        rooms.extend(data.get("rooms", []))
        token = data.get("next_batch")
        if token is None:
            break
    return rooms


def pick_targets(syn: Synapse, rooms: list, keep_book: bool) -> list:
    """Zwraca liste (room, powod) -- tylko pokoje do usuniecia."""
    book_id = None if keep_book else syn.find_room_by_alias(BOOK_ALIAS)
    targets = []
    for r in rooms:
        alias = (r.get("canonical_alias") or "").lower()
        if alias.startswith(SPACE_ALIAS_PREFIX):
            targets.append((r, "przestrzen (alias #space-*)"))
        elif r.get("room_type") == "m.space":
            targets.append((r, "przestrzen (typ m.space)"))
        elif not keep_book and (alias == BOOK_ALIAS or r["room_id"] == book_id):
            targets.append((r, "ksiazka adresowa"))
    return targets


def purge_room(syn: Synapse, room_id: str):
    """Usuwa pokoj z purge. Zwraca (ok, komunikat)."""
    r = syn.call("DELETE", f"/_synapse/admin/v2/rooms/{q(room_id)}", json={"purge": True})
    delete_id = r.json().get("delete_id")
    if not delete_id:
        return False, "brak delete_id w odpowiedzi"
    for _ in range(90):   # do ok. 3 min
        time.sleep(2)
        st = syn.call("GET", f"/_synapse/admin/v2/rooms/delete_status/{q(delete_id)}").json()
        status = st.get("status")
        if status == "complete":
            return True, ""
        if status == "failed":
            return False, str(st.get("error", "nieznany blad"))
    return False, "przekroczono czas oczekiwania na zakonczenie usuwania"


def main():
    parser = argparse.ArgumentParser(description="Jednorazowe sprzatanie: usuwa pokoje Spaces i pokoj ksiazki adresowej.")
    parser.add_argument("--dry-run", action="store_true", help="tylko pokaz liste (bez usuwania)")
    parser.add_argument("--yes", action="store_true", help="nie pytaj o potwierdzenie")
    parser.add_argument("--keep-book", action="store_true", help="nie usuwaj pokoju 'Ksiazka adresowa'")
    args = parser.parse_args()

    if not ROOT_CA_PATH.exists():
        print(f"BLAD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)

    if args.dry_run:
        print("*** TRYB PROBNY (--dry-run): nic nie zostanie usuniete ***\n")

    print(f"Loguje sie do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia/logowania do Synapse: {e}")
        sys.exit(1)
    print("Zalogowano.\n")

    rooms = list_rooms(syn)
    print(f"Pokoi na serwerze: {len(rooms)}")
    targets = pick_targets(syn, rooms, args.keep_book)

    if not targets:
        print("Nic do usuniecia (brak pokoi #space-*, przestrzeni m.space i pokoju ksiazki).")
        return

    print(f"\nDo usuniecia ({len(targets)}):")
    for r, why in targets:
        print(f"  - {safe(r.get('name')) or '(bez nazwy)':<32} {safe(r.get('canonical_alias')) or '(bez aliasu)':<42} "
              f"czlonkow: {r.get('joined_members', '?'):<4} [{why}]")
    print()

    if args.dry_run:
        print("=== KONIEC TRYBU PROBNEGO ===")
        return

    if not args.yes:
        answer = input("Usuniecie jest NIEODWRACALNE. Wpisz TAK, aby usunac powyzsze pokoje: ").strip()
        if answer != "TAK":
            print("Przerwano -- nic nie usunieto.")
            return

    failed = []
    for i, (r, _why) in enumerate(targets, 1):
        label = safe(r.get("name")) or r["room_id"]
        print(f"[{i}/{len(targets)}] Usuwam {label} ({r['room_id']})...")
        try:
            ok, msg = purge_room(syn, r["room_id"])
        except RuntimeError as e:
            ok, msg = False, str(e)
        if ok:
            print("    usuniety")
        else:
            print(f"    BLAD: {msg}")
            failed.append(label)

    print("\nSprawdzam, czy aliasy sie zwolnily:")
    still = []
    for r, _why in targets:
        alias = r.get("canonical_alias")
        if not alias:
            continue
        if syn.find_room_by_alias(alias):
            print(f"  {alias}: NADAL ZAJETY")
            still.append(alias)
        else:
            print(f"  {alias}: wolny")

    print()
    if failed or still:
        print("=== ZAKONCZONO Z PROBLEMAMI ===")
        if failed:
            print("Nie usunieto: " + ", ".join(failed))
        if still:
            print("Aliasy nadal zajete: " + ", ".join(still) + " (uruchom skrypt ponownie albo usun pokoj w Synapse Admin z purge)")
        sys.exit(1)
    print("=== GOTOWE === Teraz: provision_synapse_users.py -> setup_directory.py (przerwa ok. 4 min miedzy skryptami).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBLAD: {e}")
        sys.exit(1)
