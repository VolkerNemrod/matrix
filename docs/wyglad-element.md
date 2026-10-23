# Wygląd Element Desktop (motywy i logo, opcjonalne)

> Część dokumentacji projektu Matrix PoC. **Opcjonalne – kosmetyka, nie część wdrożenia testowego.**
> Dotyczy tylko Element Desktop, nie telefonów.

⚠️ *Stan na 2026-10-18: pliki są gotowe w katalogu `element-layout/`, ale nie były jeszcze sprawdzane w aplikacji (kolory,
logo, działanie własnych motywów w używanej wersji Element Desktop).* Notatki robocze: `element-layout/layout.md`.

**Cel:** stonowany ciemny motyw (zamiast dwóch wbudowanych: jasnego i ciemnego), własne logo na ekranie logowania i powitalnym
oraz serwer `matrix.local` ustawiony z góry (przy logowaniu nie trzeba go wpisywać).

**Jak to działa:** wygląd ma ustawiać plik `config.json` klienta Element Desktop. ⚠️ W Element Desktop 1.12.32 plik skopiowany do `%APPDATA%\Element\` **nie jest wczytywany** jako config webowy (diagnoza 2026-10-20, patrz niżej), więc do czasu wersji (a) wygląd ustawia się ręcznie w koncie – wersja (b). Gotowy wzór: `element-layout/config.json`.
`docker-compose.yml` nie zawiera Element Web, więc nie ma serwera, na którym zmianę dałoby się zrobić centralnie –
**każdy komputer potrzebuje własnej kopii pliku** (przy wdrożeniu klientów można ją rozdawać razem z `rootCA.pem`,
patrz [Wdrożenie klientów (D)](administrowanie.md#etap-d--klienci-do-sprawdzenia-przy-produkcji)).

Plik zawiera:

- `default_server_config`: serwer `https://matrix.local`, `default_federate: false`, `default_country_code: "PL"`,
  `disable_guests: true`,
- `features.feature_custom_themes` i `default_theme: "custom-Firma Dark"`: włączenie własnych motywów i motyw startowy,
- `setting_defaults.custom_themes`: sześć motywów (tabela niżej),
- `branding.auth_header_logo_url`: logo na ekranie logowania i powitalnym.

| Motyw | Charakter |
|---|---|
| **Firma Dark** (domyślny) | granatowy, ciemne tło |
| Grafit i Szalwia | ciepły grafit, szalwiowa zieleń |
| Nord Zmierzch | chłodny, lodowo-niebieski |
| Sliwkowy Wieczor | przygaszony fiolet, pudrowy róż |
| Bursztyn i Mgla | ciepła szarość, bursztynowy akcent |
| Morska Stal | łupkowo-morski, turkusowy akcent |

Motyw wybierasz w *Ustawienia → Wygląd*.
Kolory są pierwszym przybliżeniem do dostrojenia po obejrzeniu w aplikacji (edytuj wartości w `config.json`).

## Wersja (b): ręczne ustawienia konta (obowiązuje teraz)

🪟 **PC**, jednorazowo dla każdego konta (nowe konto = powtórz). Bez `config.json` nie ma własnych motywów, logo ani serwera
wpisanego z góry – za to to działa w każdej wersji Element Desktop i nie ginie przy aktualizacji aplikacji.

1. **Serwer przy logowaniu:** na ekranie logowania przy nazwie serwera kliknij *Zmień* (Edit) i wpisz `https://matrix.local`
   (komputer nadal potrzebuje wpisu w `hosts` i zaufanego `rootCA.pem`, patrz README). Po zalogowaniu Element zapamiętuje serwer.
2. **Wygląd:** avatar (lewy górny róg) → *Wszystkie ustawienia* → *Wygląd*:
   - *Motyw*: wbudowany **Ciemny**. Opcję „Dopasuj do systemu” wyłącz, żeby motyw nie skakał. (Własnych motywów, w tym
     „Firma Dark”, bez `config.json` nie ma.)
   - *Układ wiadomości*: **Nowoczesny** (Modern). Nie wybieraj dymków ani IRC: dymki zmieniają szerokość zwiniętych działów
     w pokoju „Książka adresowa” (`SUMMARY_PX` w `scripts\setup_directory.py`).
3. **Oś czasu:** *Wszystkie ustawienia* → *Preferencje* → sekcja *Oś czasu*. Wyłącz cztery opcje (nazwy angielskie, polskie mogą
   brzmieć nieco inaczej):
   - *Show join/leave events (invites/removes/bans unaffected)* – usuwa linię „… i 201 innych dołączyło”,
   - *Show display name changes*,
   - *Show profile picture changes*,
   - *Show a placeholder for removed messages*.
