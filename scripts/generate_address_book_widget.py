#!/usr/bin/env python3
"""
generate_address_book_widget.py -- generuje statyczna "sciage" pracownikow
(widget/index.html) na podstawie aktualnej struktury w LLDAP: drzewo
Dzial -> Lokalizacja -> Osoby.

CEL (zmiana podejscia, 2026-10-13): poprzedni widget mial liste ludzi wpisana
na sztywno w kodzie ORAZ klikalne linki matrix.to, ktore otwieraly przegladarke
(problem opisany w README, sekcja "Ksiazka adresowa"). To byl pretekst do
zastapienia go wbudowanym katalogiem Synapse (Etap A-C) -- i to dziala dobrze.

Ten skrypt NIE jest powrotem do starego podejscia. To CZYSTO INFORMACYJNA
"sciaga": pokazuje strukture firmy (kto jest w jakim dziale/lokalizacji) jako
drzewo, generowana automatycznie z LLDAP zamiast wpisywana recznie -- ale BEZ
zadnych klikalnych linkow, akcji czy wywolan do Synapse/Elementa. Osoba, ktora
znajdzie tu kogos, sama wpisuje jego imie i nazwisko w wyszukiwarce Elementa
(+ -> Rozpocznij czat, lewy panel) -- dokladnie tak jak dzialajacy juz Wariant 1
z README.

Wymaga: pip install requests
Uzycie: python generate_address_book_widget.py
"""

import os
import sys
from pathlib import Path

import requests

# ============================================================
# KONFIGURACJA
# ============================================================

# Te same listy co w seed_test_employees.py / provision_synapse_users.py --
# trzeba je trzymac w synchronizacji, jesli sie zmienia dzialy/lokalizacje.
DEPARTMENTS = ["Księgowość", "Wydział EFS", "Dyrekcja", "IT", "Sprzedaż"]
LOCATIONS = ["Warszawa", "Kraków", "Poznań"]

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "widget" / "index.html"

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


def resolve_lldap_url() -> str:
    ts_ip = os.environ.get("TS_IP") or load_dotenv_value("TS_IP")
    if not ts_ip or "x.x" in ts_ip:
        print("BLAD: brak TS_IP w .env.")
        sys.exit(1)
    return f"http://{ts_ip}:17170"


class LldapReader:
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

    def list_users_with_groups(self):
        q = """
        query {
          users {
            id
            firstName
            lastName
            displayName
            groups { displayName }
          }
        }
        """
        r = self.session.post(
            f"{self.base_url}/api/graphql",
            json={"query": q, "variables": {}},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"Blad GraphQL: {data['errors']}")
        return data["data"]["users"]


def build_tree(users):
    """Zwraca: { dzial: { lokalizacja: [ {name, login}, ... ], "_bez_lokalizacji": [...] }, "_bez_dzialu": [...] }"""
    tree = {}
    no_dept = []
    for u in users:
        if u["id"] == "admin":
            continue
        first = u.get("firstName") or ""
        last = u.get("lastName") or ""
        name = f"{first} {last}".strip() or u["id"]
        group_names = {g["displayName"] for g in (u.get("groups") or [])}
        dept = next((d for d in DEPARTMENTS if d in group_names), None)
        loc = next((l for l in LOCATIONS if l in group_names), None)
        person = {"name": name, "login": u["id"]}

        if not dept:
            no_dept.append(person)
            continue
        tree.setdefault(dept, {})
        loc_key = loc or "Bez przypisanej lokalizacji"
        tree[dept].setdefault(loc_key, []).append(person)

    # sortowanie osob w kazdej grupie alfabetycznie po nazwisku
    for dept in tree.values():
        for loc in dept.values():
            loc.sort(key=lambda p: p["name"].split()[-1] if p["name"].split() else p["name"])
    no_dept.sort(key=lambda p: p["name"].split()[-1] if p["name"].split() else p["name"])

    return tree, no_dept


