# Zamysł architektury

## Cel projektu

Naszym celem jest zbudowanie systemu, który zbiera dane pogodowe i o jakości powietrza dla polskich powiatów, magazynuje je i udostępnia przez przeglądarkę. Użytkownik ma widzieć interaktywną mapę Polski, gdzie każdy powiat jest pokolorowany według wybranego wskaźnika (temperatura, wiatr, AQI itp.). Oprócz aktualnych danych, mają być dostępne prognoza na kilka godzin do przodu i historia z ostatnich dni.

## Podejście ogólne

Dzielimy system na cztery niezależne moduły:

- **Ingestion worker** – skrypt działający w tle, cyklicznie pobierający dane z API i zapisujący do bazy
- **Baza danych** – przechowuje lokalizacje powiatów, pomiary i prognozy
- **Backend API** – prosta warstwa serwująca dane z bazy do frontendu
- **Frontend** – mapa z panelem bocznym, statyczna strona HTML/JS; nginx serwuje pliki statyczne i pełni rolę reverse proxy dla zapytań do backendu

Użytkownik trafia zawsze do jednego punktu wejścia – nginx na porcie 80. Żądania pod `/api/` są transparentnie przekazywane do backendu, reszta to pliki statyczne. Worker pisze do bazy niezależnie od ruchu użytkownika.

## Źródła danych zewnętrznych

**Open-Meteo** – API pogodowe bez klucza. Odpytujemy po koordynatach GPS. Zwraca bieżące dane i prognozy godzinowe.

**AQICN (WAQI)** – API jakości powietrza, potrzebny token. Zwraca AQI i stężenia PM dla najbliższej stacji monitoringowej. Użytkownik systemu musi podać własny klucz, żeby dane były zróżnicowane geograficznie (klucz `demo` zawsze zwraca dane z tej samej stacji).

## Baza danych

PostgreSQL. Główne tabele:

- lokalizacje (koordynaty powiatów, indeks H3)
- historia pogody (pomiary godzinowe, retencja ~7 dni)
- dane smogowe (AQI, PM2.5, PM10)
- prognozy (nadpisywane przy każdym cyklu workera)

Indeksujemy po `(fk_lokalizacja, data)`, bo takie są główne zapytania.

## Środowiska

Trzy środowiska:

- **dev** – Docker Compose, wolumeny lokalne, hot-reload, logi debug
- **test** – Docker Compose, osobna baza, pytest + testy obciążeniowe Locust
- **prod** – Kubernetes (lokalnie Kind), kilka replik backendu i frontendu, PVC dla bazy

Konfiguracja przez zmienne środowiskowe (`.env` plik lokalnie, ConfigMap/Secret na k8s).

# 
