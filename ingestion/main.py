"""
Ingestion Worker — Weather & AQI System

Pobiera dane z zewnętrznych API równolegle i zapisuje je do bazy PostgreSQL.

Współbieżność:
  ThreadPoolExecutor z MAX_WORKERS wątkami (domyślnie 5).
  Każdy wątek zarządza własnym połączeniem DB — thread-safe.
  HTTP calls (requests) są I/O-bound → wątki dają duże przyspieszenie.

Konfiguracja:
  INGESTION_WORKERS — liczba równoległych wątków (env var, default: 5)
  LOG_LEVEL         — poziom logowania (debug/info/warning/error, default: info)

Szacowany czas cyklu (~380 lokalizacji):
  Sekwencyjnie: ~7-8 min
  5 wątków:     ~1.5-2 min
  10 wątków:    ~50-70 sek
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import psycopg2
import requests
from psycopg2.extras import execute_values

# zmienne połączenia z bazą
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "weather_aqi_db")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")

MAX_WORKERS = int(os.getenv("INGESTION_WORKERS", "5"))

# token 'demo' ignoruje koordynaty, zwraca tę samą stację dla całego kraju
AQICN_TOKEN = os.getenv("AQICN_TOKEN", "demo")


def _setup_logging() -> logging.Logger:
    """
    Konfiguruje system logowania dla serwisu ingestion.

    Poziom pobierany ze zmiennej środowiskowej LOG_LEVEL (domyślnie: INFO).
    Logi kierowane na stdout - Docker / Kubernetes przechwytuje je przez
    `docker logs` / `kubectl logs -n weather-prod deployment/ingestion`.
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
        force=True,
    )
    # wyciszamy szum logów z requests/urllib3
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return logging.getLogger("ingestion")


logger = _setup_logging()


def get_db_connection():
    """
    Tworzy połączenie z PostgreSQL używając domyślnego kursora (tuple-based).

    Wywołanie jest thread-safe — każdy wątek tworzy własną instancję połączenia.

    Zwraca:
        psycopg2.extensions.connection: Aktywny obiekt połączenia.

    Wyjątki:
        psycopg2.OperationalError: Loguje szczegóły przed re-raise.
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
        )
        logger.debug("Połączono z bazą: %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
        return conn
    except psycopg2.OperationalError as exc:
        logger.error("Błąd połączenia z bazą %s:%s/%s — %s", DB_HOST, DB_PORT, DB_NAME, exc)
        raise


def cleanup_old_data():
    """
    Usuwa dane starsze niż 7 dni na podstawie czasu pomiaru (measurement_date).

    Realizuje politykę retencji danych: system przechowuje tylko tydzień historii,
    co zapobiega nieograniczonemu wzrostowi rozmiaru bazy danych.
    """
    logger.info("Czyszczenie starych danych (retencja 7 dni)...")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        granica_wieku = datetime.now() - timedelta(days=7)
        logger.debug("Usuwanie rekordów starszych niż: %s", granica_wieku.isoformat())

        cursor.execute(
            "DELETE FROM WeatherHistory_Fact WHERE measurement_date < %s;",
            (granica_wieku,),
        )
        deleted_weather = cursor.rowcount

        cursor.execute(
            "DELETE FROM SmogInfo WHERE measurement_date < %s;",
            (granica_wieku,),
        )
        deleted_smog = cursor.rowcount

        conn.commit()
        logger.info(
            "Czyszczenie zakończone — usunięto: WeatherHistory=%d, SmogInfo=%d",
            deleted_weather, deleted_smog,
        )
    except Exception as exc:
        conn.rollback()
        logger.error("Błąd podczas czyszczenia danych (rollback): %s", exc)
    finally:
        cursor.close()
        conn.close()


def get_stale_localizations():
    """
    Zwraca lokalizacje, które wymagają przeładowania (starsze niż 50 minut lub brak danych).

    Analiza opiera się na datach ostatniej aktualizacji aktywnego rekordu (is_current = TRUE).

    Zwraca:
        list[tuple]: Lista krotek (id_localization, latitude, longitude).
    """
    logger.debug("Szukanie lokalizacji wymagających odświeżenia...")
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT g.id_localization, g.latitude, g.longitude
        FROM Geographical_Dim g
        LEFT JOIN WeatherHistory_Fact w ON g.id_localization = w.fk_localization AND w.is_current = TRUE
        LEFT JOIN SmogInfo s ON g.id_localization = s.fk_localization AND s.is_current = TRUE
        WHERE
            w.last_update_date IS NULL OR w.last_update_date < NOW() - INTERVAL '50 minutes'
            OR
            s.last_update_date IS NULL OR s.last_update_date < NOW() - INTERVAL '50 minutes'
        ORDER BY COALESCE(w.last_update_date, s.last_update_date) ASC NULLS FIRST;
    """
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    except Exception as exc:
        logger.error("Błąd podczas pobierania listy lokalizacji do odświeżenia: %s", exc)
        rows = []
    finally:
        cursor.close()
        conn.close()

    logger.debug("Znaleziono %d lokalizacji wymagających odświeżenia", len(rows))
    return rows


