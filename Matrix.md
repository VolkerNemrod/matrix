# Plan Testów (Proof of Concept) - Wdrożenie Komunikatora Matrix

## Cel 
Symulacja zamkniętego, sfederowanego komunikatora firmowego dla 3 lokalizacji. Weryfikacja działania środowiska serwerowego, integracji z usługą katalogową (AD/LDAP), komunikacji audio/wideo 1:1 oraz własnego widżetu książki adresowej w izolowanej sieci (symulowanej przez Tailscale).

---

## 1. Architektura Środowiska Testowego

*   **Host (Hub):** Maszyna Wirtualna (VM) na platformie Proxmox (np. Debian/Ubuntu).
*   **Sieć VPN (Symulacja Site-to-Site):** Tailscale zainstalowany bezpośrednio na maszynie VM oraz na komputerach klienckich.
*   **Środowisko uruchomieniowe:** Docker + Docker Compose.
*   **Klienci testowi:** Aplikacje Element Desktop na systemach Windows (Lokalny PC + Zdalny PC znajomego).

## 2. Faza 1: Przygotowanie Infrastruktury (Proxmox i Sieć)

- [ ] Utworzenie maszyny wirtualnej (VM) na Proxmoxie (min. 4GB RAM, 2 vCPU).
- [ ] Instalacja systemu Linux (Debian 12 lub Ubuntu 24.04).
- [ ] Instalacja silnika Docker oraz wtyczki Docker Compose.
- [ ] Instalacja klienta Tailscale na serwerze Linux.
- [ ] Zalogowanie serwera do sieci Tailnet i odnotowanie przypisanego adresu IP (np. `100.x.x.10`).

## 3. Faza 2: Infrastruktura Kluczy Publicznych (PKI)

- [ ] Wygenerowanie lokalnego urzędu certyfikacji (Root CA) przy użyciu narzędzia OpenSSL (`rootCA.pem`).
- [ ] Utworzenie pliku konfiguracyjnego `v3.ext` z parametrem SAN (Subject Alternative Name) dla domeny testowej, np. `matrix.twojtest.local`.
- [ ] Wygenerowanie i podpisanie certyfikatu serwera (`matrix.crt` oraz `matrix.key`) kluczem Root CA.
- [ ] Przygotowanie certyfikatu `rootCA.pem` do dystrybucji na maszyny z systemem Windows.

## 4. Faza 3: Środowisko Docker (Matrix & Usługi)

- [ ] Utworzenie struktury katalogów na serwerze (np. `/opt/matrix`).
- [ ] Przygotowanie pliku `docker-compose.yml` zawierającego 6 usług:
  1.  **Reverse Proxy** (np. Traefik / Nginx) - terminacja SSL.
  2.  **Synapse** - główny serwer komunikatora (Matrix).
  3.  **PostgreSQL** - baza danych dla Synapse.
  4.  **Coturn** - serwer STUN/TURN dla WebRTC (rozmowy A/V).
  5.  **LLDAP** - lekki serwer symulujący Active Directory.
  6.  **Nginx (Widget)** - lekki kontener serwujący plik HTML (Książka Adresowa).
- [ ] Konfiguracja `homeserver.yaml` dla Synapse:
  - Zablokowanie federacji (`federation_domain_whitelist: []`).
  - Podłączenie bazy PostgreSQL.
  - Skonfigurowanie integracji z LLDAP (moduł `matrix-synapse-ldap3`).
  - Wskazanie serwera Coturn.
- [ ] Uruchomienie środowiska poleceniem `docker compose up -d`.

## 5. Faza 4: Symulacja Bazy Pracowników i Widżet

- [ ] Zalogowanie do panelu WWW usługi LLDAP (port 17170).
- [ ] Utworzenie testowych grup/działów (np. `Zarzad`, `IT`).
- [ ] Utworzenie testowych kont użytkowników (np. `j.kowalski`, `a.nowak`) i przypisanie im haseł.
- [ ] Utworzenie statycznego pliku `index.html` (Książka Adresowa):
  - Dodanie prostego skryptu JS do filtrowania (wyszukiwarki).
  - Wygenerowanie linków w formacie: `https://matrix.to/#/@j.kowalski:matrix.twojtest.local`.
- [ ] Umieszczenie pliku `index.html` w zmapowanym wolumenie kontenera Nginx (Widget).

## 6. Faza 5: Konfiguracja Klientów (Symulacja Oddziałów)

Czynności wykonywane na komputerach testowych (Lokalny PC oraz Zdalny PC znajomego):
- [ ] Instalacja klienta Tailscale i podłączenie do sieci testowej.
- [ ] Edycja pliku `C:\Windows\System32\drivers\etc\hosts`:
  - Dodanie wpisu: `100.x.x.10 matrix.twojtest.local` (IP Tailscale serwera).
- [ ] Dodanie certyfikatu `rootCA.pem` do "Zaufanych głównych urzędów certyfikacji" w systemie Windows.
- [ ] Instalacja aplikacji Element Desktop.
- [ ] Konfiguracja Element Desktop: zmiana domyślnego serwera z `matrix.org` na `https://matrix.twojtest.local`.

## 7. Faza 6: Wykonanie Testów Funkcjonalnych (Scenariusze)

1.  **Test Uwierzytelniania:** 
    - Logowanie do aplikacji Element za pomocą danych testowych z LLDAP.
2.  **Test Komunikacji Podstawowej:** 
    - Utworzenie pokoju ogólnofirmowego (np. `#Firma-Ogolny`).
    - Wymiana wiadomości tekstowych pomiędzy dwoma testowymi komputerami (przez Tailscale).
3.  **Test Książki Adresowej (Widżet):**
    - Przypięcie aplikacji Nginx (adres HTTP z kontenera) jako widżetu do pokoju ogólnofirmowego.
    - Przetestowanie wyszukiwarki w widżecie.
    - Kliknięcie w testowe nazwisko z listy – weryfikacja czy aplikacja otwiera prywatny kanał 1:1 (Direct Message).
4.  **Test WebRTC (Rozmowy Audio/Wideo):**
    - Zainicjowanie połączenia głosowego i wideo z czatu 1:1.
    - Weryfikacja przepływu danych przez serwer Coturn (biorąc pod uwagę użycie sieci Tailscale zamiast LAN).

---
*Status testu:* Oczekuje na realizację.