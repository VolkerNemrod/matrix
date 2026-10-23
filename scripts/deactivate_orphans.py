#!/usr/bin/env python3
"""
deactivate_orphans.py -- Etap 1 (README, "Odejscie pracownika"): dezaktywuje w Synapse konta, ktorych
nie ma juz w LLDAP (w firmie: AD).

PO CO: usuniecie osoby z LLDAP blokuje jej logowanie (logowanie idzie przez LDAP), ale konto w Synapse
zostaje i -- przy search_all_users -- dalej wyskakuje w wyszukiwarce uzytkownikow i w ksiazce adresowej.
Ten skrypt porownuje aktywne konta lokalne Synapse z lista uzytkownikow LLDAP i dezaktywuje te, ktore
istnieja tylko w Synapse (Admin API: POST /_synapse/admin/v1/deactivate/<mxid>).

Czego NIE rusza (zabezpieczenia):
  - konta ADMIN_LOGIN i kazdego konta z flaga administratora Synapse,
  - kont technicznych (user_type bot/support) i gosci,
  - loginow podanych w --keep albo w DEACTIVATE_KEEP w .env (po przecinku) -- np. konta techniczne,
    ktorych celowo nie ma w LLDAP,
  - nic nie robi, gdy LLDAP zwroci pusta liste (np. awaria) albo gdy do dezaktywacji bylaby ponad
    polowa kont (zabezpieczenie przed pomylka; --force wylacza ten limit).
Dezaktywacji w Synapse NIE da sie cofnac w prosty sposob (konto nie wroci do uzycia z tym samym
loginem bez recznej interwencji) -- dlatego zawsze najpierw --dry-run.

Uzycie (PC, katalog scripts, venv aktywny):
  python deactivate_orphans.py --dry-run          # tylko lista: kogo by dezaktywowano
  python deactivate_orphans.py                    # lista + pytanie o potwierdzenie (wpisz TAK)
  python deactivate_orphans.py --yes              # bez pytania
  python deactivate_orphans.py --keep login1,login2
  python deactivate_orphans.py --erase            # dodatkowo usuwa dane profilu (nazwa, awatar)

Potem (przerwa ok. 4 min -- limit logowania, HTTP 429):
  python setup_directory.py --dry-run
  python setup_directory.py

Wymaga: pip install requests (scripts/requirements.txt); w .env na PC: SYNAPSE_ADMIN_PASSWORD, TS_IP,
LLDAP_ADMIN_PASSWORD. Korzysta z kodu provision_synapse_users.py (odczyt LLDAP) i setup_main_room.py
(Synapse).
"""

import argparse
import os
import sys

import requests

from provision_synapse_users import LldapReader, load_dotenv_value, resolve_lldap_url
from setup_main_room import (
    ADMIN_LOGIN, ADMIN_PASSWORD, HOMESERVER_DOMAIN, MATRIX_BASE_URL, ROOT_CA_PATH, Synapse, q,
)

MAX_SHARE = 0.5   # tyle (ulamek aktywnych kont) wolno dezaktywowac bez --force


def safe(text) -> str:
    """Tekst bezpieczny dla konsoli Windows (bez znakow spoza ASCII)."""
    return str(text or "").encode("ascii", "replace").decode("ascii")


def list_synapse_users(syn: Synapse) -> list:
    """Aktywne konta lokalne (bez gosci)."""
    users, token = [], None
    while True:
        params = {"limit": 100, "deactivated": "false", "guests": "false"}
        if token is not None:
            params["from"] = token
        data = syn.call("GET", "/_synapse/admin/v2/users", params=params).json()
        users.extend(data.get("users", []))
        token = data.get("next_token")
        if token is None:
            break
    return users


def localpart(mxid: str) -> str:
    return mxid.split(":", 1)[0].lstrip("@").lower()


