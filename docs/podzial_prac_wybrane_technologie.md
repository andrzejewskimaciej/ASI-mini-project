# Podział prac i uzasadnienie wyboru technologii

Niniejsza sekcja przedstawia zakres prac zrealizowanych przez członków zespołu projektowego oraz uzasadnienie wyboru zastosowanych technologii.

## 1. Podział prac

### Prace realizowane wspólnie

* Opracowanie architektury systemu, w tym przygotowanie diagramów komponentów oraz wdrożenia w notacji UML.
* Przygotowanie dokumentacji projektowej, obejmującej plik `README.md` oraz dokumentację techniczną aplikacji.

### Maciej Andrzejewski

* Implementacja modułu Ingestion, odpowiedzialnego za pobieranie danych pogodowych i informacji o jakości powietrza z zewnętrznych API (Open-Meteo oraz AQICN), wraz z mechanizmem usuwania nieaktualnych danych.
* Przygotowanie środowiska testowego w Dockerze oraz opracowanie testów dla modułu Ingestion.
* Implementacja warstwy frontendowej aplikacji, w tym wizualizacji danych pogodowych i jakości powietrza z wykorzystaniem biblioteki Leaflet.

### Ludwik Madej

* Projekt oraz implementacja schematu bazy danych PostgreSQL, w tym przygotowanie skryptów inicjalizacyjnych, indeksów oraz danych początkowych.
* Implementacja backendowego API w technologii FastAPI, obejmującego endpointy dla dashboardu, danych historycznych i prognoz, wraz z obsługą logowania żądań oraz mechanizmu CORS. Przygotowanie testów backendu.
* Przygotowanie środowiska wdrożeniowego w Kubernetes (Kind), w tym manifestów dla wszystkich komponentów systemu oraz skryptu automatyzującego wdrożenie.

## 2. Uzasadnienie wyboru technologii

### PostgreSQL

PostgreSQL wybrano ze względu na relacyjny charakter przetwarzanych danych oraz konieczność zachowania spójności pomiędzy lokalizacjami, prognozami i danymi historycznymi. Zastosowanie indeksów umożliwiło optymalizację wydajności najczęściej wykonywanych zapytań.

### FastAPI (Python)

FastAPI zapewnia wysoką wydajność dzięki obsłudze operacji asynchronicznych oraz umożliwia automatyczne generowanie dokumentacji API w standardzie Swagger, co znacząco usprawniło proces testowania i integracji systemu.

### Python - Ingestion Worker

Wybór języka Python dla modułu Ingestion pozwolił zachować spójność technologiczną projektu. Dodatkowo zastosowanie mechanizmów wielowątkowości umożliwiło równoległe pobieranie danych dla wielu lokalizacji.

### Frontend: HTML/CSS/JavaScript + Nginx

Ze względu na relatywnie prosty charakter interfejsu zdecydowano się na wykorzystanie podstawowych technologii webowych zamiast rozbudowanych frameworków frontendowych. Pozwoliło to ograniczyć złożoność projektu oraz zapewnić szybkie ładowanie aplikacji. Nginx wykorzystano jako lekki serwer do obsługi statycznych zasobów aplikacji.

### Docker i Kubernetes (Kind)

Docker Compose umożliwił wydzielenie niezależnego środowiska testowego, natomiast wykorzystanie pamięci `tmpfs` dla testowej instancji bazy danych przyspieszyło wykonywanie testów. Kubernetes (Kind) zapewnił możliwość zarządzania wdrożeniem aplikacji, konfiguracją sieci oraz trwałymi wolumenami danych dla bazy PostgreSQL.
