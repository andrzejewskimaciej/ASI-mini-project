# System Prognozowania Pogody i Jakości Powietrza (Weather & AQI System)



System zbiera, przetwarza i wizualizuje dane pogodowe oraz informacje o jakości powietrza (smogu) dla powiatów w Polsce. Dane pobierane są równolegle z zewnętrznych interfejsów Open Data, zapisywane w relacyjnej bazie danych PostgreSQL, a następnie wystawiane przez wysokowydajne REST API (FastAPI) i prezentowane użytkownikowi na interaktywnej mapie.

---

## Konfiguracja Jakości Powietrza (AQI)

Moduł pobierania danych o smogu łączy się z zewnętrznym serwisem **AQICN (WAQI)**. Domyślnie w konfiguracji używany jest publiczny klucz `demo` (`AQICN_TOKEN=demo`). Serwer AQICN przy użyciu klucza `demo` ignoruje współrzędne geograficzne i zwraca dane ze stacji najbliższej adresowi IP, z którego przychodzi żądanie (powodując, że we wszystkich powiatach w bazie pojawia się identyczna wartość).

Aby aktywować pobieranie rzeczywistych, lokalnych danych dla każdego powiatu z osobna:

1. Zarejestruj się bezpłatnie na stronie [AQICN Data Platform](https://aqicn.org/data-platform/token/).
2. Skopiuj wygenerowany API Token.
3. Wpisz go jako wartość `AQICN_TOKEN` w pliku `.env.dev` (dla Docker Compose) lub w pliku [k8s/configmap.yml](file:///e:/Do%20gita/asi-mini-project-raw/k8s/configmap.yml) w sekcji `data` (dla Kubernetes).

---

## Instrukcja Uruchomienia Środowisk

### A. Środowisko Deweloperskie (Development) — Docker Compose

Środowisko dev wspiera **hot-reload** (zmiany w kodzie backendu i frontendu są widoczne natychmiast bez konieczności przebudowywania obrazów) dzięki podmontowanym wolumenom lokalnym.

```bash
# Uruchomienie wszystkich serwisów w trybie dev (baza, backend, worker, nginx)
docker compose -f docker-compose.dev.yml up --build
```

* **Frontend**: [http://localhost:8080](http://localhost:8080)
* **Backend API / Swagger**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Baza PostgreSQL**: Port `5432` jest wystawiony na hosta (użytkownik: `user`, hasło: `password`, baza: `weather_aqi_db`).

---

### B. Środowisko Testowe (Test) — Docker Compose Profiles

Środowisko testowe uruchamia bazę w pamięci RAM (`tmpfs`), co znacznie przyspiesza testy i nie zaśmieca dysku.

#### 1. Testy Jednostkowe (Unit Tests)

Uruchamia testy jednostkowe dla backendu (`pytest`) oraz workera ingestion, generując raporty JUnit XML w katalogu `./reports/`.

```bash
docker compose -f docker-compose.test.yml --profile unit up --build --abort-on-container-exit
```

#### 2. Testy Wydajnościowe (Performance/Load Tests)

Dostępne są 3 oddzielne profile obciążeniowe (odzwierciedlające lekkie, średnie i wysokie obciążenie):

* **Lekkie obciążenie (Light)** — 50 jednoczesnych użytkowników, narastanie 5/s, czas 90s:
  
  ```bash
  docker compose -f docker-compose.test.yml --profile perf up --build --abort-on-container-exit
  ```
  
  Raport HTML zostanie zapisany w: `./reports/perf-report.html`.

* **Średnie obciążenie (Medium)** — 200 jednoczesnych użytkowników, narastanie 20/s, czas 60s:
  
  ```bash
  docker compose -f docker-compose.test.yml --profile perf-medium up --build --abort-on-container-exit
  ```
  
  Raport HTML zostanie zapisany w: `./reports/perf-report-medium.html`.

* **Wysokie obciążenie (Heavy)** — 500 jednoczesnych użytkowników, narastanie 50/s, czas 60s:
  
  ```bash
  docker compose -f docker-compose.test.yml --profile perf-heavy up --build --abort-on-container-exit
  ```
  
  Raport HTML zostanie zapisany w: `./reports/perf-report-heavy.html`.

---

### C. Środowisko Produkcyjne (Production) — Kubernetes (Kind)

Środowisko produkcyjne odzwierciedla w pełni architekturę chmurową o wysokiej niezawodności przy użyciu lokalnego klastra Kubernetes (Kind).

#### Wymagania:

* Zainstalowany **Docker Desktop**
* Narzędzia **kind**, **kubectl**
* Skrypt uruchamiający wymaga systemu Windows (PowerShell)

#### Wdrożenie na klastrze:

Skrypt automatycznie tworzy klaster Kind, konfiguruje mapowanie portów (host `80` -> ingress), buduje produkcyjne obrazy Docker, ładuje je do klastra i wdraża zasoby w przestrzeni nazw `weather-prod`.

```powershell
# Uruchomienie skryptu deploymentu (z głównego folderu projektu)
.\k8s\deploy.ps1
```

Zasoby wdrożone w klastrze:

* **Namespace**: `weather-prod`
* **Database**: Stateful PostgreSQL z persistent volume (PVC) na dane
* **Secrets & ConfigMaps**: Bezpieczne oddzielenie konfiguracji od kodu
* **Backend**: Skalowany deployment FastAPI z livenessProbe
* **Ingestion**: Pojedynczy replikowany worker pobierający dane w tle
* **Frontend**: Serwer Nginx z wbudowanymi plikami statycznymi (ze statycznym gzipem i buforowaniem cache).

Dostęp do aplikacji po wdrożeniu: [http://localhost](http://localhost) (port 80).