4. **Sprawdzenie:** otwórz pokój „Książka adresowa” i „Ogłoszenia”: ma nie być linii o dołączeniach, a działy mają mieć
   jednakową szerokość.

Ograniczenia wersji (b): brak własnego logo, brak własnych motywów, serwer trzeba wybrać przy pierwszym logowaniu; linia
„stworzył i skonfigurował pokój” zostaje (Element jej nie ukrywa – to nie zależy od konfiguracji). Ustawienia osi czasu
zapisują się na koncie i powinny być widoczne na innych urządzeniach, motyw i układ trzeba sprawdzić osobno na każdym
urządzeniu (niezweryfikowane).

## Wersja (a): `config.json` wewnątrz `webapp.asar` (na później)

Odłożone. Pomysł: rozpakować `resources\webapp.asar` (`npx asar extract`), podmienić w nim `config.json` na
`element-layout\config.json`, spakować (`npx asar pack`) – po zamknięciu Elementa i z kopią zapasową `webapp.asar`. Test:
`fetch("config.json")` w konsoli (Ctrl+Shift+I) ma zwrócić 2644 znaki, a nie 1914. Wada: zmiana ginie przy każdej aktualizacji
aplikacji, więc dla całej firmy sensowna dopiero jako własna paczka instalacyjna. Wersja (c) (Element Web na VM) nie zmienia
Desktopa i nie jest planowana.

## Kopiowanie `config.json` do `%APPDATA%` – NIE DZIAŁA (historia)

Diagnoza 2026-10-20 (Element Desktop 1.12.32): log startu wczytuje `Roaming\Element\config.json` jako „local config”, ale
`fetch("config.json")` nadal zwraca domyślny config z `webapp.asar` (1914 znaków). Wykluczone: flagi, zmienna
`ELEMENT_DESKTOP_CONFIG_JSON`, BOM, składnia JSON, cache. Kroki poniżej zostawione tylko jako zapis tego, co sprawdzono:

🪟 **PC**, dla każdego stanowiska osobno:

1. Zamknij Element Desktop.
2. Skopiuj `element-layout\config.json` do `%APPDATA%\Element\config.json` (zwykłe uruchomienie) albo do
   `%APPDATA%\Element-<profil>\config.json` (uruchomienie z `--profile <profil>`). Jeśli katalogu nie ma, uruchom Element raz
   i zamknij.
3. Uruchom Element. Zalogowane konto zostaje zalogowane; serwer z pliku zobaczysz dopiero po wylogowaniu.
4. Uwaga na rozszerzenie: z Eksploratora Windows łatwo dostać `config.json.txt`.

## Logo

- Plik: `element-layout/logo-zastepcze.svg` (neutralne logo zastępcze; prawdziwego logo firmy w repozytorium nie ma).
- Logo pojawia się na ekranie logowania i powitalnym. Nie zmienia ikony aplikacji ani paska bocznego (do tego trzeba by
  przebudować Element Desktop).
- Logo jest wpisane w `config.json` jako adres `data:image/svg+xml;base64,...` (plik ma tylko ok. 0,4 KB), więc działa na każdym
  komputerze bez osobnego pliku i bez zależności od ścieżki. ⚠️ Wyświetlanie logo w Element Desktop nie jest jeszcze sprawdzone.
  Gdy chcesz zmienić logo: podmień plik w `element-layout/` i zakoduj go ponownie (PowerShell:
  `[Convert]::ToBase64String([IO.File]::ReadAllBytes("logo-zastepcze.svg"))`), a wynik wstaw po `data:image/svg+xml;base64,` (dla PNG: `data:image/png;base64,`).
- Jeśli własne logo będzie ciemne, może być słabo widoczne na ciemnym tle. Wtedy potrzebna jest jasna wersja logo.

## Niesprawdzone i ograniczenia

- Motywy nie były oglądane w aplikacji.
- System własnych motywów Element zmienia tylko część kolorów, więc możliwe są pojedyncze „dziwne” elementy. Pełna
  kontrola wymagałaby własnego CSS, którego Element oficjalnie nie wspiera.
- Czy w używanej wersji Element Desktop działa taki zapis własnych motywów (flaga `feature_custom_themes`,
  `default_theme: "custom-…"`): do potwierdzenia.

**Do zrobienia:** wdrożyć `config.json` w jednym profilu, wybrać motyw i ocenić kolory, sprawdzić, czy logo się wyświetla,
a dopiero potem rozdawać plik na stanowiska.

**Źródła:** [dokumentacja motywów Element](https://github.com/element-hq/element-web/blob/develop/docs/theming.md),
[konfiguracja Element Web](https://github.com/element-hq/element-web/blob/master/docs/config.md) (`branding`, `setting_defaults`).
