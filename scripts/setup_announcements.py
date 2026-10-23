#!/usr/bin/env python3
"""
setup_announcements.py -- pokoj "Ogloszenia" (zamiast "Firma-Ogloszenia"): PUBLICZNY (kazdy z serwera moze dolaczyc przez
alias, ale pokoj nie jest w katalogu publicznym), TYLKO DO ODCZYTU, bez szyfrowania -- te same zasady co "Ksiazka adresowa"
(setup_directory.py), tyle ze skrypt NIE wysyla zadnych wiadomosci: ogloszenia pisza recznie w Elemencie admin
i osoby z ANNOUNCE_WRITERS.

CO ROBI (kazdy krok idempotentny -- mozna puszczac wielokrotnie, np. po dodaniu pracownikow):
  1. Loguje sie do Synapse jako admin, pobiera wszystkie aktywne konta lokalne.
  2. Pokoj: znajduje po aliasie albo tworzy (od razu publiczny, preset public_chat); nazwa, temat, uprawnienia
     "tylko do odczytu" (pisza admin i ANNOUNCE_WRITERS; reakcje emoji zablokowane, chyba ze --reactions),
     regula dolaczania "public".
  3. Dolacza do pokoju wszystkich z listy (pomija tych, ktorzy sami wyszli -- chyba ze --rejoin).

NIE USUWA starego pokoju "Firma-Ogloszenia": usun go recznie (panel Synapse Admin, z purge), gdy ogloszenia sie przeniosa.
Nowi pracownicy: po provision_synapse_users.py puszczaj ten skrypt ponownie (dolaczy nowych) albo ustaw w Synapse
auto_join_rooms (homeserver.yaml) -- tego skrypt nie robi.

Uzycie (PC, katalog scripts, venv aktywny):
  python setup_announcements.py --dry-run               # co by zrobil
  python setup_announcements.py                         # wykonaj
Opcje: --alias NAZWA (pokoj probny), --skip-join, --rejoin, --reactions (pozwol na reakcje emoji), --exclude login1,login2.
Ustawienia w .env (opcjonalne): ANNOUNCE_ROOM_ALIAS (domyslnie ogloszenia), ANNOUNCE_ROOM_NAME, ANNOUNCE_ROOM_TOPIC,
ANNOUNCE_WRITERS (domyslnie DIRECTORY_WRITERS, potem MAIN_ROOM_WRITERS), ANNOUNCE_JOIN_RULE (public | invite;
domyslnie public), ANNOUNCE_EXCLUDE (loginy po przecinku).

STATUS: uruchomiony przez uzytkownika 2026-10-20 (napisany 2026-10-19). Przy zmianach najpierw --dry-run.
Nie puszczaj skryptow pod rzad bez przerw (HTTP 429, README, Rozwiazywanie problemow, pkt 4).
Wymaga: pip install requests; setup_main_room.py i setup_directory.py w tym samym katalogu (importowane jako biblioteki).
"""

import argparse
import sys

import requests

from setup_directory import DEFAULT_JOIN_RULE, ensure_join_rule, ensure_room, join_all, list_people
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
)

DEFAULT_ALIAS = "ogloszenia"   # alias pokoju: #ogloszenia:<domena>


def main():
    ap = argparse.ArgumentParser(description="Pokój „Ogłoszenia”: publiczny, tylko do odczytu, bez wiadomości od skryptu.")
    ap.add_argument("--dry-run", action="store_true", help="nic nie zapisuj; pokaż plan")
    ap.add_argument("--alias", help="inny alias pokoju (np. do prób)")
    ap.add_argument("--skip-join", action="store_true", help="nie dołączaj osób do pokoju")
    ap.add_argument("--rejoin", action="store_true", help="dołącz też osoby, które same wyszły z pokoju")
    ap.add_argument("--reactions", action="store_true", help="pozwól na reakcje emoji (domyślnie zablokowane)")
    ap.add_argument("--exclude", default="", help="loginy pominięte, po przecinku (np. konta techniczne)")
    args = ap.parse_args()

    if not ROOT_CA_PATH.exists():
        print(f"BŁĄD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)
    if args.dry_run:
        print("*** TRYB PRÓBNY (--dry-run): nic nie zostanie zapisane ***\n")

    alias = (args.alias or cfg("ANNOUNCE_ROOM_ALIAS", DEFAULT_ALIAS)).lstrip("#").split(":")[0]
    join_rule = cfg("ANNOUNCE_JOIN_RULE", DEFAULT_JOIN_RULE).strip().lower()
    spec = {
        "alias": alias,
        "name": cfg("ANNOUNCE_ROOM_NAME", "Ogłoszenia") + (" (PRÓBA)" if args.alias else ""),
        "topic": cfg("ANNOUNCE_ROOM_TOPIC", "Ogłoszenia dla wszystkich pracowników (tylko do odczytu)"),
        "public": join_rule == "public",
    }
    writers = []
    for w in (cfg("ANNOUNCE_WRITERS") or cfg("DIRECTORY_WRITERS") or cfg("MAIN_ROOM_WRITERS")).split(","):
        w = w.strip().lstrip("@")
        if w:
            writers.append(f"@{w}" if ":" in w else f"@{w}:{HOMESERVER_DOMAIN}")
    excluded = {x.strip().lower().lstrip("@").split(":")[0]
                for x in (args.exclude or cfg("ANNOUNCE_EXCLUDE")).split(",") if x.strip()}

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
    print(f"Piszący (poza adminem): {len(writers)}.\n")

    room_id = ensure_room(syn, spec, args.dry_run)
    if room_id:
        ensure_name_topic(syn, room_id, spec, args.dry_run)
        ensure_power_levels(syn, room_id, True, writers, args.dry_run, allow_reactions=args.reactions)
        ensure_join_rule(syn, room_id, join_rule, args.dry_run)
        if args.skip_join:
            print("  Członkowie: pominięto (--skip-join).")
        else:
            join_all(syn, room_id, [p["mxid"] for p in people], args.rejoin, args.dry_run)
    print()

    if args.dry_run:
        print("=== KONIEC TRYBU PRÓBNEGO ===")
        return
    print("=== GOTOWE ===")
    print(f"Pokój: \"{spec['name']}\" (#{alias}:{HOMESERVER_DOMAIN}). Sprawdź na koncie zwykłego pracownika, czy jest na liście")
    print("i czy nie może pisać. Ogłoszenia pisze admin (lub osoba z ANNOUNCE_WRITERS) w Elemencie.")
    print("Stary pokój \"Firma-Ogłoszenia\" usuń ręcznie w panelu Synapse Admin (z purge), gdy ogłoszenia się przeniosą.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBŁĄD: {e}")
        sys.exit(1)