def main():
    parser = argparse.ArgumentParser(description="Dezaktywuje w Synapse konta, ktorych nie ma juz w LLDAP.")
    parser.add_argument("--dry-run", action="store_true", help="tylko pokaz liste (bez dezaktywacji)")
    parser.add_argument("--yes", action="store_true", help="nie pytaj o potwierdzenie")
    parser.add_argument("--keep", default="", help="loginy do pominiecia, po przecinku (oprocz DEACTIVATE_KEEP z .env)")
    parser.add_argument("--erase", action="store_true", help="przy dezaktywacji usun tez dane profilu (erase=true)")
    parser.add_argument("--force", action="store_true", help="wylacz limit 'maks. polowa kont'")
    args = parser.parse_args()

    if not ROOT_CA_PATH.exists():
        print(f"BLAD: nie znaleziono {ROOT_CA_PATH} (certyfikat CA projektu).")
        sys.exit(1)

    keep = {ADMIN_LOGIN.lower()}
    for src in (args.keep, os.environ.get("DEACTIVATE_KEEP") or load_dotenv_value("DEACTIVATE_KEEP")):
        keep |= {x.strip().lower() for x in src.split(",") if x.strip()}

    if args.dry_run:
        print("*** TRYB PROBNY (--dry-run): nic nie zostanie zmienione ***\n")

    # --- LLDAP: kto istnieje ---
    lldap_url = resolve_lldap_url()
    lldap_password = os.environ.get("LLDAP_ADMIN_PASSWORD") or load_dotenv_value("LLDAP_ADMIN_PASSWORD")
    if not lldap_password or lldap_password.startswith("CHANGE_ME"):
        print("BLAD: nie znaleziono LLDAP_ADMIN_PASSWORD w .env.")
        sys.exit(1)
    print(f"Lacze sie z LLDAP ({lldap_url})...")
    try:
        lldap = LldapReader(lldap_url, "admin", lldap_password)
        lldap_users = lldap.list_users_with_groups()
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD odczytu LLDAP: {e}")
        sys.exit(1)
    lldap_ids = {u["id"].lower() for u in lldap_users}
    if not lldap_ids:
        print("BLAD: LLDAP zwrocil pusta liste uzytkownikow -- przerywam (nikogo nie dezaktywuje).")
        sys.exit(1)
    print(f"Uzytkownikow w LLDAP: {len(lldap_ids)}")

    # --- Synapse: kto jest aktywny ---
    print(f"Loguje sie do Synapse ({MATRIX_BASE_URL}) jako '{ADMIN_LOGIN}'...")
    syn = Synapse(MATRIX_BASE_URL, str(ROOT_CA_PATH), HOMESERVER_DOMAIN)
    try:
        syn.login(ADMIN_LOGIN, ADMIN_PASSWORD)
        active = list_synapse_users(syn)
    except (requests.RequestException, RuntimeError) as e:
        print(f"BLAD polaczenia/logowania do Synapse: {e}")
        sys.exit(1)
    print(f"Aktywnych kont w Synapse: {len(active)}\n")

    targets, skipped = [], []
    for u in active:
        mxid = u["name"]
        login = localpart(mxid)
        if login in lldap_ids:
            continue
        if u.get("admin") or login in keep or u.get("user_type"):
            skipped.append((mxid, "admin / --keep / konto techniczne"))
            continue
        targets.append(u)

    if skipped:
        print("Pominiete (brak w LLDAP, ale chronione):")
        for mxid, why in skipped:
            print(f"  - {mxid} [{why}]")
        print()

    if not targets:
        print("Nic do dezaktywacji -- wszystkie aktywne konta maja odpowiednik w LLDAP.")
        return

    print(f"Do dezaktywacji ({len(targets)}):")
    for u in targets:
        print(f"  - {u['name']:<40} {safe(u.get('displayname')) or '(bez nazwy)'}")
    print()

    if not args.force and len(targets) > MAX_SHARE * len(active):
        print(f"BLAD: do dezaktywacji bylaby ponad polowa aktywnych kont ({len(targets)} z {len(active)}).")
        print("To wyglada na pomylke (zly LLDAP? zle konto?). Sprawdz dane albo uruchom z --force.")
        sys.exit(1)

    if args.dry_run:
        print("=== KONIEC TRYBU PROBNEGO ===")
        return

    if not args.yes:
        answer = input("Dezaktywacja jest trudna do cofniecia. Wpisz TAK, aby dezaktywowac powyzsze konta: ").strip()
        if answer != "TAK":
            print("Przerwano -- nic nie zmieniono.")
            return

    failed = []
    for i, u in enumerate(targets, 1):
        mxid = u["name"]
        print(f"[{i}/{len(targets)}] Dezaktywuje {mxid}...")
        try:
            syn.call("POST", f"/_synapse/admin/v1/deactivate/{q(mxid)}", json={"erase": args.erase})
            print("    dezaktywowane")
        except (requests.RequestException, RuntimeError) as e:
            print(f"    BLAD: {e}")
            failed.append(mxid)

    print("\n=== PODSUMOWANIE ===")
    print(f"Dezaktywowane: {len(targets) - len(failed)}")
    print(f"Bledy:         {len(failed)}")
    if failed:
        print("  " + ", ".join(failed))
        sys.exit(1)
    print("Teraz: setup_directory.py (przerwa ok. 4 min -- limit logowania).")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"\nBLAD: {e}")
        sys.exit(1)
