const API_URL = '/api/v1';


let map;
let geojsonLayer = null; 
let regionyGeoJSON = null; 
let currentData = []; 
let globalLocalizations = [];
let currentFactor = "aqi";
let currentTimeMode = "live";
let activeFeature = null; // zapamiętuje aktualnie wybrany powiat

const MAP_MODE = 'powiaty'; 
const GEOJSON_URL = 'https://raw.githubusercontent.com/ppatrzyk/polska-geojson/master/powiaty/powiaty-min.geojson';

const COLOR_CONFIG = {
    aqi: { minHue: 120, maxHue: 0, minVal: 0, maxVal: 150, title: "Jakość Powietrza (AQI)", unit: "" },          
    temperature: { minHue: 240, maxHue: 0, minVal: -10, maxVal: 35, title: "Temperatura", unit: " °C" },       
    humidity: { minHue: 40, maxHue: 220, minVal: 0, maxVal: 100, title: "Wilgotność", unit: " %" },           
    pressure: { minHue: 280, maxHue: 140, minVal: 980, maxVal: 1040, title: "Ciśnienie", unit: " hPa" },         
    wind_speed: { minHue: 180, maxHue: 300, minVal: 0, maxVal: 15, title: "Prędkość wiatru", unit: " m/s" }  
};

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initControls();
    initLayerSelector();
    checkConnectionAndLoad();
    if (window.lucide) {
        lucide.createIcons();
    }
});

function initMap() {
    map = L.map('map', {
        center: [51.9194, 19.1451], zoom: 6, minZoom: 5, maxZoom: 11,
        maxBounds: [[48.8, 14.0], [55.0, 24.2]], 
        maxBoundsViscosity: 1.0
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 20 }).addTo(map);

    map.createPane('labelsPane');
    map.getPane('labelsPane').style.zIndex = 650;
    map.getPane('labelsPane').style.pointerEvents = 'none';

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png', {
        pane: 'labelsPane'
    }).addTo(map);
}

function getContinuousColor(value, minVal, maxVal, config) {
    if (value === null || value === undefined) return '#1e293b';
    if (maxVal === minVal) return `hsl(${config.minHue}, 85%, 45%)`;
    const fraction = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal)));
    const hue = config.minHue + fraction * (config.maxHue - config.minHue);
    
    return `hsl(${hue}, 85%, 45%)`; 
}

async function checkConnectionAndLoad() {
    const statusEl = document.getElementById("connection-status");
    const loadingBar = document.getElementById("loading-bar");
    statusEl.textContent = "Pobieranie siatki mapy i danych stacji...";
    statusEl.className = "status-checking";
    if (loadingBar) loadingBar.classList.remove("hidden");

    try {
        if (!regionyGeoJSON) {
            const geojsonRes = await fetch(GEOJSON_URL);
            if (!geojsonRes.ok) throw new Error("Błąd CDN GeoJSON");
            regionyGeoJSON = await geojsonRes.json();

            regionyGeoJSON.features.forEach(feature => {
                const bounds = L.geoJSON(feature).getBounds();
                feature.properties.cachedCenterLat = (bounds.getSouth() + bounds.getNorth()) / 2;
                feature.properties.cachedCenterLon = (bounds.getWest() + bounds.getEast()) / 2;
            });
        }
    } catch (e) {
        console.error("Nie udało się pobrać siatki mapy z zewnętrznego serwera:", e);
        statusEl.textContent = "Błąd pobierania podkładu mapy (CORS/Network)";
        statusEl.className = "status-offline";
        if (loadingBar) loadingBar.classList.add("hidden");
        return; 
    }

    try {
        const [locRes, liveRes] = await Promise.all([
            fetch(`${API_URL}/localizations`),
            fetch(`${API_URL}/dashboard/live`)
        ]);

        globalLocalizations = await locRes.json();
        const liveJson = await liveRes.json();
        currentData = liveJson.data || liveJson; 

        statusEl.textContent = "Połączono (Tryb: Powiaty)";
        statusEl.className = "status-online";
        
        updateVisualization();
    } catch (error) {
        console.error("Błąd komunikacji z API lokalnym:", error);
        statusEl.textContent = "Brak połączenia z lokalnym API serwera";
        statusEl.className = "status-offline";
    } finally {
        if (loadingBar) loadingBar.classList.add("hidden");
        if (window.lucide) lucide.createIcons();
    }
}

function findNearestData(lat, lon) {
    let nearest = null; let minDistance = Infinity;
    for (let i = 0; i < currentData.length; i++) {
        const item = currentData[i];
        const itemLat = item.latitude || item.lat;
        const itemLon = item.longitude || item.lon;
        if (!itemLat || !itemLon) continue;
        
        const dist = Math.pow(lat - itemLat, 2) + Math.pow(lon - itemLon, 2);
        if (dist < minDistance) { 
            minDistance = dist; 
            nearest = item; 
        }
    }
    return nearest;
}

