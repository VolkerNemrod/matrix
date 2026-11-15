# Test u kolegi: komputer w innej lokalizacji

> Część dokumentacji projektu Matrix PoC. Podstawowa ścieżka klienta (Windows, Element Desktop) jest w
> [README – krok 9.1](../README.md#91-windows-element-desktop); tu jest to samo dla osoby w zupełnie innej sieci
> (README, krok 9.2).

> ⚠️ **Status: opisane, ale NIESPRAWDZONE w praktyce.** To plan krok po kroku na test „co widzi osoba w innej sieci,
> u siebie w domu/biurze” – symulacja drugiej lokalizacji firmy. Dopisz tu wynik, gdy kolega faktycznie to przetestuje.

## Zasada

Projekt **nie zależy od Tailscale**: serwer jest dostępny pod swoją domeną (`<DOMENA>`, `MATRIX_DOMAIN` z `.env`), a każdy
klient potrzebuje tylko:

1. **łączności z serwerem** – przez VPN firmy, sieć lokalną albo (do szybkiego testu) Tailscale,
2. **wpisu w `hosts`**: `<IP_SERWERA>   <DOMENA>`,
3. **zainstalowanego `rootCA.pem`** (publiczny certyfikat urzędu, który podpisał certyfikat serwera).

Nie ma osobnego certyfikatu ani dodatkowej konfiguracji serwera dla „drugiej lokalizacji”: kolega robi to samo co
[README, krok 9.1](../README.md#91-windows-element-desktop). Adres w `hosts` to adres serwera **widziany z jego sieci**.
Przy Tailscale jest to adres Tailscale serwera (`tailscale ip -4` na VM), przy VPN firmy – adres z tego VPN-u.

## Co przekazujesz koledze

- plik **`rootCA.pem`** (z `certs/rootCA.pem` na serwerze; to certyfikat publiczny),
- **`<IP_SERWERA>`** i **`<DOMENA>`** (do wpisu w `hosts`),
- login i hasło **konta testowego** (patrz niżej),
- link do tej instrukcji.

> ⛔ **Nigdy** nie wysyłaj `pki/rootCA.key` (klucz urzędu) ani `certs/matrix.key`. Klucz urzędu zostaje wyłącznie na serwerze.

> ⚠️ **Co to oznacza dla kolegi:** instaluje u siebie zaufany urząd certyfikacji, którym można podpisać certyfikat dla
> dowolnej strony (nie tylko dla `<DOMENA>`). Do testu to akceptowalne, jeśli ufa Ci i kluczowi `rootCA.key`,
> ale po teście warto go usunąć (patrz „Po teście”). Bezpieczniejszy wariant: zaimportować `rootCA.pem` tylko do
> Firefoksa (ma własny magazyn certyfikatów) i testować w nim w przeglądarce, bez instalacji w systemie.

## Dostęp do sieci

**Tailscale (szybki test):** kolega zakłada konto (tailscale.com, wystarczy darmowe osobiste), a Ty udostępniasz mu
maszynę serwera: panel Tailscale (login.tailscale.com) → **Machines** → przy VM **Share** → e-mail kolegi. Kolega przyjmuje
zaproszenie i instaluje Tailscale (tailscale.com/download). Udostępnienie dotyczy tylko tej jednej maszyny, bez dołączania
do reszty Twojej sieci.

- **Niesprawdzone:** czy udostępniona w ten sposób maszyna działa identycznie jak pełne członkostwo w tailnecie (adres
  `100.x.x.x` po stronie kolegi) i czy ruch jest rzeczywiście jednokierunkowy. Jeśli **Share** nie zadziała, alternatywa to
  zaproszenie kolegi jako pełnego członka tailnetu (**Users** → **Invite**).

**VPN firmy:** kolega łączy się z VPN wg zasad firmy; wpis w `hosts` ma adres serwera z tego VPN-u.

**Sprawdzenie połączenia** (PowerShell kolegi; przy Tailscale): `tailscale ping <IP_SERWERA>` – ma pokazać odpowiedzi (czas
w ms), a nie `no response`. Bez Tailscale: `Test-NetConnection <IP_SERWERA> -Port 443` ma dać `TcpTestSucceeded : True`.

## Co kolega robi u siebie

1. **Plik `hosts`** i **`rootCA.pem`** – dokładnie jak w [README, krok 9.1](../README.md#91-windows-element-desktop)
   (Notatnik jako administrator → `C:\Windows\System32\drivers\etc\hosts` → dopisać `<IP_SERWERA>   <DOMENA>` → **Ctrl+S**;
   certyfikat: PowerShell jako administrator, `certutil -addstore -f "Root" rootCA.pem`; potem `ipconfig /flushdns`).
2. **Test w przeglądarce** (przed Elementem): `https://<DOMENA>/_matrix/client/versions` – ma pokazać JSON, **bez** ostrzeżenia
   o certyfikacie.
3. **Element Desktop** (element.io/download): przy logowaniu **Edytuj** przy serwerze domowym → `https://<DOMENA>`.
4. **Logowanie** loginem i hasłem z LLDAP. **Zalecane: jedno z testowych kont z Etapu B0** (patrz
   [Przygotowanie, Etap B0](administrowanie.md#etap-b0--testowa-struktura-firmy-w-lldap), ok. 200 fikcyjnych kont,
   wspólne hasło testowe), a nie konto prawdziwego pracownika – to dane niezwiązane z żadną realną tożsamością.

## Co przetestować po zalogowaniu

- **Wiadomości:** pokój `Firma-Ogolny` albo nowy DM z kolegi do Ciebie – czy wszystko działa przez prawdziwą sieć (nie LAN).
- **Rozmowa audio/wideo 1:1** – kluczowy test tego scenariusza (symulacja 2. lokalizacji). **Niesprawdzone:**
  - czy połączenie A/V przechodzi między dwiema różnymi sieciami przez Coturn (u nas testowane tylko w jednej sieci),
  - Coturn ogłasza **jeden** zewnętrzny adres (`SERVER_IP` z `.env`, `--external-ip`); musi to być adres, który klient
    faktycznie widzi (przy teście przez Tailscale: adres Tailscale serwera; przy VPN firmy: adres z tego VPN-u),
  - Coturn potrzebuje portu **3478** oraz zakresu **49160–49200** na adresie `SERVER_IP` (poza standardowym **443** dla
    samego Elementa); zawężony firewall/ACL u kolegi albo w VPN to pierwsze podejrzane miejsce.
- Kolejność zalecana: najpierw zwykłe wiadomości, dopiero potem A/V – łatwiej odróżnić problem połączenia od problemu
  Coturn/WebRTC (szkic: [szkic-coturn-webrtc.md](szkic-coturn-webrtc.md)).

## Po teście

- Kolega usuwa wpis z `hosts` i certyfikat: `certmgr.msc` → Zaufane główne urzędy certyfikacji → certyfikat o nazwie
  `Matrix PoC Root CA - <DOMENA>` → Usuń (⚠️ niesprawdzone: `certutil -delstore "Root" "Matrix PoC Root CA - <DOMENA>"`).
- Ty cofasz udostępnienie maszyny w panelu Tailscale (**Machines** → **Share** → usuń dostęp) i, jeśli to było konto testowe,
  zmieniasz jego hasło albo dezaktywujesz konto.
