"""
Scenariusze testów wydajnościowych - Weather & AQI API

Konfiguracja: 50 użytkowników, spawn 5/s, czas 90s
Uruchomienie (przez docker-compose.test.yml):
  docker compose -f docker-compose.test.yml --profile perf up --build

Endpointy pokryte testami:
  - GET /api/v1/dashboard/live          (priorytet: 8 - najczęstszy widok)
  - GET /api/v1/localizations           (priorytet: 5)
  - GET /api/v1/localizations/{id}/forecast  (priorytet: 4)
  - GET /api/v1/localizations/{id}/history   (priorytet: 4)
  - GET /api/v1/dashboard/forecast?time=     (priorytet: 3)
  - GET /api/v1/dashboard/history?time=      (priorytet: 3)
  - GET /api/v1/raw/weather-forecasts        (priorytet: 1 - audyt)
"""

import random
from datetime import datetime, timedelta

from locust import HttpUser, between, events, task


class WeatherAPIUser(HttpUser):
    """
    Symuluje typowego użytkownika systemu monitoringu środowiskowego.

    Scenariusz odzwierciedla realny wzorzec korzystania z dashboardu:
    - Użytkownik ląduje na mapie (live dashboard)
    - Klika lokalizacje, sprawdza prognozy i historię
    - Przesuwa suwak czasu (forecast/history timeline)
    """

    wait_time = between(0.2, 1.2)  # Krótkie czasy oczekiwania → duże obciążenie

    @task(8)
    def dashboard_live(self):
        """Główny widok mapy - najczęściej odpytywany endpoint."""
        with self.client.get("/api/v1/dashboard/live", catch_response=True) as resp:
            if resp.status_code == 200:
                data = resp.json()
                # Weryfikacja jakości odpowiedzi (nie tylko kodu HTTP)
                if not isinstance(data.get("data"), list):
                    resp.failure("Odpowiedź nie zawiera klucza 'data' z listą")
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:100]}")

    @task(5)
    def list_localizations(self):
        """Pobieranie listy wszystkich punktów pomiarowych."""
        with self.client.get("/api/v1/localizations", catch_response=True) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list):
                    resp.failure("Oczekiwano listy lokalizacji")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(4)
    def localization_forecast(self):
        """Prognoza pogody dla konkretnej lokalizacji (symulacja kliknięcia na mapie)."""
        loc_id = random.randint(1, 20)
        with self.client.get(
            f"/api/v1/localizations/{loc_id}/forecast",
            name="/api/v1/localizations/[id]/forecast",  # Grupowanie w statystykach
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 404):
                resp.failure(f"Nieoczekiwany HTTP {resp.status_code}")

    @task(4)
    def localization_history(self):
        """Historia pomiarów z zakresem czasu - symulacja analizy trendów."""
        loc_id = random.randint(1, 20)
        start = (datetime.utcnow() - timedelta(days=random.randint(1, 5))).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        end = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.client.get(
            f"/api/v1/localizations/{loc_id}/history",
            params={"start": start, "end": end},
            name="/api/v1/localizations/[id]/history",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 404):
                resp.failure(f"Nieoczekiwany HTTP {resp.status_code}")

    @task(3)
    def dashboard_forecast_timeline(self):
        """Symuluje przesuwanie suwaka prognozy +1h do +24h."""
        offset_h = random.randint(1, 24)
        target = (datetime.utcnow() + timedelta(hours=offset_h)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self.client.get(
            "/api/v1/dashboard/forecast",
            params={"time": target},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data.get("data"), list):
                    resp.failure("Brak klucza 'data' w odpowiedzi forecast")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(3)
    def dashboard_history_timeline(self):
        """Symuluje przesuwanie suwaka historii -1h do -168h (7 dni)."""
        offset_h = random.randint(1, 168)
        target = (datetime.utcnow() - timedelta(hours=offset_h)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self.client.get(
            "/api/v1/dashboard/history",
            params={"time": target},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data.get("data"), list):
                    resp.failure("Brak klucza 'data' w odpowiedzi history")
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def raw_weather_forecasts(self):
        """Dostęp do surowych danych - rzadki, symuluje integracje zewnętrzne."""
        with self.client.get(
            "/api/v1/raw/weather-forecasts", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """
    Hook Locust: uruchamiany przy zamknięciu testu.
    Wymusza kod wyjścia != 0 jeśli wskaźnik błędów przekracza 5%.
    Umożliwia integrację z CI/CD (test failed → pipeline blocked).
    """
    stats = environment.stats.total
    if stats.num_requests > 0:
        failure_rate = stats.num_failures / stats.num_requests
        print(
            f"\n[LOCUST SUMMARY] Żądania: {stats.num_requests} | "
            f"Błędy: {stats.num_failures} | "
            f"Wskaźnik błędów: {failure_rate:.1%} | "
            f"P95: {stats.get_response_time_percentile(0.95):.0f}ms"
        )
        if failure_rate > 0.05:
            print("[LOCUST] FAIL: Wskaźnik błędów > 5% — testy wydajnościowe nie zdały!")
            environment.process_exit_code = 1
        else:
            print("[LOCUST] PASS: System wydajnościowy spełnia wymagania.")
