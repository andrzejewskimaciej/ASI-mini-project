"""
Warstwa dostępu do danych (DAL) — Weather & AQI System

Logowanie:
  Logger: 'backend.database' (dziedziczy konfigurację z main.py)
  DEBUG — czas wykonania zapytania SQL, liczba pobranych wierszy
  ERROR — błędy połączenia z bazą danych

Wszystkie zapytania SQL mierzone są w milisekundach.
Przy LOG_LEVEL=debug w logach pojawią się szczegóły każdego zapytania.
"""

import logging
import os
import time as _time
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("backend.database")

# połączenie z bazą — parametry z env
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "weather_aqi_db")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")


def get_db_connection():
    """
    Inicjalizuje synchroniczne połączenie z bazą danych PostgreSQL.

    Wykorzystuje fabrykę kursorów `RealDictCursor`, zmieniając domyślny format
    zwracanych danych z krotek (tuples) na słowniki Pythona (klucz-wartość),
    gdzie kluczem jest nazwa kolumny w bazie danych. Ułatwia to mapowanie
    danych na format JSON w API.

    Zwraca:
        psycopg2.extensions.connection: Aktywny obiekt połączenia relacyjnego.

    Wyjątki:
        psycopg2.OperationalError: Loguje szczegóły błędu.
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            cursor_factory=RealDictCursor,
        )
        logger.debug("Połączono z bazą: %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
        return conn
    except psycopg2.OperationalError as exc:
        logger.error(
            "Błąd połączenia z bazą %s:%s/%s — %s", DB_HOST, DB_PORT, DB_NAME, exc
        )
        raise


def _exec(cur, query: str, params=None) -> float:
    """
    Wykonuje zapytanie SQL i zwraca czas wykonania w milisekundach.

    Loguje czas wykonania na poziomie DEBUG. Przy LOG_LEVEL=info i wyżej
    logi SQL są niewidoczne.

    Parametry:
        cur: Kursor psycopg2 (RealDictCursor).
        query (str): Treść zapytania SQL.
        params: Opcjonalne parametry zapytania (tuple lub dict).

    Zwraca:
        float: Czas wykonania zapytania w milisekundach.
    """
    start = _time.monotonic()
    cur.execute(query, params)
    elapsed_ms = (_time.monotonic() - start) * 1000
    logger.debug("SQL [%.1fms]", elapsed_ms)
    return elapsed_ms


# wymiar geograficzny

def fetch_all_geographical_dim():
    """
    Pobiera pełny zestaw danych z tabeli wymiaru geograficznego.

    Wykorzystywane do ładowania wszystkich punktów pomiarowych systemu.

    Zwraca:
        list[dict]: Lista słowników zawierających klucze: id_localization,
                    h3_index, longitude, latitude, last_update_date.
    """
    logger.debug("Pobieranie wszystkich lokalizacji geograficznych")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(
                cur,
                "SELECT id_localization, h3_index, longitude, latitude, last_update_date "
                "FROM Geographical_Dim;",
            )
            rows = cur.fetchall()
    logger.debug("Pobrano %d lokalizacji [%.1fms]", len(rows), elapsed)
    return rows


def fetch_one_geographical_dim(loc_id: int):
    """
    Pobiera metadane pojedynczego punktu geograficznego na podstawie identyfikatora.

    Parametry:
        loc_id (int): Unikalny identyfikator lokalizacji (id_localization).

    Zwraca:
        dict | None: Słownik z danymi lokalizacji lub None, jeśli rekord nie istnieje.
    """
    logger.debug("Pobieranie lokalizacji loc_id=%d", loc_id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _exec(
                cur,
                "SELECT id_localization, h3_index, longitude, latitude, last_update_date "
                "FROM Geographical_Dim WHERE id_localization = %s;",
                (loc_id,),
            )
            row = cur.fetchone()
    if row is None:
        logger.debug("Lokalizacja loc_id=%d nie znaleziona", loc_id)
    return row


# prognozy pogody

def fetch_all_weather_forecast():
    """
    Pobiera wszystkie rekordy prognoz pogody zapisane w systemie (zrzut surowy).

    Zwraca:
        list[dict]: Lista słowników reprezentujących surowe rekordy tabeli WeatherForecast.
    """
    logger.debug("[RAW] Pobieranie wszystkich prognoz pogody")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(
                cur,
                "SELECT id_forecast, fk_localization, forecast_date, temperature, "
                "humidity, wind_speed, pressure, load_date FROM WeatherForecast;",
            )
            rows = cur.fetchall()
    logger.debug("[RAW] Pobrano %d prognoz [%.1fms]", len(rows), elapsed)
    return rows


def fetch_one_weather_forecast(forecast_id: int):
    """
    Pobiera pojedynczy rekord prognozy pogody na podstawie klucza głównego.

    Parametry:
        forecast_id (int): Unikalny identyfikator prognozy (id_forecast).

    Zwraca:
        dict | None: Słownik z danymi prognozy lub None w przypadku braku pasującego rekordu.
    """
    logger.debug("[RAW] Pobieranie prognozy id=%d", forecast_id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _exec(
                cur,
                "SELECT id_forecast, fk_localization, forecast_date, temperature, "
                "humidity, wind_speed, pressure, load_date "
                "FROM WeatherForecast WHERE id_forecast = %s;",
                (forecast_id,),
            )
            return cur.fetchone()


# historia pogody

def fetch_all_weather_history():
    """
    Pobiera wszystkie surowe wpisy z tabeli faktów historii pogody (WeatherHistory_Fact).

    Zwraca:
        list[dict]: Lista słowników reprezentujących historyczne punkty pomiarowe pogody.
    """
    logger.debug("[RAW] Pobieranie całej historii pogody")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(
                cur,
                "SELECT id_history, fk_localization, measurement_date, temperature, "
                "humidity, wind_speed, pressure, last_update_date, is_current "
                "FROM WeatherHistory_Fact;",
            )
            rows = cur.fetchall()
    logger.debug("[RAW] Pobrano %d rekordów historii pogody [%.1fms]", len(rows), elapsed)
    return rows


def fetch_one_weather_history(history_id: int):
    """
    Pobiera pojedynczy historyczny fakt pogodowy na podstawie klucza głównego.

    Parametry:
        history_id (int): Unikalny identyfikator rekordu historii (id_history).

    Zwraca:
        dict | None: Słownik z danymi historycznymi pogody lub None.
    """
    logger.debug("[RAW] Pobieranie historii pogody id=%d", history_id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _exec(
                cur,
                "SELECT id_history, fk_localization, measurement_date, temperature, "
                "humidity, wind_speed, pressure, last_update_date, is_current "
                "FROM WeatherHistory_Fact WHERE id_history = %s;",
                (history_id,),
            )
            return cur.fetchone()


# smog / jakość powietrza

def fetch_all_smog_info():
    """
    Pobiera wszystkie surowe wpisy z tabeli faktów dotyczących zanieczyszczenia powietrza (SmogInfo).

    Zwraca:
        list[dict]: Lista rekordów zawierających indeksy AQI, PM2.5 oraz PM10.
    """
    logger.debug("[RAW] Pobieranie wszystkich danych smogowych")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(
                cur,
                "SELECT id_smog, fk_localization, measurement_date, aqi, pm25, pm10, "
                "load_date, last_update_date, is_current FROM SmogInfo;",
            )
            rows = cur.fetchall()
    logger.debug("[RAW] Pobrano %d rekordów smogowych [%.1fms]", len(rows), elapsed)
    return rows


def fetch_one_smog_info(smog_id: int):
    """
    Pobiera pojedynczy fakt zanieczyszczenia powietrza na podstawie klucza głównego.

    Parametry:
        smog_id (int): Unikalny identyfikator wpisu smogowego (id_smog).

    Zwraca:
        dict | None: Dane o zanieczyszczeniu dla podanego ID lub None.
    """
    logger.debug("[RAW] Pobieranie SmogInfo id=%d", smog_id)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _exec(
                cur,
                "SELECT id_smog, fk_localization, measurement_date, aqi, pm25, pm10, "
                "load_date, last_update_date, is_current "
                "FROM SmogInfo WHERE id_smog = %s;",
                (smog_id,),
            )
            return cur.fetchone()


# widoki zagregowane (dashboard)

def fetch_live_dashboard():
    """
    Agreguje najbardziej aktualny stan środowiskowy dla wszystkich lokalizacji.

    Wykonuje złączenia tabeli wymiaru geograficznego z tabelami faktów (pogoda i smog),
    filtrując je po flagach operacyjnych `is_current = TRUE`. Zapewnia to natychmiastowy
     dostęp do najświeższych metryk synoptycznych oraz jakości powietrza przypisanych do indeksów siatki H3.

    Zwraca:
        list[dict]: Kolekcja zawierająca spłaszczone, zintegrowane obiekty geo-środowiskowe.
    """
    logger.debug("Pobieranie live dashboard (JOIN weather + smog, is_current=TRUE)")
    query = """
        SELECT
            g.id_localization,
            g.h3_index,
            g.longitude,
            g.latitude,
            w.measurement_date AS weather_last_measurement,
            w.temperature,
            w.humidity,
            w.wind_speed,
            w.pressure,
            s.measurement_date AS smog_last_measurement,
            s.aqi,
            s.pm25,
            s.pm10
        FROM Geographical_Dim g
        LEFT JOIN WeatherHistory_Fact w ON g.id_localization = w.fk_localization AND w.is_current = TRUE
        LEFT JOIN SmogInfo s ON g.id_localization = s.fk_localization AND s.is_current = TRUE;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(cur, query)
            rows = cur.fetchall()
    logger.debug("Live dashboard: %d lokalizacji [%.1fms]", len(rows), elapsed)
    return rows


