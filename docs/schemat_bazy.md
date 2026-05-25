# Schemat bazy danych

Baza: PostgreSQL 15. Inicjalizacja: `database/01_init.sql`, dane geograficzne: `database/02_seed_geo.sql`.

## Tabele

### Geographical_Dim

Słownik lokalizacji - ~380 powiatów Polski. Dane statyczne, seedowane przy starcie.

| Kolumna          | Typ                | Opis                                         |
| ---------------- | ------------------ | -------------------------------------------- |
| id_localization  | SERIAL PK          | klucz główny                                 |
| h3_index         | VARCHAR(15) UNIQUE | indeks H3 (sześciokątna siatka geograficzna) |
| longitude        | REAL               | długość geograficzna                         |
| latitude         | REAL               | szerokość geograficzna                       |
| last_update_date | TIMESTAMPTZ        | czas ostatniej zmiany rekordu                |

---

### WeatherHistory_Fact

Bieżące i historyczne pomiary pogodowe. Jeden rekord = jeden pomiar godzinowy dla jednej lokalizacji.

| Kolumna          | Typ         | Opis                                        |
| ---------------- | ----------- | ------------------------------------------- |
| id_history       | SERIAL PK   | klucz główny                                |
| fk_localization  | INT FK      | referencja do Geographical_Dim              |
| measurement_date | TIMESTAMPTZ | czas pomiaru (z API)                        |
| temperature      | REAL        | temperatura powietrza [°C]                  |
| humidity         | REAL        | wilgotność względna [%]                     |
| wind_speed       | REAL        | prędkość wiatru [m/s]                       |
| pressure         | REAL        | ciśnienie atmosferyczne [hPa]               |
| is_current       | BOOLEAN     | `TRUE` = bieżący pomiar dla tej lokalizacji |
| last_update_date | TIMESTAMPTZ | czas zapisu przez workera                   |

Unikalny constraint: `(fk_localization, measurement_date)` - upsert nie duplikuje danych.

---

### WeatherForecast

Prognoza pogodowa na 24 godziny do przodu. Nadpisywana przy każdym cyklu workera.

| Kolumna         | Typ         | Opis                               |
| --------------- | ----------- | ---------------------------------- |
| id_forecast     | SERIAL PK   | klucz główny                       |
| fk_localization | INT FK      | referencja do Geographical_Dim     |
| forecast_date   | TIMESTAMPTZ | docelowy czas prognozy             |
| temperature     | REAL        | prognozowana temperatura [°C]      |
| humidity        | REAL        | prognozowana wilgotność [%]        |
| wind_speed      | REAL        | prognozowana prędkość wiatru [m/s] |
| pressure        | REAL        | prognozowane ciśnienie [hPa]       |
| load_date       | TIMESTAMPTZ | czas zapisu przez workera          |

Unikalny constraint: `(fk_localization, forecast_date)`.

---

### SmogInfo

Dane o jakości powietrza z AQICN. Analogiczna struktura do WeatherHistory_Fact.

| Kolumna          | Typ         | Opis                           |
| ---------------- | ----------- | ------------------------------ |
| id_smog          | SERIAL PK   | klucz główny                   |
| fk_localization  | INT FK      | referencja do Geographical_Dim |
| measurement_date | TIMESTAMPTZ | czas pomiaru ze stacji AQICN   |
| aqi              | INTEGER     | Air Quality Index              |
| pm25             | REAL        | stężenie PM2.5 [µg/m³]         |
| pm10             | REAL        | stężenie PM10 [µg/m³]          |
| is_current       | BOOLEAN     | `TRUE` = bieżący pomiar        |
| load_date        | TIMESTAMPTZ | czas pierwszego zapisu         |
| last_update_date | TIMESTAMPTZ | czas ostatniej aktualizacji    |

Unikalny constraint: `(fk_localization, measurement_date)`.

---

## Indeksy

| Indeks                    | Tabela              | Warunek             | Cel                                  |
| ------------------------- | ------------------- | ------------------- | ------------------------------------ |
| idx_weather_hist_current  | WeatherHistory_Fact | `is_current = TRUE` | szybki odczyt aktualnego stanu mapy  |
| idx_smog_current          | SmogInfo            | `is_current = TRUE` | szybki odczyt aktualnego smogu       |
| idx_weather_hist_date_loc | WeatherHistory_Fact | -                   | zapytania historyczne po dacie       |
| idx_smog_date_loc         | SmogInfo            | -                   | zapytania historyczne po dacie       |
| idx_weather_fore_date_loc | WeatherForecast     | -                   | pobieranie prognozy po czasie        |
| idx_geo_coords            | Geographical_Dim    | -                   | wyszukiwanie przestrzenne po lat/lon |

Pierwsze dwa to **partial indexes** - obejmują tylko rekordy z `is_current = TRUE`, co drastycznie zmniejsza ich rozmiar.

## Retencja

Worker czyści dane starsze niż 7 dni raz na dobę (dotyczy `WeatherHistory_Fact` i `SmogInfo`). `WeatherForecast` jest nadpisywana przy każdym cyklu i nie rośnie.
