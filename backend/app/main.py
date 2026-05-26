"""
Backend API — Weather & AQI System

Logowanie:
  Poziom kontrolowany zmienną ENV: LOG_LEVEL (debug/info/warning/error).
  W docker-compose.yml dev: LOG_LEVEL=debug → pełne logi SQL + requestów.
  W prod (k8s): domyślnie info → tylko requesty i błędy.

Format logu:
  2026-05-24 22:53:37 | INFO     | backend.api      | dispatch | ← GET /api/v1/dashboard/live 200 [12.3ms]
"""

import logging
import os
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import (
    fetch_all_geographical_dim, fetch_one_geographical_dim,
    fetch_all_weather_forecast, fetch_one_weather_forecast,
    fetch_all_weather_history, fetch_one_weather_history,
    fetch_all_smog_info, fetch_one_smog_info,
    fetch_live_dashboard, fetch_localization_forecast, fetch_localization_history,
    fetch_forecast_dashboard_by_time, fetch_history_dashboard_by_time,
)


# Konfiguracja systemu logowania
def _setup_logging() -> logging.Logger:
    """
    Inicjalizuje globalny system logowania aplikacji.

    Poziom pobierany ze zmiennej środowiskowej LOG_LEVEL (domyślnie: INFO).
    Wszystkie logi kierowane na stdout - Docker / Kubernetes przechwytują je
    automatycznie i udostępniają przez `docker logs` / `kubectl logs`.

    Biblioteki zewnętrzne (uvicorn.access) są wyciszane, żeby unikać
    duplikacji logów requestów HTTP (middleware loguje je sam).
    """
    log_level_name = os.getenv("LOG_LEVEL", "info").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-28s | %(message)s"
    )
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler()],
        force=True, # nadpisuje konfig ustawiony ewentualnie przez uvicorn
    )

    # uvicorn sam loguje access logi, wyłączamy duplikaty
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)

    return logging.getLogger("backend.api")


logger = _setup_logging()


# Middleware: logowanie każdego requestu HTTP
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware rejestrujący każde żądanie HTTP wraz z kodem odpowiedzi i czasem.

    Format:
        → GET  /api/v1/dashboard/live              (DEBUG - przychodzące żądanie)
        ← GET  /api/v1/dashboard/live  200 [12.3ms] (INFO  - zakończone powodzeniem)
        ← GET  /api/v1/localizations/999  404 [2.1ms] (WARNING - błąd klienta)
        ← POST /...  500 [8.0ms] — <opis błędu>   (ERROR - błąd serwera)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        full_path = f"{path}{query}"

        logger.debug("→ %-6s %s", method, full_path)
        start = _time.monotonic()

        try:
            response = await call_next(request)
            elapsed_ms = (_time.monotonic() - start) * 1000
            status = response.status_code

            if status >= 500:
                logger.error("← %-6s %-50s %d [%.1fms]", method, full_path, status, elapsed_ms)
            elif status >= 400:
                logger.warning("← %-6s %-50s %d [%.1fms]", method, full_path, status, elapsed_ms)
            else:
                logger.info("← %-6s %-50s %d [%.1fms]", method, full_path, status, elapsed_ms)

            return response

        except Exception as exc:
            elapsed_ms = (_time.monotonic() - start) * 1000
            logger.error(
                "← %-6s %-50s 500 [%.1fms] — %s: %s",
                method, full_path, elapsed_ms, type(exc).__name__, exc,
            )
            raise