function initLayerSelector() {
    document.getElementById("layer-selector").addEventListener("change", (e) => {
        currentFactor = e.target.value;
        updateVisualization();
    });
}

function updateVisualization() {
    if (!regionyGeoJSON || !currentData || currentData.length === 0) return;

    if (geojsonLayer) map.removeLayer(geojsonLayer);

    const config = COLOR_CONFIG[currentFactor];
    const minVal = config.minVal;
    const maxVal = config.maxVal;

    geojsonLayer = L.geoJSON(regionyGeoJSON, {
        style: function (feature) {
            const centerLat = feature.properties.cachedCenterLat;
            const centerLon = feature.properties.cachedCenterLon;

            const nearestSensor = findNearestData(centerLat, centerLon);
            feature.properties.sensorData = nearestSensor; 

            let val = nearestSensor ? nearestSensor[currentFactor] : null;

            return {
                fillColor: getContinuousColor(val, minVal, maxVal, config),
                weight: 0.8,
                opacity: 0.6,
                color: '#334155', 
                fillOpacity: 0.7
            };
        },
        onEachFeature: function (feature, layer) {
            layer.on({
                mouseover: (e) => {
                    const l = e.target;
                    l.setStyle({ weight: 2.5, color: '#ffffff', fillOpacity: 0.9 });
                    l.bringToFront();
                    activeFeature = feature; // zapamiętujemy aktywny powiat
                    displayLocationDetails(feature.properties.nazwa, feature.properties.sensorData);
                },
                mouseout: (e) => geojsonLayer.resetStyle(e.target)
            });
        }
    }).addTo(map);

    // odświeżamy panel boczny dla wybranego powiatu po zaktualizowaniu danych
    if (activeFeature) {
        displayLocationDetails(activeFeature.properties.nazwa, activeFeature.properties.sensorData);
    }

    updateContinuousLegend(minVal, maxVal, config);
}

function updateContinuousLegend(minVal, maxVal, config) {
    const legendBoxes = document.getElementById("legend-boxes");
    if (!legendBoxes) return;
    legendBoxes.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.style.width = "100%";

    const gradientBar = document.createElement("div");
    gradientBar.style.height = "16px";
    gradientBar.style.width = "100%";
    gradientBar.style.borderRadius = "4px";
    
    const steps = 5;
    const stops = [];
    for (let i = 0; i <= steps; i++) {
        const fraction = i / steps;
        const hue = config.minHue + fraction * (config.maxHue - config.minHue);
        stops.push(`hsl(${hue}, 85%, 45%) ${fraction * 100}%`);
    }
    gradientBar.style.background = `linear-gradient(to right, ${stops.join(", ")})`;
    gradientBar.style.marginBottom = "6px";

    const labelContainer = document.createElement("div");
    labelContainer.style.display = "flex";
    labelContainer.style.justifyContent = "space-between";
    labelContainer.style.fontSize = "0.8rem";
    
    const printMin = Number(minVal).toFixed(1);
    const printMax = Number(maxVal).toFixed(1);

    labelContainer.innerHTML = `
        <span>Min: <b>${printMin}${config.unit}</b></span>
        <span>Max: <b>${printMax}${config.unit}</b></span>
    `;

    wrapper.appendChild(gradientBar);
    wrapper.appendChild(labelContainer);
    legendBoxes.appendChild(wrapper);

    const containerHeader = document.getElementById("legend-container").querySelector("h3");
    if (containerHeader) containerHeader.textContent = `Legenda: ${config.title}`;
}