def render_html(tree: dict, no_dept: list) -> str:
    total = sum(len(people) for dept in tree.values() for people in dept.values()) + len(no_dept)

    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

    sections = []
    # działy w ustalonej kolejności z DEPARTMENTS, potem cokolwiek dodatkowego
    ordered_depts = [d for d in DEPARTMENTS if d in tree] + [d for d in tree if d not in DEPARTMENTS]

    for dept in ordered_depts:
        locs = tree[dept]
        dept_count = sum(len(people) for people in locs.values())
        loc_blocks = []
        ordered_locs = [l for l in LOCATIONS if l in locs] + [l for l in locs if l not in LOCATIONS]
        for loc in ordered_locs:
            people = locs[loc]
            rows = "\n".join(
                f'          <li class="person" data-search="{esc(p["name"].lower())} {esc(loc.lower())} {esc(dept.lower())} {esc(p["login"].lower())}">'
                f'<span class="name">{esc(p["name"])}</span>'
                f'<span class="meta">@{esc(p["login"])}</span></li>'
                for p in people
            )
            loc_blocks.append(
                f'        <details class="loc" open>\n'
                f'          <summary>{esc(loc)} <span class="count">({len(people)})</span></summary>\n'
                f'          <ul class="people">\n{rows}\n          </ul>\n'
                f"        </details>"
            )
        sections.append(
            f'      <details class="dept">\n'
            f'        <summary>{esc(dept)} <span class="count">({dept_count})</span></summary>\n'
            + "\n".join(loc_blocks)
            + "\n      </details>"
        )

    if no_dept:
        rows = "\n".join(
            f'          <li class="person" data-search="{esc(p["name"].lower())} {esc(p["login"].lower())}">'
            f'<span class="name">{esc(p["name"])}</span>'
            f'<span class="meta">@{esc(p["login"])}</span></li>'
            for p in no_dept
        )
        sections.append(
            f'      <details class="dept">\n'
            f'        <summary>Bez przypisanego działu <span class="count">({len(no_dept)})</span></summary>\n'
            f'        <ul class="people">\n{rows}\n        </ul>\n'
            f"      </details>"
        )

    sections_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ściąga: struktura firmy</title>
