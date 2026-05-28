# Testy

## Struktura

Testy podzielone na dwa zestawy - jednostkowe (pytest) i wydajnościowe (Locust). Wszystkie działają w Docker Compose, w celu uniknięcia lokalnej instalacji zależności.

```
backend/app/test_backend.py   - testy backendu (FastAPI)
ingestion/test_app.py         - testy workera ingestion
reports/                      - wyniki testów (XML JUnit + HTML Locust)
```

---

## Testy jednostkowe (pytest)

Uruchamiane w izolowanym środowisku - baza danych testowa trzymana w pamięci RAM (`tmpfs`), brak realnych połączeń z zewnętrznymi API (wszystko mockowane).

### Jak uruchomić

```bash
docker compose -f docker-compose.test.yml --profile unit up --build --abort-on-container-exit
```

Wyniki JUnit XML zapisywane do `reports/`.

---

### Backend (`test_backend.py`)

Testuje endpointy FastAPI przez `TestClient`. Warstwa bazodanowa jest mockowana przez `unittest.mock.patch`.

| Test                                            | Co sprawdza                                            |
| ----------------------------------------------- | ------------------------------------------------------ |
| `test_get_live_metrics_dashboard_success`       | GET /dashboard/live zwraca 200, poprawne pola JSON     |
| `test_get_localizations_all`                    | GET /localizations zwraca listę                        |
| `test_get_localization_by_id_success`           | GET /localizations/{id} zwraca 200 i poprawny h3_index |
| `test_get_localization_by_id_not_found`         | GET /localizations/999 zwraca 404                      |
| `test_get_forecast_by_localization_success`     | GET /localizations/{id}/forecast zwraca 200            |
| `test_get_history_by_localization_with_filters` | przekazanie parametrów start/end jako datetime         |
| `test_get_one_raw_forecast_not_found`           | GET /raw/weather-forecasts/999 → 404                   |
| `test_get_one_raw_history_not_found`            | GET /raw/weather-histories/999 → 404                   |
| `test_get_one_raw_smog_not_found`               | GET /raw/smog-infos/999 → 404                          |

---

### Ingestion Worker (`test_app.py`)

Testuje logikę workera bez realnych połączeń do bazy i API.

| Test                                               | Co sprawdza                                               |
| -------------------------------------------------- | --------------------------------------------------------- |
| `test_cleanup_old_data_success`                    | 2x DELETE + commit + zamknięcie kursorów                  |
| `test_cleanup_old_data_rollback_on_exception`      | rollback przy błędzie DB, brak commit                     |
| `test_fetch_weather_and_smog_no_work`              | short-circuit gdy brak przestarzałych lokalizacji → False |
| `test_fetch_weather_and_smog_api_timeout_handling` | rollback przy timeout API, wynik True (pętla kontynuuje)  |

---

## Testy wydajnościowe (Locust)

Testy obciążeniowe generują ruch HTTP na backend i mierzą czasy odpowiedzi, throughput i error rate.

### Jak uruchomić

**Lekki profil (szybki smoke test):**

```bash
docker compose -f docker-compose.test.yml --profile perf up --build --abort-on-container-exit
```

**Średni profil:**

```bash
docker compose -f docker-compose.test.yml --profile perf-medium up --build --abort-on-container-exit
```

**Ciężki profil:**

```bash
docker compose -f docker-compose.test.yml --profile perf-heavy up --build --abort-on-container-exit
```

Raport HTML zapisywany do `reports/locust_report.html`.

---

## Wyniki

Wyniki testów jednostkowych i wydajnościowych trafiają do katalogu `reports/`.
