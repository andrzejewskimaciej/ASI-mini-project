import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import main
from main import cleanup_old_data, fetch_weather_and_smog, get_stale_localizations


class TestIngestionService:

    @patch("main.get_db_connection")
    def test_cleanup_old_data_success(self, mock_get_conn):
        """
        TEST: main.cleanup_old_data (Sukces)
        
        CEL: 
        Weryfikacja poprawnego usuwania rekordów starszych niż 7 dni.
        
        PROCEDURA:
        - Symulacja poprawnego połączenia i zwrócenia kursora bazy danych.
        - Wywołanie funkcji czyszczącej.
        
        ASERCJE:
        - Wykonanie dokładnie 2 zapytań SQL typu DELETE.
        - Jawne zatwierdzenie transakcji przez metodę commit().
        - Bezwarunkowe zamknięcie kursora i połączenia z bazą danych.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 5

        cleanup_old_data()

        assert mock_cursor.execute.call_count == 2
        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch("main.get_db_connection")
    def test_cleanup_old_data_rollback_on_exception(self, mock_get_conn):
        """
        TEST: main.cleanup_old_data (Obsługa błędów bazy)
        
        CEL:
        Weryfikacja zachowania transakcyjności w przypadku awarii bazy danych.
        
        PROCEDURA:
        - Wymuszenie rzucenia wyjątku Exception podczas operacji execute().
        - Wywołanie funkcji czyszczącej.
        
        ASERCJE:
        - Całkowity brak wywołań metody commit().
        - Jawne wykonanie metody rollback() w celu wyczyszczenia bufora bazy.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("Database error")

        cleanup_old_data()

        mock_conn.commit.assert_not_called()
        mock_conn.rollback.assert_called_once()

    @patch("main.get_stale_localizations")
    def test_fetch_weather_and_smog_no_work(self, mock_get_stale):
        """
        TEST: main.fetch_weather_and_smog (Brak zadań)
        
        CEL:
        Weryfikacja mechanizmu short-circuit, gdy dane są aktualne.
        
        PROCEDURA:
        - Podstawienie pustej listy [] jako wyniku wyszukiwania przeterminowanych punktów.
        - Wywołanie głównej funkcji potoku.
        
        ASERCJE:
        - Funkcja przerywa działanie na samym początku i zwraca wartość False.
        """
        mock_get_stale.return_value = []

        result = fetch_weather_and_smog()

        assert result is False

    @patch("main.requests.get")
    @patch("main.get_db_connection")
    @patch("main.get_stale_localizations")
    def test_fetch_weather_and_smog_api_timeout_handling(
        self, mock_get_stale, mock_get_conn, mock_requests_get
    ):
        """
        TEST: main.fetch_weather_and_smog (Obsługa timeoutu API)
        
        CEL:
        Weryfikacja odporności na błędy sieciowe (np. Read timed out) i izolacji błędów.
        
        PROCEDURA:
        - Podstawienie jednej lokalizacji o ID 999.
        - Wymuszenie rzucenia wyjątku przez moduł requests przy próbie połączenia z API.
        - Wywołanie głównej funkcji.
        
        ASERCJE:
        - Funkcja nie przerywa działania aplikacji (zwraca True jako koniec pętli).
        - Wykonanie rollback() dla uszkodzonego rekordu w celu odblokowania transakcji.
        - Brak wywołania commit() dla błędnej paczki danych.
        """
        mock_get_stale.return_value = [(999, 52.23, 21.01)]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_requests_get.side_effect = Exception("Read timed out")

        result = fetch_weather_and_smog()

        assert result is True
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()