function displayLocationDetails(regionName, data) {
    document.getElementById("info-placeholder").classList.add("hidden");
    document.getElementById("info-data").classList.remove("hidden");
    document.getElementById("powiat-name").textContent = regionName;

    const ringStroke = document.getElementById("aqi-ring-stroke");
    const levelText = document.getElementById("aqi-level-text");

    if(!data) {
        document.getElementById("val-aqi").textContent = "-";
        if (ringStroke) ringStroke.style.strokeDashoffset = 251.2;
        if (levelText) {
            levelText.textContent = "Brak Danych";
            levelText.style.color = "var(--text-muted)";
        }
        document.getElementById("val-pm25").textContent = "-";
        document.getElementById("val-pm10").textContent = "-";
        document.getElementById("val-temp").textContent = "-";
        document.getElementById("val-humidity").textContent = "-";
        document.getElementById("val-pressure").textContent = "-";
        document.getElementById("val-wind").textContent = "-";
        document.querySelector("#data-timestamp span").textContent = "Czas danych: -";
        return;
    }

    const hasAqi = data.aqi !== null && data.aqi !== undefined;
    if (hasAqi) {
        document.getElementById("val-aqi").textContent = data.aqi;
        if (ringStroke) {
            const maxVal = COLOR_CONFIG.aqi.maxVal; // 150
            const percentage = Math.min(1.0, Math.max(0.0, data.aqi / maxVal));
            const offset = 251.2 - (percentage * 251.2);
            ringStroke.style.strokeDashoffset = offset;
            ringStroke.style.stroke = getContinuousColor(data.aqi, COLOR_CONFIG.aqi.minVal, COLOR_CONFIG.aqi.maxVal, COLOR_CONFIG.aqi);
        }

        if (levelText) {
            let label = "Dobra";
            let color = "#10b981"; // green
            if (data.aqi > 150) {
                label = "Bardzo Zła";
                color = "#ef4444"; // red
            } else if (data.aqi > 100) {
                label = "Niezdrowa";
                color = "#f97316"; // orange
            } else if (data.aqi > 50) {
                label = "Umiarkowana";
                color = "#f59e0b"; // yellow
            }
            levelText.textContent = label;
            levelText.style.color = color;
        }
    } else {
        document.getElementById("val-aqi").textContent = "-";
        if (ringStroke) ringStroke.style.strokeDashoffset = 251.2;
        if (levelText) {
            levelText.textContent = "Brak";
            levelText.style.color = "var(--text-muted)";
        }
    }

    const fmt = (v, suffix) => (v !== null && v !== undefined) ? `${v}${suffix}` : "-";
    document.getElementById("val-pm25").textContent = fmt(data.pm25, " µg/m³");
    document.getElementById("val-pm10").textContent = fmt(data.pm10, " µg/m³");
    document.getElementById("val-temp").textContent = fmt(data.temperature, " °C");
    document.getElementById("val-humidity").textContent = fmt(data.humidity, " %");
    document.getElementById("val-pressure").textContent = fmt(data.pressure, " hPa");
    document.getElementById("val-wind").textContent = fmt(data.wind_speed, " m/s");

    const timestamp = data.weather_last_measurement || data.measurement_date || data.forecast_date || "Teraz";
    const formattedTime = timestamp.replace('T', ' ').replace('Z', '').split('.')[0];
    document.querySelector("#data-timestamp span").textContent = `Czas danych: ${formattedTime}`;

    if (window.lucide) lucide.createIcons();
}

function initControls() {
    document.getElementById("btn-live").addEventListener("click", () => {
        currentTimeMode = "live";
        document.getElementById("time-slider").classList.add("hidden");
        document.getElementById("selected-time-display").classList.add("hidden");
        updateTimeButtonState("btn-live");
        checkConnectionAndLoad();
    });
    
    document.getElementById("btn-forecast").addEventListener("click", () => {
        currentTimeMode = "forecast";
        setupTimeSlider(0, 24, 0); 
        updateTimeButtonState("btn-forecast");
        
        if (currentFactor === "aqi") {
            currentFactor = "temperature";
            const selector = document.getElementById("layer-selector");
            if (selector) selector.value = "temperature";
        }
        
        loadSliderData(0);
    });

    document.getElementById("btn-history").addEventListener("click", () => {
        currentTimeMode = "history";
        setupTimeSlider(-168, 0, -24); 
        updateTimeButtonState("btn-history");
        loadSliderData(-24);
    });

    const slider = document.getElementById("time-slider");
    slider.addEventListener("input", (e) => loadSliderData(parseInt(e.target.value)));
}

function setupTimeSlider(min, max, value) {
    const slider = document.getElementById("time-slider");
    const display = document.getElementById("selected-time-display");
    slider.classList.remove("hidden"); display.classList.remove("hidden");
    slider.min = min; slider.max = max; slider.value = value;
}

function updateTimeButtonState(activeId) {
    document.querySelectorAll(".time-btn").forEach(btn => btn.classList.remove("active"));
    document.getElementById(activeId).classList.add("active");
}

function loadSliderData(offsetHours) {
    const display = document.getElementById("selected-time-display");
    if (currentTimeMode === "forecast") {
        display.textContent = `Wybrana prognoza: +${offsetHours}h`;
        loadTimelineState(offsetHours, "forecast");
    } else if (currentTimeMode === "history") {
        const days = Math.abs(Math.floor(offsetHours / 24));
        const hours = Math.abs(offsetHours % 24);
        display.textContent = `Wybrany czas: ${days} dni ${hours}h wstecz`;
        loadTimelineState(offsetHours, "history");
    }
}

async function loadTimelineState(offsetHours, type) {
    const loadingBar = document.getElementById("loading-bar");
    if (loadingBar) loadingBar.classList.remove("hidden");

    const targetDate = new Date();
    targetDate.setHours(targetDate.getHours() + offsetHours);

    const endpoint = type === "forecast" ? "dashboard/forecast" : "dashboard/history";
    const url = `${API_URL}/${endpoint}?time=${targetDate.toISOString()}`;

    try {
        const res = await fetch(url);
        const json = await res.json();
        
        currentData = json.data || json;
        updateVisualization();
    } catch (err) {
        console.error(`Błąd podczas pobierania stanu osi czasu (${type}):`, err);
    } finally {
        if (loadingBar) loadingBar.classList.add("hidden");
    }
}