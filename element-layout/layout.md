# Wygląd Element Desktop – motywy i logo

Stan na 2026-10-18. Zmiana dotyczy **tylko Element Desktop** (telefony pominięte). Opisana w `README.md` (sekcja „Wygląd Element Desktop”), ale nie sprawdzona w aplikacji.

## Cel

- Stonowany tryb ciemny (nie czarny) zamiast dwóch wbudowanych motywów (jasny/ciemny).
- Własne logo na ekranie logowania i powitalnym.

## Rozwiązanie

Wygląd ustawia się po stronie klienta, w pliku `config.json` Element Desktop (`docker-compose.yml` nie zawiera Element Web, więc nie ma serwera, na którym można by to zmienić centralnie). Gotowy plik leży w tym katalogu: `element-layout\config.json`.

Plik zawiera:

- `default_server_config`: serwer `https://matrix.local` ustawiony z góry (przy logowaniu nie trzeba go wpisywać).
- `default_federate: false`, `default_country_code: "PL"`, `disable_guests: true`.
- `features.feature_custom_themes: "enable"`: włącza obsługę własnych motywów.
- `default_theme: "custom-Firma Dark"`: motyw startowy.
- Wersja uproszczona (2026-10-19): motywy zmieniają TYLKO kolory tła (`sidebar-color`, `roomlist-background-color`, `timeline-background-color`). Teksty, akcenty, podświetlenia i układ wiadomości (Modern / IRC / dymki) pochodzą z wbudowanego motywu ciemnego Elementa; układ wybiera każde konto samo (Ustawienia → Wygląd). Dymki dają różną szerokość zwiniętych działów w pokoju książki adresowej (patrz `SUMMARY_PX` w `scripts\setup_directory.py`).
- `setting_defaults.custom_themes`: sześć motywów (tabela niżej).
- `branding.auth_header_logo_url`: logo na ekranie logowania/powitalnym.

## Motywy

| Nazwa | Charakter |
|---|---|
| Firma Dark (domyślny) | granatowy, ciemne tło |
| Grafit i Szalwia | ciepły grafit, szałwiowa zieleń |
| Nord Zmierzch | chłodny, lodowo-niebieski |
| Sliwkowy Wieczor | przygaszony fiolet, pudrowy róż |
| Bursztyn i Mgla | ciepła szarość, bursztynowy akcent |
| Morska Stal | łupkowo-morski, turkusowy akcent |

Wybór motywu: Ustawienia → Wygląd.

## Wdrożenie na komputerze

⚠️ **Stan 2026-10-20 (Element Desktop 1.12.32): kopiowanie `config.json` do `%APPDATA%\Element\` NIE działa** – `fetch("config.json")` nadal zwraca domyślny config z `webapp.asar` (1914 znaków, nie nasze 2644). Obowiązuje wersja (b): ręczne ustawienia konta (motyw Ciemny, układ Nowoczesny, wyłączone zdarzenia dołączeń/zmian nazwy/avatara/usuniętych wiadomości w *Preferencje → Oś czasu*) – opis krok po kroku w `docs\wyglad-element.md`. Wersja (a) (podmiana `config.json` w `webapp.asar`) odłożona na później. `setting_defaults` w pliku (layout Modern, `showJoinLeaves`, `showAvatarChanges`, `showDisplaynameChanges`, `showRedactions` = false) to tylko wartości domyślne, bez wymuszenia, i zadziałają dopiero po wdrożeniu wersji (a). Kroki poniżej to historia sprawdzonego podejścia.

Przed zmianą w profilu Element Desktop nie było żadnego `config.json`, więc nie ma czego nadpisywać ani porównywać.

1. Zamknij Element Desktop.
2. Skopiuj `element-layout\config.json` do `%APPDATA%\Element-<profil>\config.json` (przy uruchomieniu z `--profile <profil>`) albo do `%APPDATA%\Element\config.json` (bez profilu). Jeśli katalogu nie ma, uruchom Element raz i zamknij.
3. Uruchom Element. Zalogowane konto zostaje zalogowane; serwer z pliku zobaczysz po wylogowaniu.
4. Sprawdź rozszerzenie pliku: z Eksploratora Windows łatwo dostać `config.json.txt`.

Każdy komputer wymaga własnej kopii pliku (droga A: `config.json` na komputer, bez hostowania Element Web).

## Logo

- Plik `element-layout\logo-zastepcze.svg` jest w katalogu (neutralne logo zastępcze).
- Logo pojawia się na ekranie logowania i powitalnym. Nie zmienia ikony aplikacji ani paska bocznego (do tego trzeba by przebudować Element Desktop).
- Logo jest wpisane w `config.json` jako adres `data:image/svg+xml;base64,...` (plik ma ok. 0,4 KB), więc nie zależy od ścieżki ani osobnego pliku na komputerze. Wyświetlanie w Desktopie **nie jest sprawdzone**. Zmiana logo: zakoduj nowy plik do base64 i wstaw po `data:image/svg+xml;base64,` (PNG: `data:image/png;base64,`).
- Jeśli własne logo będzie ciemne, może być słabo widoczne na ciemnym tle. Wtedy potrzebna jest jasna wersja.

## Niesprawdzone / ograniczenia

- Motywy nie były oglądane w aplikacji; kolory to pierwsze przybliżenie do strojenia.
- System własnych motywów Element zmienia tylko część kolorów, więc możliwe są pojedyncze „dziwne” elementy. Pełna kontrola wymagałaby własnego CSS, którego Element oficjalnie nie wspiera.
- Czy własne motywy działają bez zgrzytów w używanej wersji Element Desktop: do potwierdzenia.

## Do zrobienia

1. Wdrożyć `config.json` w profilu, wybrać motyw, ocenić kolory i ewentualnie je dostroić.
2. Sprawdzić, czy logo się wyświetla (adres `data:`).
3. Dopiero potem rozdawać plik na stanowiska.

## Źródła

- Theming Element: https://github.com/element-hq/element-web/blob/develop/docs/theming.md
- Konfiguracja Element Web (`branding`, `setting_defaults`): https://github.com/element-hq/element-web/blob/master/docs/config.md
- Gotowe motywy: https://github.com/aaronraimist/element-themes, https://github.com/isabelroses/ctp-element
