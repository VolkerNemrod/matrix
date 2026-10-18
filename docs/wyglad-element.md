# Wygląd Element Desktop (motywy i logo, opcjonalne)

> Część dokumentacji projektu Matrix PoC. **Opcjonalne – kosmetyka, nie część wdrożenia testowego.**
> Dotyczy tylko Element Desktop, nie telefonów.

⚠️ *Stan na 2026-10-18: pliki są gotowe w katalogu `element-layout/`, ale nie były jeszcze sprawdzane w aplikacji (kolory,
logo, działanie własnych motywów w używanej wersji Element Desktop).* Notatki robocze: `element-layout/layout.md`.

**Cel:** stonowany ciemny motyw (zamiast dwóch wbudowanych: jasnego i ciemnego), logo firmy na ekranie logowania i powitalnym
oraz serwer `matrix.local` ustawiony z góry (przy logowaniu nie trzeba go wpisywać).

**Jak to działa:** wygląd ustawia plik `config.json` klienta Element Desktop. Gotowy wzór: `element-layout/config.json`.
`docker-compose.yml` nie zawiera Element Web, więc nie ma serwera, na którym zmianę dałoby się zrobić centralnie –
**każdy komputer potrzebuje własnej kopii pliku** (przy wdrożeniu klientów można ją rozdawać razem z `rootCA.pem`,
patrz [README – Wdrożenie klientów (D)](../README.md#etap-d--klienci-do-sprawdzenia-przy-produkcji)).

Plik zawiera:

- `default_server_config`: serwer `https://matrix.local`, `default_federate: false`, `default_country_code: "PL"`,
  `disable_guests: true`,
- `features.feature_custom_themes` i `default_theme: "custom-Firma Dark"`: włączenie własnych motywów i motyw startowy,
- `setting_defaults.custom_themes`: sześć motywów (tabela niżej),
- `branding.auth_header_logo_url`: logo na ekranie logowania i powitalnym.

| Motyw | Charakter |
|---|---|
| **Firma Dark** (domyślny) | granat i róż z logo firmy |
| Grafit i Szalwia | ciepły grafit, szalwiowa zieleń |
| Nord Zmierzch | chłodny, lodowo-niebieski |
| Sliwkowy Wieczor | przygaszony fiolet, pudrowy róż |
| Bursztyn i Mgla | ciepła szarość, bursztynowy akcent |
| Morska Stal | łupkowo-morski, turkusowy akcent |

Kolory logo użyte w „Firma Dark”: granat ok. `#2D3A8C`, róż ok. `#EC2E5B`. Motyw wybierasz w *Ustawienia → Wygląd*.
Kolory są pierwszym przybliżeniem do dostrojenia po obejrzeniu w aplikacji (edytuj wartości w `config.json`).

## Wdrożenie na komputerze

🪟 **PC**, dla każdego stanowiska osobno:

1. Zamknij Element Desktop.
2. Skopiuj `element-layout\config.json` do `%APPDATA%\Element\config.json` (zwykłe uruchomienie) albo do
   `%APPDATA%\Element-<profil>\config.json` (uruchomienie z `--profile <profil>`). Jeśli katalogu nie ma, uruchom Element raz
   i zamknij.
3. Uruchom Element. Zalogowane konto zostaje zalogowane; serwer z pliku zobaczysz dopiero po wylogowaniu.
4. Uwaga na rozszerzenie: z Eksploratora Windows łatwo dostać `config.json.txt`.

## Logo

- Plik: `element-layout/logo-firma.png` (128×109 px, PNG z przezroczystym tłem, ok. 3,5 KB).
- Logo pojawia się na ekranie logowania i powitalnym. Nie zmienia ikony aplikacji ani paska bocznego (do tego trzeba by
  przebudować Element Desktop).
- Logo jest wpisane w `config.json` jako adres `data:image/png;base64,...` (plik ma tylko ok. 3,5 KB), więc działa na każdym
  komputerze bez osobnego pliku i bez zależności od ścieżki. ⚠️ Wyświetlanie logo w Element Desktop nie jest jeszcze sprawdzone.
  Gdy chcesz zmienić logo: zamień PNG w `element-layout/` i zakoduj go ponownie (PowerShell:
  `[Convert]::ToBase64String([IO.File]::ReadAllBytes("logo-firma.png"))`), a wynik wstaw po `data:image/png;base64,`.
- Granatowy łuk może być słabo widoczny na ciemnym tle. Wtedy potrzebna jest druga, jasna wersja logo.

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
