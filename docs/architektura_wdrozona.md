# Architektura wdrożona

## Co powstało

System monitoringu pogody i jakości powietrza dla powiatów w Polsce. Zbiera dane cyklicznie z dwóch zewnętrznych API, przechowuje je w PostgreSQL i udostępnia przez przeglądarkę na interaktywnej mapie.

Ogólny kształt systemu pokrył się z planem. Główne różnice i decyzje opisano poniżej.

## Komponenty

**Nginx (frontend)** serwuje pliki statyczne (HTML, CSS, JS) i pełni rolę reverse proxy - żądania pod `/api/` są przekazywane do backendu. Użytkownik trafia zawsze do jednego punktu wejścia na porcie 80.

**FastAPI (backend)** wystawia REST API z danymi z bazy. Nie zawiera żadnej logiki biznesowej - tylko odczyt i zwrot JSON. Swagger UI dostępny pod `/docs`.

**Ingestion Worker (Python)** działa w nieskończonej pętli. Co 60 sekund sprawdza, które lokalizacje mają dane starsze niż 50 minut i odpytuje dla nich Open-Meteo oraz AQICN. Przetwarza lokalizacje równolegle przez `ThreadPoolExecutor`. Raz na dobę czyści dane starsze niż 7 dni.

**PostgreSQL** przechowuje dane geograficzne, historię pomiarów, prognozy i dane smogowe. Schemat opisany w `schemat_bazy.md`.

## Decyzje podjęte w trakcie

**Równoległość workera** - sekwencyjne przetwarzanie 380 lokalizacji zajmowało ~7-8 minut. Przeszliśmy na `ThreadPoolExecutor` (domyślnie 5 wątków), co skróciło czas do ~1.5-2 min. Każdy wątek tworzy własne połączenie z bazą, żeby uniknąć problemów z thread-safety psycopg2.

**Interwał odświeżania** - zdecydowaliśmy na 50 minut jako granicę "przestarzałości" danych. Jest to kompromis między aktualnością a  limitami narzuconymi przez API.

**Nginx jako reverse proxy** - zamiast wystawiać backend bezpośrednio na zewnątrz, frontend-nginx obsługuje cały ruch. Upraszcza to konfigurację k8s (jeden NodePort zamiast dwóch) i pozwala unikać problemów z CORS.

**H3 indexing** - lokalizacje powiatów są opisane indeksem H3 (sześciokątna siatka geograficzna) jako naturalny klucz przestrzenny. Ułatwia późniejsze grupowanie na mapie.

**is_current flag** - zamiast zawsze nadpisywać jedyny rekord na lokalizację, trzymamy historię i oznaczamy bieżący pomiar flagą `is_current = TRUE`. Poprzednie rekordy tej lokalizacji tracą flagę przy każdym upsert. Partial index na `is_current = TRUE` sprawia, że zapytania o aktualny stan mapy są znacznie szybsze.

**Retencja 7 dni** - historia starsza niż tydzień jest usuwana raz na dobę. Wystarczy do analizy trendów i nie powoduje niekontrolowanego wzrostu bazy.

## Środowiska

| Środowisko | Jak uruchomić                                  | Charakterystyka                                          |
| ---------- | ---------------------------------------------- | -------------------------------------------------------- |
| dev        | `docker compose -f docker-compose.dev.yml up`  | hot-reload, logi debug, nginx bez cache                  |
| test       | `docker compose -f docker-compose.test.yml up` | osobna baza, pytest + Locust                             |
| prod       | `.\k8s\deploy.ps1`                             | Kind cluster, 2 repliki backendu i frontendu, PVC dla DB |

Konfiguracja przez zmienne środowiskowe (`.env.dev` lokalnie, Secret/ConfigMap w k8s). Klucz AQICN_TOKEN musi być własny - token `demo` zwraca dane zawsze z tej samej stacji niezależnie od koordynat.

## Ograniczenia

- AQICN z kluczem `demo` zwraca dane z jednej stacji dla całego kraju - na mapie smog jest wtedy wszędzie taki sam. Wymagany własny klucz.
- Brak autentykacji backendu - API jest otwarte.
- PostgreSQL działa jako single-instance (1 replika). HA wymagałoby lepszego rozwiązania.
