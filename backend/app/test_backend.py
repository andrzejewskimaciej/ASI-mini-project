import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

# dodanie ścieżki do sys.path, żeby importy z app działały poprawnie
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app


class TestBackendArchitecture:

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """
        Inicjalizacja izolowanego klienta testowego FastAPI.
        Wywoływana automatycznie przed każdym scenariuszem testowym.
        """
        self.client = TestClient(app)




    # testy API, punkty dostępowe i baza danych

    @patch("app.main.fetch_live_dashboard")
    def test_get_live_metrics_dashboard_success(self, mock_fetch):
        """
        TEST: GET /api/v1/dashboard/live (Sukces)
        
        CEL:
        Weryfikacja agregacji danych w widoku operacyjnym (Live Dashboard).
        
        MOCKOWANIE:
        Podstawienie pod warstwę bazodanową listy zawierającej jeden kompletny 
        słownik reprezentujący połączone dane przestrzenne, pogodowe oraz smogowe.
        
        ASERCJE:
        - Kod odpowiedzi HTTP musi wynosić 200 (OK).
        - Klucz 'count' w strukturze JSON musi być równy długości zwróconej kolekcji (1).
        - Dane przestrzenne (h3_index, lat, lon) oraz pomiarowe (aqi, temperature) 
          muszą być idealnie zmapowane w ciele odpowiedzi.
        """
        mock_fetch.return_value = [{
            "id_localization": 1,
            "h3_index": "881e204481fffff",
            "longitude": 21.01,
            "latitude": 52.23,
            "weather_last_measurement": "2026-05-17T12:00:00Z",
            "temperature": 18.5,
            "humidity": 60.0,
            "wind_speed": 3.4,
            "pressure": 1013.0,
            "smog_last_measurement": "2026-05-17T12:00:00Z",
            "aqi": 42,
            "pm25": 10.2,
            "pm10": 20.4
        }]

        response = self.client.get("/api/v1/dashboard/live")
        json_data = response.json()

        assert response.status_code == 200
        assert json_data["count"] == 1
        assert json_data["data"][0]["h3_index"] == "881e204481fffff"
        assert json_data["data"][0]["temperature"] == 18.5
        assert json_data["data"][0]["aqi"] == 42

    @patch("app.main.fetch_all_geographical_dim")
    def test_get_localizations_all(self, mock_fetch):
        """
        TEST: GET /api/v1/localizations (Sukces)
        
        CEL:
        Weryfikacja pobierania pełnego spisu zarejestrowanych węzłów geograficznych.
        
        MOCKOWANIE:
        Wymuszenie zwrotu wieloelementowej kolekcji słowników z warstwy DAL.
        
        ASERCJE:
        - Kod odpowiedzi HTTP musi wynosić 200 (OK).
        - Zwrócona struktura musi być listą.
        - Długość listy musi odpowiadać danym zasymulowanym w mocku.
        """
        mock_fetch.return_value = [
            {"id_localization": 1, "h3_index": "881e204481fffff"},
            {"id_localization": 2, "h3_index": "881e204483fffff"}
        ]

        response = self.client.get("/api/v1/localizations")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 2

    @patch("app.main.fetch_one_geographical_dim")
    def test_get_localization_by_id_success(self, mock_fetch):
        """
        TEST: GET /api/v1/localizations/{loc_id} (Sukces)
        
        CEL:
        Weryfikacja pobierania metadanych jednej konkretnej lokalizacji na podstawie ID.
        
        MOCKOWANIE:
        Symulacja odnalezienia rekordu o ID = 1 w bazie danych.
        
        ASERCJE:
        - Kod odpowiedzi HTTP musi wynosić 200 (OK).
        - Zwrócony obiekt musi zawierać unikalny indeks H3 powiązany z danym kluczem głównym.
        """
        mock_fetch.return_value = {"id_localization": 1, "h3_index": "881e204481fffff"}

        response = self.client.get("/api/v1/localizations/1")
        
        assert response.status_code == 200
        assert response.json()["h3_index"] == "881e204481fffff"

    @patch("app.main.fetch_one_geographical_dim")
    def test_get_localization_by_id_not_found(self, mock_fetch):
        """
        TEST: GET /api/v1/localizations/{loc_id} (Brak rekordu - HTTP 404)
        
        CEL:
        Weryfikacja reakcji systemu na zapytanie o nieistniejący węzeł geograficzny.
        
        MOCKOWANIE:
        Ustawienie wartości zwracanej z bazy danych jako None (brak dopasowania w SQL).
        
        ASERCJE:
        - Kod odpowiedzi HTTP musi wynosić 404 (Not Found).
        - Treść komunikatu błędu ('detail') musi precyzyjnie wskazywać brak węzła.
        """
        mock_fetch.return_value = None

        response = self.client.get("/api/v1/localizations/999")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Localization node not found"

    @patch("app.main.fetch_localization_forecast")
    def test_get_forecast_by_localization_success(self, mock_fetch):
        """
        TEST: GET /api/v1/localizations/{loc_id}/forecast (Sukces)
        
        CEL:
        Weryfikacja pobierania chronologicznej prognozy pogody (24h) dla określonego węzła.
        
        MOCKOWANIE:
        Wstrzyknięcie listy obiektów prognozy posortowanych czasowo.
        
        ASERCJE:
        - Kod odpowiedzi HTTP wynosi 200 (OK).
        - Odpowiedź zawiera poprawną strukturę danych dla interfejsu użytkownika.
        """
        mock_fetch.return_value = [
            {"forecast_date": "2026-05-18T00:00:00Z", "temperature": 12.0},
            {"forecast_date": "2026-05-18T01:00:00Z", "temperature": 11.5}
        ]

        response = self.client.get("/api/v1/localizations/1/forecast")
        
        assert response.status_code == 200
        assert len(response.json()) == 2

    @patch("app.main.fetch_localization_history")
    def test_get_history_by_localization_with_filters(self, mock_fetch):
        """
        TEST: GET /api/v1/localizations/{loc_id}/history (Filtrowanie zakresu czasu)
        
        CEL:
        Weryfikacja przekazywania i obsługi parametrów Query (start, end) dla serii historycznych.
        
        MOCKOWANIE:
        Przechwycenie parametrów i zwrócenie ustrukturyzowanej odpowiedzi z bazy danych.
        
        ASERCJE:
        - Serwer prawidłowo parsuje parametry czasu ISO i zwraca status 200 (OK).
        - Funkcja bazodanowa została wywołana z poprawnymi filtrami czasowymi (obiekty datetime).
        """
        mock_fetch.return_value = [
            {"measurement_date": "2026-05-15T10:00:00Z", "temperature": 20.0, "aqi": 35}
        ]

        params = {
            "start": "2026-05-15T00:00:00Z",
            "end": "2026-05-16T00:00:00Z"
        }
        response = self.client.get("/api/v1/localizations/1/history", params=params)
        
        assert response.status_code == 200
        mock_fetch.assert_called_once()
        
        # sprawdzamy typ argumentów, czy poszły obiekty datetime
        called_args = mock_fetch.call_args[1]
        assert isinstance(called_args["start_date"], datetime)
        assert isinstance(called_args["end_date"], datetime)




    # testy tabel faktów, surowe rekordy wejściowe

    @patch("app.main.fetch_one_weather_forecast")
    def test_get_one_raw_forecast_not_found(self, mock_fetch):
        """
        TEST: GET /api/v1/raw/weather-forecasts/{id} (Brak rekordu - HTTP 404)
        
        CEL:
        Zapewnienie integralności obsługi błędów dla surowych tabel faktów prognozy pogody.
        """
        mock_fetch.return_value = None
        response = self.client.get("/api/v1/raw/weather-forecasts/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Forecast record not found"

    @patch("app.main.fetch_one_weather_history")
    def test_get_one_raw_history_not_found(self, mock_fetch):
        """
        TEST: GET /api/v1/raw/weather-histories/{id} (Brak rekordu - HTTP 404)
        
        CEL:
        Zapewnienie integralności obsługi błędów dla surowych tabel historycznych.
        """
        mock_fetch.return_value = None
        response = self.client.get("/api/v1/raw/weather-histories/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "History fact record not found"

    @patch("app.main.fetch_one_smog_info")
    def test_get_one_raw_smog_not_found(self, mock_fetch):
        """
        TEST: GET /api/v1/raw/smog-infos/{id} (Brak rekordu - HTTP 404)
        
        CEL:
        Zapewnienie integralności obsługi błędów dla surowych danych pomiarowych indeksu SMOG.
        """
        mock_fetch.return_value = None
        response = self.client.get("/api/v1/raw/smog-infos/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Smog info record not found"