def fetch_localization_forecast(loc_id: int):
    """
    Zwraca chronologiczny profil prognozy pogody dla konkretnego węzła.

    Wykorzystywane głównie na wykresach liniowych prezentujących przewidywane zmiany
    temperatury i ciśnienia w najbliższych cyklach czasowych.

    Parametry:
        loc_id (int): Identyfikator lokalizacji, dla której szukamy prognozy.

    Zwraca:
        list[dict]: Prognozy posortowane rosnąco według daty (`forecast_date ASC`).
    """
    logger.debug("Pobieranie prognozy dla loc_id=%d", loc_id)
    query = """
        SELECT forecast_date, temperature, humidity, wind_speed, pressure
        FROM WeatherForecast
        WHERE fk_localization = %s
        ORDER BY forecast_date ASC;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(cur, query, (loc_id,))
            rows = cur.fetchall()
    logger.debug("Prognoza loc_id=%d: %d punktów czasowych [%.1fms]", loc_id, len(rows), elapsed)
    return rows


def fetch_localization_history(loc_id: int, start_date: datetime = None, end_date: datetime = None):
    """
    Generuje zintegrowane serie czasowe danych historycznych (pogoda + smog) dla punktu.

    Używa operacji `FULL OUTER JOIN` łącząc dane pogodowe i smogowe po wspólnej dacie
    pomiaru (`measurement_date`). Pozwala to na uniknięcie luk w danych, gdy dla danej godziny
    istnieje wpis o smogu, a brakuje wpisu o pogodzie (lub odwrotnie). Implementuje dynamiczne
    klauzule WHERE do filtrowania zakresów czasu za pomocą konstrukcji `COALESCE`.

    Parametry:
        loc_id (int): Identyfikator badanej lokalizacji.
        start_date (datetime, optional): Dolna granica przedziału czasowego (włącznie).
        end_date (datetime, optional): Górna granica przedziału czasowego (włącznie).

    Zwraca:
        list[dict]: Połączona oś czasu posortowana malejąco (od najnowszych danych).
    """
    logger.debug(
        "Pobieranie historii loc_id=%d | start=%s end=%s",
        loc_id,
        start_date.isoformat() if start_date else "brak",
        end_date.isoformat() if end_date else "brak",
    )
    query = """
        SELECT
            w.measurement_date,
            w.temperature,
            w.humidity,
            w.wind_speed,
            w.pressure,
            s.aqi,
            s.pm25,
            s.pm10
        FROM WeatherHistory_Fact w
        FULL OUTER JOIN SmogInfo s ON w.fk_localization = s.fk_localization AND w.measurement_date = s.measurement_date
        WHERE COALESCE(w.fk_localization, s.fk_localization) = %s
    """
    params = [loc_id]

    if start_date:
        query += " AND COALESCE(w.measurement_date, s.measurement_date) >= %s"
        params.append(start_date)
    if end_date:
        query += " AND COALESCE(w.measurement_date, s.measurement_date) <= %s"
        params.append(end_date)

    query += " ORDER BY COALESCE(w.measurement_date, s.measurement_date) DESC;"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(cur, query, params)
            rows = cur.fetchall()
    logger.debug("Historia loc_id=%d: %d rekordów [%.1fms]", loc_id, len(rows), elapsed)
    return rows


def fetch_forecast_dashboard_by_time(target_time: datetime):
    """
    WIDOK CZASOWY PROGNOZY: Wybiera dla każdej lokalizacji dokładnie jeden rekord prognozy,
    który jest najbliższy podanemu 'target_time'. Dołącza najświeższy stan smogu,
    aby uniknąć pustej mapy w trybie AQI.
    """
    logger.debug("Dashboard forecast (CTE ROW_NUMBER): target_time=%s", target_time.isoformat())
    query = """
        WITH RankedForecast AS (
            SELECT
                fk_localization,
                forecast_date,
                temperature,
                humidity,
                wind_speed,
                pressure,
                ROW_NUMBER() OVER(
                    PARTITION BY fk_localization
                    ORDER BY ABS(EXTRACT(EPOCH FROM (forecast_date - %s::timestamptz)))
                ) as rn
            FROM WeatherForecast
        ),
        LatestSmog AS (
            SELECT DISTINCT ON (fk_localization)
                fk_localization,
                aqi,
                pm25,
                pm10
            FROM SmogInfo
            ORDER BY fk_localization, measurement_date DESC
        )
        SELECT
            g.id_localization,
            g.h3_index,
            g.longitude,
            g.latitude,
            rf.forecast_date,
            rf.temperature,
            rf.humidity,
            rf.wind_speed,
            rf.pressure,
            s.aqi,
            s.pm25,
            s.pm10
        FROM Geographical_Dim g
        INNER JOIN RankedForecast rf ON g.id_localization = rf.fk_localization AND rf.rn = 1
        LEFT JOIN LatestSmog s ON g.id_localization = s.fk_localization;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(cur, query, (target_time,))
            rows = cur.fetchall()
    logger.debug("Dashboard forecast: %d lokalizacji [%.1fms]", len(rows), elapsed)
    return rows