# Lifecycle: logowanie startu i zamknięcia aplikacji
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Loguje start i graceful shutdown serwera."""
    env = os.getenv("ENV", "production")
    log_level = os.getenv("LOG_LEVEL", "info").upper()
    db_host = os.getenv("DB_HOST", "db")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "weather_aqi_db")

    logger.info("=" * 60)
    logger.info("Weather & AQI API — START")
    logger.info("Środowisko : %s", env)
    logger.info("Log level  : %s", log_level)
    logger.info("Baza danych: %s:%s/%s", db_host, db_port, db_name)
    logger.info("=" * 60)

    yield  # Aplikacja działa

    logger.info("Weather & AQI API — STOP (graceful shutdown)")


# Inicjalizacja aplikacji FastAPI
app = FastAPI(
    title="Weather & AQI Big Data API",
    description="Backend produkcyjny systemu analityki przestrzennej i monitoringu środowiskowego",
    version="1.0.0",
    lifespan=lifespan,
)

# middleware: kolejność ma znaczenie, RequestLogging musi być przed CORS
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# endpointy: dashboard

@app.get("/api/v1/dashboard/live")
def get_live_metrics_dashboard():
    """
    Agreguje najświeższe metryki środowiskowe dla widoku z aktualnymi danymi.

    Zwraca zintegrowany zbiór danych zawierający aktualne parametry pogodowe,
    indeksy jakości powietrza (AQI, PM2.5, PM10) oraz współrzędne geograficzne
    wraz z indeksami H3 dla wszystkich aktywnych punktów pomiarowych.

    Zwraca:
        dict: Słownik zawierający:
            - count (int): Liczba zwróconych lokalizacji.
            - data (list[dict]): Spłaszczona struktura danych geograficzno-środowiskowych.

    Kody odpowiedzi:
        - 200 OK: Udane pobranie agregatu dla dashboardu.
    """
    data = fetch_live_dashboard()
    logger.debug("Dashboard live: zwrócono %d lokalizacji", len(data))
    return {"count": len(data), "data": data}


@app.get("/api/v1/dashboard/forecast")
def get_forecast_dashboard_by_time(
    time: datetime = Query(..., description="ISO timestamp docelowego momentu prognozy (np. 2026-05-18T12:00:00Z)")
):
    """
    WIDOK CZASOWY PROGNOZY: Zwraca stan siatki kraju (wszystkie stacje)
    zintegrowany dla konkretnej godziny w przyszłości na podstawie parametru 'time'.
    """
    logger.debug("Dashboard forecast: target_time=%s", time.isoformat())
    data = fetch_forecast_dashboard_by_time(time)
    logger.debug("Dashboard forecast: zwrócono %d lokalizacji", len(data))
    return {"count": len(data), "data": data}


@app.get("/api/v1/dashboard/history")
def get_history_dashboard_by_time(
    time: datetime = Query(..., description="ISO timestamp docelowego momentu z historii (np. 2026-05-15T14:30:00Z)")
):
    """
    WIDOK CZASOWY HISTORII: Zwraca stan siatki kraju (wszystkie stacje)
    zintegrowany dla konkretnej godziny z przeszłości na podstawie parametru 'time'.
    """
    logger.debug("Dashboard history: target_time=%s", time.isoformat())
    data = fetch_history_dashboard_by_time(time)
    logger.debug("Dashboard history: zwrócono %d lokalizacji", len(data))
    return {"count": len(data), "data": data}


# Endpointy: Lokalizacje

@app.get("/api/v1/localizations")
def get_localizations():
    """
    Zwraca spis wszystkich zarejestrowanych węzłów geograficznych.

    Punkt końcowy dedykowany do inicjalizacji komponentów mapowych oraz list
    wyboru w interfejsie użytkownika.

    Zwraca:
        list[dict]: Kolekcja obiektów reprezentujących wymiary geograficzne (ID, H3, Lon, Lat).

    Kody odpowiedzi:
        - 200 OK: Pomyślny zwrot listy lokalizacji.
    """
    return fetch_all_geographical_dim()


@app.get("/api/v1/localizations/{loc_id}")
def get_localization(loc_id: int):
    """
    Zwraca szczegółowe metadane określonego punktu pomiarowego.

    Parametry:
        loc_id (int): Identyfikator żądanej lokalizacji.

    Zwraca:
        dict: Słownik z danymi przestrzennymi wybranego węzła.

    Wyjątki:
        HTTPException (404): Podany identyfikator lokalizacji nie istnieje w bazie danych.

    Kody odpowiedzi:
        - 200 OK: Znaleziono lokalizację i zwrócono jej strukturę.
        - 404 Not Found: Brak zasobu o wskazanym ID.
    """
    data = fetch_one_geographical_dim(loc_id)
    if not data:
        logger.warning("Lokalizacja loc_id=%d nie istnieje", loc_id)
        raise HTTPException(status_code=404, detail="Localization node not found")
    return data


@app.get("/api/v1/localizations/{loc_id}/forecast")
def get_forecast_by_localization(loc_id: int):
    """
    Zwraca chronologiczną prognozę pogody dla wybranej lokalizacji.

    Agreguje dane prognostyczne (temperatura, wilgotność, wiatr, ciśnienie)
    uporządkowane rosnąco według czasu ich planowanego wystąpienia.

    Parametry:
        loc_id (int): Ścieżkowy identyfikator lokalizacji.

    Zwraca:
        list[dict]: Lista punktów czasu reprezentujących okno prognozy.

    Kody odpowiedzi:
        - 200 OK: Zwrócenie serii danych prognostycznych (może być pusta lista).
    """
    return fetch_localization_forecast(loc_id)


@app.get("/api/v1/localizations/{loc_id}/history")
def get_history_by_localization(
    loc_id: int,
    start: Optional[datetime] = Query(None, description="ISO timestamp początku zakresu (np. 2026-05-15T00:00:00Z)"),
    end: Optional[datetime] = Query(None, description="ISO timestamp końca zakresu (np. 2026-05-17T00:00:00Z)")
):
    """
    Zwraca połączone serie czasowe danych historycznych (pogoda + smog) z dynamicznym filtrowaniem.

    Punkt końcowy realizuje zapytanie łączące fakty historyczne zanieczyszczenia i meteorologii.
    Pozwala na opcjonalne zawężenie wyników za pomocą parametrów zapytania (query parameters).

    Parametry:
        loc_id (int): Ścieżkowy identyfikator lokalizacji.
        start (datetime, optional): Dolna granica filtrowania osi czasu (ISO 8601).
        end (datetime, optional): Górna granica filtrowania osi czasu (ISO 8601).

    Zwraca:
        list[dict]: Zintegrowane wpisy historyczne posortowane od najnowszych.

    Kody odpowiedzi:
        - 200 OK: Pomyślne wygenerowanie i zwrócenie historycznej osi czasu.
    """
    logger.debug(
        "Historia loc_id=%d | zakres: %s → %s",
        loc_id,
        start.isoformat() if start else "brak",
        end.isoformat() if end else "brak",
    )
    return fetch_localization_history(loc_id, start_date=start, end_date=end)


# endpointy: surowe dane (audyt ETL)

@app.get("/api/v1/raw/weather-forecasts")
def get_all_raw_forecasts():
    """
    [RAW] Zrzut danych: Pobiera kompletną zawartość tabeli faktów WeatherForecast.

    Zwraca:
        list[dict]: Surowe rekordy bazy danych bez odfiltrowywania okien czasowych.
    """
    return fetch_all_weather_forecast()


@app.get("/api/v1/raw/weather-forecasts/{id}")
def get_one_raw_forecast(id: int):
    """
    [RAW] Pobiera pojedynczy rekord prognozy bezpośrednio po jego kluczu głównym.

    Parametry:
        id (int): ID rekordu prognozy (id_forecast).

    Wyjątki:
        HTTPException (404): Brak rekordu prognozy o podanym identyfikatorze.
    """
    data = fetch_one_weather_forecast(id)
    if not data:
        logger.warning("[RAW] Prognoza id=%d nie istnieje", id)
        raise HTTPException(status_code=404, detail="Forecast record not found")
    return data


@app.get("/api/v1/raw/weather-histories")
def get_all_raw_histories():
    """
    [RAW] Zrzut danych: Pobiera kompletną zawartość tabeli WeatherHistory_Fact.

    Zwraca:
        list[dict]: Pełna historia pomiarów meteorologicznych zapisana w systemie.
    """
    return fetch_all_weather_history()


@app.get("/api/v1/raw/weather-histories/{id}")
def get_one_raw_history(id: int):
    """
    [RAW] Pobiera pojedynczy rekord historii pogody bezpośrednio po jego kluczu głównym.

    Parametry:
        id (int): ID rekordu historycznego (id_history).

    Wyjątki:
        HTTPException (404): Brak rekordu historii o podanym identyfikatorze.
    """
    data = fetch_one_weather_history(id)
    if not data:
        logger.warning("[RAW] Historia id=%d nie istnieje", id)
        raise HTTPException(status_code=404, detail="History fact record not found")
    return data


@app.get("/api/v1/raw/smog-infos")
def get_all_raw_smogs():
    """
    [RAW] Zrzut danych: Pobiera kompletną zawartość tabeli SmogInfo.

    Zwraca:
        list[dict]: Wszystkie historyczne i bieżące rekordy dotyczące stężeń zanieczyszczeń powietrza.
    """
    return fetch_all_smog_info()


@app.get("/api/v1/raw/smog-infos/{id}")
def get_one_raw_smog(id: int):
    """
    [RAW] Pobiera pojedynczy rekord zanieczyszczenia powietrza bezpośrednio po jego kluczu głównym.

    Parametry:
        id (int): ID rekordu smogowego (id_smog).

    Wyjątki:
        HTTPException (404): Brak rekordu smogu o podanym identyfikatorze.
    """
    data = fetch_one_smog_info(id)
    if not data:
        logger.warning("[RAW] SmogInfo id=%d nie istnieje", id)
        raise HTTPException(status_code=404, detail="Smog info record not found")
    return data