def _process_location(loc_id: int, lat: float, lon: float) -> dict:
    """
    Przetwarza JEDNĄ lokalizację: pobiera dane pogodowe i smogowe, zapisuje do DB.

    Funkcja jest zaprojektowana do wywoływania w osobnym wątku przez ThreadPoolExecutor.
    Każde wywołanie tworzy własne, niezależne połączenie z bazą danych.

    Parametry:
        loc_id (int): Identyfikator lokalizacji z tabeli Geographical_Dim.
        lat (float): Szerokość geograficzna.
        lon (float): Długość geograficzna.

    Zwraca:
        dict: Wynik przetwarzania:
            - {"loc_id": int, "status": "ok"}              — sukces
            - {"loc_id": int, "status": "error", "msg": str} — błąd
    """
    logger.debug("Wątek START loc_id=%d (lat=%.4f, lon=%.4f)", loc_id, lat, lon)
    t_start = time.monotonic()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # open-meteo: dane bieżące i prognoza, dodajemy wind_speed_unit=ms dla m/s
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure"
            f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure"
            f"&forecast_hours=24"
            f"&forecast_days=2"
            f"&wind_speed_unit=ms"
        )
        logger.debug("Open-Meteo request: loc_id=%d", loc_id)

        t_w = time.monotonic()
        w_res = requests.get(weather_url, timeout=10).json()
        logger.debug("Open-Meteo response: loc_id=%d [%.0fms]", loc_id, (time.monotonic() - t_w) * 1000)

        current = w_res.get("current", {})
        current_time = current.get("time")
        temp  = current.get("temperature_2m")
        hum   = current.get("relative_humidity_2m")
        wind  = current.get("wind_speed_10m")
        press = current.get("surface_pressure")

        if current_time:
            logger.debug(
                "Pogoda loc_id=%d: t=%.1f°C h=%.0f%% w=%.1fm/s p=%.0fhPa @ %s",
                loc_id, temp or 0, hum or 0, wind or 0, press or 0, current_time,
            )
            # upsert bieżącego pomiaru
            cursor.execute("""
                INSERT INTO WeatherHistory_Fact
                    (fk_localization, measurement_date, temperature, humidity, wind_speed, pressure, is_current, last_update_date)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (fk_localization, measurement_date) DO UPDATE
                SET temperature=EXCLUDED.temperature, humidity=EXCLUDED.humidity,
                    wind_speed=EXCLUDED.wind_speed, pressure=EXCLUDED.pressure,
                    is_current=TRUE, last_update_date=CURRENT_TIMESTAMP;
            """, (loc_id, current_time, temp, hum, wind, press))

            # starsze rekordy tej lokalizacji tracą flagę is_current
            cursor.execute("""
                UPDATE WeatherHistory_Fact
                SET is_current = FALSE
                WHERE fk_localization = %s AND measurement_date != %s;
            """, (loc_id, current_time))

        # pierwsze 24h prognozy godzinowej
        hourly = w_res.get("hourly", {})
        forecast_times = hourly.get("time", [])[:24]
        # guard na wypadek niekompletnej odpowiedzi API
        h_temp  = hourly.get("temperature_2m") or []
        h_hum   = hourly.get("relative_humidity_2m") or []
        h_wind  = hourly.get("wind_speed_10m") or []
        h_press = hourly.get("surface_pressure") or []
        forecast_data = [
            (
                loc_id, f_time,
                h_temp[i]  if i < len(h_temp)  else None,
                h_hum[i]   if i < len(h_hum)   else None,
                h_wind[i]  if i < len(h_wind)  else None,
                h_press[i] if i < len(h_press) else None,
            )
            for i, f_time in enumerate(forecast_times)
        ]
        logger.debug("Prognoza loc_id=%d: %d punktów czasowych", loc_id, len(forecast_data))

        execute_values(cursor, """
            INSERT INTO WeatherForecast
                (fk_localization, forecast_date, temperature, humidity, wind_speed, pressure)
            VALUES %s
            ON CONFLICT (fk_localization, forecast_date) DO UPDATE
            SET temperature=EXCLUDED.temperature, humidity=EXCLUDED.humidity,
                wind_speed=EXCLUDED.wind_speed, pressure=EXCLUDED.pressure,
                load_date=CURRENT_TIMESTAMP;
        """, forecast_data)

        # 2. AQICN: jakość powietrza
        smog_url = f"https://api.waqi.info/feed/geo:{lat};{lon}/?token={AQICN_TOKEN}"
        logger.debug("AQICN request: loc_id=%d", loc_id)

        t_s = time.monotonic()
        s_res = requests.get(smog_url, timeout=10).json()
        logger.debug("AQICN response: loc_id=%d status=%s [%.0fms]",
                     loc_id, s_res.get("status"), (time.monotonic() - t_s) * 1000)

        if s_res.get("status") == "ok":
            data  = s_res.get("data", {})
            aqi   = data.get("aqi")
            iaqi  = data.get("iaqi", {})
            pm25  = iaqi.get("pm25", {}).get("v")
            pm10  = iaqi.get("pm10", {}).get("v")
            s_time = data.get("time", {}).get("iso")

            if aqi is not None and s_time:
                logger.debug(
                    "Smog loc_id=%d: AQI=%s PM2.5=%s PM10=%s @ %s",
                    loc_id, aqi, pm25, pm10, s_time,
                )
                cursor.execute("""
                    INSERT INTO SmogInfo
                        (fk_localization, measurement_date, aqi, pm25, pm10, is_current, load_date, last_update_date)
                    VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (fk_localization, measurement_date) DO UPDATE
                    SET aqi=EXCLUDED.aqi, pm25=EXCLUDED.pm25, pm10=EXCLUDED.pm10,
                        is_current=TRUE, last_update_date=CURRENT_TIMESTAMP;
                """, (loc_id, s_time, aqi, pm25, pm10))

                cursor.execute("""
                    UPDATE SmogInfo
                    SET is_current = FALSE
                    WHERE fk_localization = %s AND measurement_date != %s;
                """, (loc_id, s_time))
            else:
                logger.debug("Smog loc_id=%d: brak kompletnych danych AQI", loc_id)
        else:
            logger.debug("AQICN loc_id=%d — status=%s (brak danych)", loc_id, s_res.get("status"))

        conn.commit()
        elapsed_total = (time.monotonic() - t_start) * 1000
        logger.debug("Wątek END loc_id=%d [%.0fms łącznie]", loc_id, elapsed_total)
        return {"loc_id": loc_id, "status": "ok"}

    except requests.exceptions.Timeout:
        conn.rollback()
        logger.warning("Timeout API loc_id=%d — pomijam (ponowna próba w następnym cyklu)", loc_id)
        return {"loc_id": loc_id, "status": "error", "msg": "API timeout"}

    except requests.exceptions.RequestException as exc:
        conn.rollback()
        logger.warning("Błąd sieciowy loc_id=%d — %s: %s", loc_id, type(exc).__name__, exc)
        return {"loc_id": loc_id, "status": "error", "msg": str(exc)}

    except Exception as exc:
        conn.rollback()
        logger.error("Nieoczekiwany błąd loc_id=%d (rollback) — %s: %s", loc_id, type(exc).__name__, exc)
        return {"loc_id": loc_id, "status": "error", "msg": str(exc)}

    finally:
        cursor.close()
        conn.close()


