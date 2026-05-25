-- geografia, hexagony h3
CREATE TABLE IF NOT EXISTS Geographical_Dim (
    id_localization SERIAL PRIMARY KEY,
    h3_index VARCHAR(15) UNIQUE NOT NULL, -- automatyczny, unikalny indeks
    longitude REAL NOT NULL,              
    latitude REAL NOT NULL,               
    last_update_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- prognoza pogody na 24h w przód
CREATE TABLE IF NOT EXISTS WeatherForecast (
    id_forecast SERIAL PRIMARY KEY,
    fk_localization INT REFERENCES Geographical_Dim(id_localization) ON DELETE CASCADE,
    forecast_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    temperature REAL,                                
    humidity REAL,                                   
    wind_speed REAL,                                 
    pressure REAL,                                   
    load_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- automatyczny indeks złożony (fk_localization, forecast_date)
    CONSTRAINT unique_loc_forecast_time UNIQUE (fk_localization, forecast_date)
);

-- historia pogody, dane historyczne
CREATE TABLE IF NOT EXISTS WeatherHistory_Fact (
    id_history SERIAL PRIMARY KEY,
    fk_localization INT REFERENCES Geographical_Dim(id_localization) ON DELETE CASCADE,
    measurement_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    temperature REAL,
    humidity REAL,
    wind_speed REAL,
    pressure REAL,
    last_update_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN DEFAULT TRUE,
    
    -- automatyczny indeks złożony (fk_localization, measurement_date)
    CONSTRAINT unique_loc_history_time UNIQUE (fk_localization, measurement_date)
);

-- aktualny smog, dane z aqicn
CREATE TABLE IF NOT EXISTS SmogInfo (
    id_smog SERIAL PRIMARY KEY,
    fk_localization INT REFERENCES Geographical_Dim(id_localization) ON DELETE CASCADE,
    measurement_date TIMESTAMP WITH TIME ZONE NOT NULL, 
    aqi INTEGER,                                        
    pm25 REAL,                                          
    pm10 REAL,                                          
    load_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_update_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_current BOOLEAN DEFAULT TRUE,

    -- automatyczny indeks złożony (fk_localization, measurement_date)
    CONSTRAINT unique_loc_smog_time UNIQUE (fk_localization, measurement_date)
);

-- indeksy do optymalizacji zapytań, przyspieszają działanie aplikacji pod obciążeniem
-- aktualny stan na mapie, filtruje tylko is_current=true, co drastycznie oszczędza dysk
CREATE INDEX IF NOT EXISTS idx_weather_hist_current 
ON WeatherHistory_Fact(fk_localization) 
WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_smog_current 
ON SmogInfo(fk_localization) 
WHERE is_current = TRUE;


-- trendy z 30 dni, przyspiesza agregowanie i sortowanie po dacie
CREATE INDEX IF NOT EXISTS idx_weather_hist_date_loc 
ON WeatherHistory_Fact(measurement_date, fk_localization);

CREATE INDEX IF NOT EXISTS idx_smog_date_loc 
ON SmogInfo(measurement_date, fk_localization);


-- pobieranie prognozy pogody, sortowanie w przód po dacie
CREATE INDEX IF NOT EXISTS idx_weather_fore_date_loc 
ON WeatherForecast(forecast_date, fk_localization);


-- wyszukiwanie przestrzenne po współrzędnych geograficznych, przydatne przy wycinaniu boxa na mapie
CREATE INDEX IF NOT EXISTS idx_geo_coords 
ON Geographical_Dim(latitude, longitude);