def fetch_history_dashboard_by_time(target_time: datetime):
    """
    WIDOK CZASOWY HISTORII: Pobiera historyczne dane meteorologiczne i smogowe,
    odporne na przesunięcia asynchroniczne pomiarów w czasie.
    """
    logger.debug("Dashboard history (CTE ROW_NUMBER): target_time=%s", target_time.isoformat())
    query = """
        WITH CombinedTimestamps AS (
            SELECT fk_localization, measurement_date FROM WeatherHistory_Fact
            UNION
            SELECT fk_localization, measurement_date FROM SmogInfo
        ),
        RankedTimestamps AS (
            SELECT
                fk_localization,
                measurement_date,
                ROW_NUMBER() OVER(
                    PARTITION BY fk_localization
                    ORDER BY ABS(EXTRACT(EPOCH FROM (measurement_date - %s::timestamptz)))
                ) as rn
            FROM CombinedTimestamps
        )
        SELECT
            g.id_localization,
            g.h3_index,
            g.longitude,
            g.latitude,
            rt.measurement_date,
            w.temperature,
            w.humidity,
            w.wind_speed,
            w.pressure,
            s.aqi,
            s.pm25,
            s.pm10
        FROM Geographical_Dim g
        INNER JOIN RankedTimestamps rt ON g.id_localization = rt.fk_localization AND rt.rn = 1
        LEFT JOIN WeatherHistory_Fact w ON rt.fk_localization = w.fk_localization AND rt.measurement_date = w.measurement_date
        LEFT JOIN SmogInfo s ON rt.fk_localization = s.fk_localization AND rt.measurement_date = s.measurement_date;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            elapsed = _exec(cur, query, (target_time,))
            rows = cur.fetchall()
    logger.debug("Dashboard history: %d lokalizacji [%.1fms]", len(rows), elapsed)
    return rows