<style>
  :root {{ --bg:#0b1410; --fg:#e8fff1; --muted:#7fa893; --line:#1f3a2c; --accent:#7dffb3; --panel:#16382a; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:14px; font:14px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--fg); }}
  h1 {{ font-size:16px; margin:0 0 4px; }}
  .sub {{ color:var(--muted); font-size:12px; margin:0 0 12px; }}
  #q {{ width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--panel); color:var(--fg); font:inherit; }}
  #q:focus {{ outline:2px solid var(--accent); border-color:transparent; }}
  #count {{ margin:8px 2px; color:var(--muted); font-size:12px; }}
  details.dept {{ border:1px solid var(--line); border-radius:8px; margin:0 0 8px; background:var(--panel); overflow:hidden; }}
  details.dept > summary {{ padding:10px 12px; font-weight:600; cursor:pointer; list-style:none; }}
  details.dept > summary::-webkit-details-marker {{ display:none; }}
  details.loc {{ margin:0 10px 8px 10px; border-left:2px solid var(--line); padding-left:10px; }}
  details.loc > summary {{ padding:4px 0; font-weight:500; cursor:pointer; list-style:none; color:var(--muted); font-size:13px; }}
  details.loc > summary::-webkit-details-marker {{ display:none; }}
  .count {{ color:var(--muted); font-weight:400; font-size:12px; }}
  ul.people {{ list-style:none; margin:0 0 6px; padding:0; }}
  li.person {{ display:flex; justify-content:space-between; gap:10px; padding:5px 4px; border-bottom:1px solid var(--line); }}
  li.person:last-child {{ border-bottom:none; }}
  .name {{ font-weight:500; }}
  .meta {{ color:var(--muted); font-size:12px; white-space:nowrap; }}
  .hidden {{ display:none !important; }}
  #empty {{ display:none; padding:16px 6px; color:var(--muted); }}
  .hint {{ color:var(--muted); font-size:12px; margin:12px 2px 0; }}
</style>
</head>
<body>
  <h1>Ściąga: struktura firmy</h1>
  <p class="sub">Generowane automatycznie z LLDAP. To TYLKO podgląd — kliknięcie niczego nie otwiera.
  Znajdź osobę tutaj, a potem wpisz jej imię i nazwisko w wyszukiwarce Elementa (po lewej: + → Rozpocznij czat).</p>
  <input id="q" type="search" placeholder="Szukaj: imię, nazwisko, dział, lokalizacja, login…" autocomplete="off">
  <div id="count">Łącznie: {total} osób</div>

{sections_html}

  <div id="empty">Brak wyników.</div>
  <p class="hint">Plik wygenerowany przez scripts/generate_address_book_widget.py — nie edytuj ręcznie, uruchom skrypt ponownie.</p>

<script>
  const q = document.getElementById("q");
  const empty = document.getElementById("empty");
  const people = Array.from(document.querySelectorAll("li.person"));
  const depts = Array.from(document.querySelectorAll("details.dept"));

  function norm(s) {{
    return s.toLowerCase().normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").replace(/ł/g, "l");
  }}

  function filter() {{
    const words = norm(q.value).split(/\\s+/).filter(Boolean);
    let visibleTotal = 0;

    for (const dept of depts) {{
      let deptVisible = 0;
      const locBlocks = dept.querySelectorAll("details.loc");
      const rows = locBlocks.length ? null : dept.querySelectorAll("li.person");

      const processRows = (rowList) => {{
        let locVisible = 0;
        for (const li of rowList) {{
          const hay = norm(li.dataset.search || "");
          const match = words.every(w => hay.includes(w));
          li.classList.toggle("hidden", !match);
          if (match) locVisible++;
        }}
        return locVisible;
      }};

      if (locBlocks.length) {{
        for (const loc of locBlocks) {{
          const v = processRows(loc.querySelectorAll("li.person"));
          loc.classList.toggle("hidden", v === 0 && words.length > 0);
          if (words.length > 0) loc.open = v > 0;
          deptVisible += v;
        }}
      }} else {{
        deptVisible = processRows(rows);
      }}

      dept.classList.toggle("hidden", deptVisible === 0 && words.length > 0);
      if (words.length > 0) dept.open = deptVisible > 0;
      visibleTotal += deptVisible;
    }}

    document.getElementById("count").textContent = words.length
      ? `Wyniki: ${{visibleTotal}} / {total}`
      : `Łącznie: {total} osób`;
    empty.style.display = (words.length && visibleTotal === 0) ? "block" : "none";
  }}

  q.addEventListener("input", filter);
</script>
</body>
</html>
"""


def main():
    lldap_url = resolve_lldap_url()
    admin_password = os.environ.get("LLDAP_ADMIN_PASSWORD") or load_dotenv_value("LLDAP_ADMIN_PASSWORD")
    if not admin_password or admin_password.startswith("CHANGE_ME"):
        print("BLAD: nie znaleziono LLDAP_ADMIN_PASSWORD w .env.")
        sys.exit(1)

    print(f"Lacze sie z LLDAP ({lldap_url})...")
    reader = LldapReader(lldap_url, "admin", admin_password)
    users = reader.list_users_with_groups()
    print(f"Znaleziono {len(users)} userow w LLDAP.")

    tree, no_dept = build_tree(users)
    html = render_html(tree, no_dept)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nZapisano: {OUTPUT_PATH}")
    print("Nastepny krok: wyslij plik na VM (scp lub git pull, jak reszte projektu) i odswiez widget w pokoju.")


if __name__ == "__main__":
    main()
