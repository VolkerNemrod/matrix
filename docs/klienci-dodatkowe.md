# Klienci – warianty dodatkowe (telefon, komputer w innej lokalizacji)

> Część dokumentacji projektu Matrix PoC. Podstawowa ścieżka klienta (Windows, Element Desktop) jest w
> [README – krok 9.1](../README.md#91-windows-element-desktop). Tu są dwa warianty, potrzebne tylko jeśli
> testujesz dostęp z telefonu albo z zupełnie innej sieci.

## Android (Element przez nazwę z Tailscale)

**Dlaczego inaczej niż na Windows:** telefon nie ma pliku `hosts`, więc nie rozwiąże `matrix.local`.
Zamiast tego łączymy się przez nazwę MagicDNS z Tailscale (`<PELNA-NAZWA-TS>`) i prawdziwy certyfikat
z Tailscale – **na telefonie nie instalujesz żadnego Root CA**.

> Sprawdzone na: Android 16, Element Classic 1.6.66. Telefon musi mieć włączone Tailscale i być w tym samym
> tailnecie co serwer.

**1. Panel Tailscale** (login.tailscale.com → zakładka **DNS**): włącz **MagicDNS** i **HTTPS Certificates**.

**2. Certyfikat z Tailscale** – 🐧 **VM**:

```bash
cd /opt/matrix/certs
sudo tailscale cert <PELNA-NAZWA-TS>
```

Wynik: `Wrote public cert to ...crt` i `Wrote private key to ...key`. Nazwy plików muszą być takie same
jak w `nginx/conf.d/matrix.conf`.

**3. Nginx** – w `nginx/conf.d/matrix.conf` zamień wszystkie wystąpienia `matrix-test.TWOJ-TAILNET.ts.net`
na `<PELNA-NAZWA-TS>` (pięć miejsc: dwa `server_name`, dwie ścieżki certyfikatu i adres w
`.well-known`). Drugi blok `server` ma **własny** `/.well-known/matrix/client` wskazujący na tę nazwę – to
ważne, bo ten z `matrix.local` jest dla telefonu nieosiągalny.

**4. Synapse (kluczowe!)** – w `synapse/homeserver.yaml` ustaw:

```yaml
public_baseurl: "https://<PELNA-NAZWA-TS>/"
```

Synapse dokleja ten adres do odpowiedzi na logowanie, a Element na telefonie przełącza się na niego.
Przy `https://matrix.local/` telefon loguje się, ale potem wisi na „Wstępna synchronizacja – czekanie
na odpowiedź serwera" (patrz [Rozwiązywanie problemów](rozwiazywanie-problemow.md)). Skutek uboczny: Element na Windowsie przy **nowym**
logowaniu też przełączy się na tę nazwę (wymaga włączonego Tailscale); zalogowane sesje się nie zmieniają.

**5. Sprawdzenie i restart** – 🐧 **VM**:

```bash
cd /opt/matrix
docker compose exec proxy nginx -t
docker compose restart proxy
docker compose restart synapse
```

`nginx -t` musi pokazać `syntax is ok` i `test is successful`. Nginx nie wstanie, jeśli plików z kroku 2
nie ma w `certs/`.

**6. Test w przeglądarce telefonu** (przed Elementem): otwórz
`https://<PELNA-NAZWA-TS>/_matrix/client/versions` – ma pokazać JSON, **bez** ostrzeżenia o certyfikacie.

**7. Element na telefonie:** zmień serwer domowy na `https://<PELNA-NAZWA-TS>` i zaloguj się loginem
z LLDAP (np. `j.kowalski`, bez `@` i bez domeny). Jeśli wcześniej logowałeś się z błędnym `public_baseurl`,
najpierw wyloguj się albo w ustawieniach Androida wyczyść dane Elementa – inaczej aplikacja zapamięta
stary adres.

**Jeszcze niesprawdzone:**

- weryfikacja nowego urządzenia w Elemencie (klucz odzyskiwania lub emotikony z drugiej sesji),
- rozmowy audio/wideo z telefonu – `turn_uris` w `homeserver.yaml` wskazują `matrix.local`, którego telefon
  nie rozwiąże; trzeba je zmienić na `<PELNA-NAZWA-TS>` (szkic: [docs/szkic-coturn-webrtc.md](szkic-coturn-webrtc.md)),
- odnawianie certyfikatu z Tailscale (ważny ok. 90 dni) – trzeba powtórzyć `tailscale cert` i zrestartować
  proxy, najlepiej w cronie.

## Komputer w innej lokalizacji (u kolegi)

> ⚠️ **Status: opisane, ale NIESPRAWDZONE w praktyce.** To jest plan krok po kroku na test „co widzi osoba
> w zupełnie innej sieci, u siebie w domu/biurze” – symulacja drugiej lokalizacji firmy. Dopisz tu wynik,
> gdy kolega faktycznie to przetestuje.

**Dlaczego to inny przypadek niż Windows w tej samej sieci:** tam komputer łączył się po
`matrix.local`, co wymagało ręcznego wpisu w pliku `hosts` i zainstalowania **własnego** Root CA (`rootCA.pem`)
jako zaufanego urzędu – to ma sens na firmowym komputerze, ale instalowanie prywatnego CA na komputerze
osoby z zewnątrz to niepotrzebne namieszanie w zaufaniu cudzego systemu. Zamiast tego używamy **tej samej
drogi co telefon wyżej** – adresu `<PELNA-NAZWA-TS>` z certyfikatem wydanym przez Tailscale (publicznie
zaufanym, przez Let's Encrypt) – **kolega NIE instaluje żadnego certyfikatu ani CA**, dzięki czemu ryzyko
i kłopot po jego stronie są minimalne.

**Co kolega musi zrobić u siebie, krok po kroku:**

1. **Założyć konto w Tailscale** (tailscale.com, może być darmowe konto osobiste – np. logowanie przez
   Google/Microsoft), jeśli jeszcze nie ma.
2. **Dostać zaproszenie do sieci (tailnetu)** – to robi administrator (Ty), nie kolega:
   - Panel Tailscale (login.tailscale.com) → **Access controls** albo wprost przy maszynie VM na liście
     **Machines** → opcja **Share** → podajesz e-mail kolegi. Kolega dostaje e-mail z linkiem, klika
     **Accept** – to udostępnia mu **tylko tę jedną maszynę** (VM), bez dołączania do reszty Twojej sieci.
   - **Niesprawdzone:** czy udostępniona w ten sposób maszyna działa identycznie jak pełne członkostwo
     w tailnecie (np. czy adres `100.x.x.x` VM wygląda tak samo po stronie kolegi), czy ruch jest
     rzeczywiście jednokierunkowy (kolega widzi VM, ale czy VM/inni mogliby zobaczyć jego komputer).
     Jeśli **Share** nie zadziała jak trzeba, alternatywa to zaproszenie kolegi jako pełnego członka
     Twojego tailnetu (ten sam ekran, zakładka **Users** → **Invite**).
3. **Zainstalować Tailscale** na swoim komputerze (tailscale.com/download) i zalogować się kontem
   z punktu 1 – zaakceptuje zaproszenie automatycznie.
4. **Sprawdzić połączenie** – w terminalu/PowerShellu kolegi:
   ```powershell
   tailscale ping <PELNA-NAZWA-TS>
   ```
   Powinno pokazać odpowiedzi (czas w ms), a nie `no response`. Jeśli nie działa – sprawdź w panelu
   Tailscale, czy maszyna kolegi faktycznie jest połączona (status **Connected**).
5. **Test w przeglądarce** (przed Elementem, tak jak w punkcie 6 wyżej): otwórz
   `https://<PELNA-NAZWA-TS>/_matrix/client/versions` – ma pokazać JSON, **bez żadnego ostrzeżenia
   o certyfikacie** (to jest ten test, który potwierdza, że certyfikat jest publicznie zaufany i kolega
   nie musi niczego instalować).
6. **Zainstalować Element Desktop** (element.io/download).
7. **Przy logowaniu** kliknij **Edytuj** przy serwerze domowym i wpisz `https://<PELNA-NAZWA-TS>`
   (NIE `matrix.local` – tego kolega nie rozwiąże, bo nie ma takiego wpisu w swoim pliku `hosts`).
8. **Zalogować się** loginem i hasłem z LLDAP. **Zalecane: użyj jednego z testowych kont z Etapu B0**
   (patrz [Przygotowanie, Etap B0](administrowanie.md#etap-b0--testowa-struktura-firmy-w-lldap), ok. 200
   fikcyjnych kont, wspólne hasło testowe) zamiast prawdziwego konta pracownika – to dane niezwiązane
   z żadną realną tożsamością, bezpieczniejsze do testu z kimś spoza zaufanego środowiska.

**Co przetestować po zalogowaniu:**

- **Wiadomości:** pokój `Firma-Ogolny` albo nowy DM z kolegi do Ciebie – podstawowy test, czy w ogóle
  wszystko działa przez prawdziwą sieć (nie LAN).
- **Rozmowa audio/wideo 1:1** – to jest kluczowy test tego scenariusza (symulacja 2. lokalizacji firmy).
  **Niesprawdzone, do zweryfikowania:**
  - czy połączenie A/V w ogóle przechodzi między dwiema różnymi sieciami przez Coturn (u nas testowane
    tylko w jednej sieci lokalnej),
  - jeśli u kolegi jest zawężony firewall/ACL (np. sieć firmowa, router korporacyjny) – Coturn
    potrzebuje portu **3478** oraz zakresu **49160–49200** na adresie Tailscale serwera (`TS_IP`), poza
    standardowym **443** dla samego Elementa. Jeśli połączenie głosowe/wideo nie działa, to pierwsze
    podejrzane miejsce.
- Kolejność zalecana: najpierw zwykłe wiadomości, dopiero potem A/V – łatwiej odróżnić, czy problem jest
  w samym połączeniu Tailscale, czy specyficznie w Coturn/WebRTC.
