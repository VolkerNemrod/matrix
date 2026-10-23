# Integracja z prawdziwym Active Directory

> Część dokumentacji projektu Matrix PoC. Ten plik zbiera to, co dotyczy przejścia z LLDAP (symulacja
> na PoC) na prawdziwe Active Directory w wdrożeniu produkcyjnym.

## Logowanie przez LDAP

Na PoC logowanie idzie przez LLDAP (moduł `matrix-synapse-ldap3` w Synapse, konfiguracja w
`synapse/homeserver.yaml`). Przejście na prawdziwe AD to w zasadzie zmiana adresu serwera LDAP, bazy
wyszukiwania (`base_dn`) i atrybutu loginu w konfiguracji tego samego modułu – mechanizm logowania
się nie zmienia. Szczegóły konfiguracji modułu zostają jak w `synapse/homeserver.yaml.example`.

## Książka adresowa: źródło danych z AD zamiast CSV

W wersji produkcyjnej stanowisko, telefon, pokój i piętro mogą pochodzić z Active Directory (atrybuty
`title`, `telephoneNumber`, `physicalDeliveryOfficeName`) – odczyt z AD zastąpi plik
`directory_extra.csv`, który na PoC wypełnia te same pola ręcznie. LLDAP (użyty na PoC do symulacji AD)
tych atrybutów nie ma, stąd rozwiązanie przez CSV.

**Aktualizacja.** Skrypt `setup_directory.py` działa na żądanie. Po zmianach w AD uruchamiaj go po
`provision_synapse_users.py`, najlepiej cyklicznie (cron na serwerze), zamiast ręcznie edytować CSV.

## Partnerzy (firmy zewnętrzne)

Sposób importu kont partnerskich firm (np. z CSV albo osobnego źródła, nie z głównego AD) i to, czy ich
pracownicy mają widzieć całą książkę adresową firmy, nie jest zdecydowane – do ustalenia przed
wdrożeniem produkcyjnym z udziałem partnerów zewnętrznych.