def fetch_weather_and_smog():
    """
    Główna pętla ingestion: równolegle pobiera dane dla wszystkich przestarzałych lokalizacji.

    Używa ThreadPoolExecutor z MAX_WORKERS wątkami (konfigurowane przez INGESTION_WORKERS).
    Każdy wątek wywołuje _process_location() — niezależne połączenie DB, izolacja błędów.

    Szacowany czas (380 lokalizacji):
        1 wątek  → ~7-8 min
        5 wątków → ~1.5-2 min
        10 wątków→ ~50-70 sek

    Zwraca:
        bool: True jeśli przetworzono przynajmniej jedną lokalizację, False jeśli nic do zrobienia.
    """
    localizations = get_stale_localizations()

    if not localizations:
        return False

    total = len(localizations)
    logger.info(
        "Odświeżanie danych: %d lokalizacji | %d wątków (INGESTION_WORKERS=%d)",
        total, MAX_WORKERS, MAX_WORKERS,
    )
    t_batch_start = time.monotonic()
    success_count = 0
    error_count = 0
    done_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # przesyłamy wszystkie zadania naraz, executor sam kolejkuje
        future_to_loc = {
            executor.submit(_process_location, loc_id, lat, lon): loc_id
            for loc_id, lat, lon in localizations
        }

        # zbieramy wyniki w miarę kończenia, nie czekając na wszystkie
        for future in as_completed(future_to_loc):
            done_count += 1
            try:
                result = future.result()
                if result["status"] == "ok":
                    success_count += 1
                    logger.info(
                        "OK   loc_id=%-5d [%d/%d] (sukces: %d, błędy: %d)",
                        result["loc_id"], done_count, total, success_count, error_count,
                    )
                else:
                    error_count += 1
                    logger.warning(
                        "ERR  loc_id=%-5d [%d/%d] — %s",
                        result["loc_id"], done_count, total, result.get("msg", ""),
                    )
            except Exception as exc:
                # wyjątek z Future, nie z _process_location — rzadki przypadek
                loc_id = future_to_loc[future]
                error_count += 1
                logger.error("Future exception loc_id=%d — %s", loc_id, exc)

    elapsed_batch_s = time.monotonic() - t_batch_start
    logger.info(
        "Seria zakończona — sukces: %d, błędy: %d, czas: %.1fs (%.1f lok/s)",
        success_count, error_count, elapsed_batch_s, total / elapsed_batch_s if elapsed_batch_s > 0 else 0,
    )
    return True


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Ingestion Worker — START")
    logger.info("Baza:     %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
    logger.info("Środow.:  %s", os.getenv("ENV", "production"))
    logger.info("Wątki:    %d (INGESTION_WORKERS)", MAX_WORKERS)
    logger.info("=" * 60)

    cleanup_old_data()
    ostatnie_czyszczenie = datetime.now()

    logger.info("Wchodzę w główną pętlę (interwał odświeżania: ~50 min / lokalizację)")

    while True:
        # raz na dobę czyścimy stare dane
        if datetime.now() - ostatnie_czyszczenie > timedelta(days=1):
            cleanup_old_data()
            ostatnie_czyszczenie = datetime.now()

        had_work = fetch_weather_and_smog()

        if not had_work:
            logger.debug("Wszystkie lokalizacje świeże (< 50 min) — czekam 60s")
            time.sleep(60)
        else:
            time.sleep(1)