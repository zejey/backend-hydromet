"""
OpenWeather current weather collector service.

Fetches current weather from OpenWeather API and upserts into the
openweather_observations Postgres table with hourly dt bucketing.
"""

import os
import requests
import psycopg2

OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5/weather"


def fetch_current_weather(api_key: str, lat: float, lon: float) -> dict:
    """Fetch current weather from OpenWeather API."""
    url = (
        f"{OPENWEATHER_API_BASE}"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def to_row(payload: dict, fallback_city: str, lat: float, lon: float) -> dict:
    """
    Convert OpenWeather API payload to a DB row dict.

    dt is bucketed to the start of the hour: dt_hour = dt - dt % 3600
    """
    dt_raw = int(payload["dt"])
    dt_hour = dt_raw - (dt_raw % 3600)

    weather = payload.get("weather", [{}])[0]
    main = payload.get("main", {})
    wind = payload.get("wind", {})
    clouds = payload.get("clouds", {})
    rain = payload.get("rain", {})
    snow = payload.get("snow", {})
    sys = payload.get("sys", {})

    return {
        "dt": dt_hour,
        "lat": lat,
        "lon": lon,
        "city_name": payload.get("name") or fallback_city,
        "country": sys.get("country"),
        "weather_id": weather.get("id"),
        "weather_main": weather.get("main"),
        "weather_description": weather.get("description"),
        "weather_icon": weather.get("icon"),
        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "temp_min": main.get("temp_min"),
        "temp_max": main.get("temp_max"),
        "pressure": main.get("pressure"),
        "humidity": main.get("humidity"),
        "visibility": payload.get("visibility"),
        "wind_speed": wind.get("speed"),
        "wind_deg": wind.get("deg"),
        "wind_gust": wind.get("gust"),
        "clouds_all": clouds.get("all"),
        "rain_1h": rain.get("1h"),
        "snow_1h": snow.get("1h"),
        "sunrise": sys.get("sunrise"),
        "sunset": sys.get("sunset"),
    }


def ensure_table(conn) -> None:
    """Create openweather_observations table and indexes if they do not exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS openweather_observations (
                id            SERIAL PRIMARY KEY,
                dt            BIGINT NOT NULL,
                dt_hour       BIGINT NOT NULL,
                lat           DOUBLE PRECISION NOT NULL,
                lon           DOUBLE PRECISION NOT NULL,
                city_name     TEXT,
                country       TEXT,
                weather_id    INTEGER,
                weather_main  TEXT,
                weather_description TEXT,
                weather_icon  TEXT,
                temp          DOUBLE PRECISION,
                feels_like    DOUBLE PRECISION,
                temp_min      DOUBLE PRECISION,
                temp_max      DOUBLE PRECISION,
                pressure      INTEGER,
                humidity      INTEGER,
                visibility    INTEGER,
                wind_speed    DOUBLE PRECISION,
                wind_deg      INTEGER,
                wind_gust     DOUBLE PRECISION,
                clouds_all    INTEGER,
                rain_1h       DOUBLE PRECISION,
                snow_1h       DOUBLE PRECISION,
                sunrise       BIGINT,
                sunset        BIGINT,
                inserted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_openweather_dt_hour_lat_lon
                    UNIQUE (dt_hour, lat, lon)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_openweather_dt_hour
                ON openweather_observations (dt_hour DESC)
        """)
    conn.commit()


def upsert_row(conn, row: dict) -> None:
    """Insert or update a weather observation row (upsert on dt_hour, lat, lon)."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO openweather_observations (
                dt, dt_hour, lat, lon, city_name, country,
                weather_id, weather_main, weather_description, weather_icon,
                temp, feels_like, temp_min, temp_max, pressure, humidity,
                visibility, wind_speed, wind_deg, wind_gust, clouds_all,
                rain_1h, snow_1h, sunrise, sunset
            ) VALUES (
                %(dt)s, %(dt_hour)s, %(lat)s, %(lon)s, %(city_name)s, %(country)s,
                %(weather_id)s, %(weather_main)s, %(weather_description)s, %(weather_icon)s,
                %(temp)s, %(feels_like)s, %(temp_min)s, %(temp_max)s, %(pressure)s, %(humidity)s,
                %(visibility)s, %(wind_speed)s, %(wind_deg)s, %(wind_gust)s, %(clouds_all)s,
                %(rain_1h)s, %(snow_1h)s, %(sunrise)s, %(sunset)s
            )
            ON CONFLICT (dt_hour, lat, lon) DO UPDATE SET
                dt                  = EXCLUDED.dt,
                city_name           = EXCLUDED.city_name,
                country             = EXCLUDED.country,
                weather_id          = EXCLUDED.weather_id,
                weather_main        = EXCLUDED.weather_main,
                weather_description = EXCLUDED.weather_description,
                weather_icon        = EXCLUDED.weather_icon,
                temp                = EXCLUDED.temp,
                feels_like          = EXCLUDED.feels_like,
                temp_min            = EXCLUDED.temp_min,
                temp_max            = EXCLUDED.temp_max,
                pressure            = EXCLUDED.pressure,
                humidity            = EXCLUDED.humidity,
                visibility          = EXCLUDED.visibility,
                wind_speed          = EXCLUDED.wind_speed,
                wind_deg            = EXCLUDED.wind_deg,
                wind_gust           = EXCLUDED.wind_gust,
                clouds_all          = EXCLUDED.clouds_all,
                rain_1h             = EXCLUDED.rain_1h,
                snow_1h             = EXCLUDED.snow_1h,
                sunrise             = EXCLUDED.sunrise,
                sunset              = EXCLUDED.sunset,
                inserted_at         = NOW()
        """, row)
    conn.commit()


def run_collection() -> dict:
    """
    Read env vars, fetch current weather from OpenWeather, and upsert into DB.

    Required env vars:
        OPENWEATHER_API_KEY  - OpenWeather API key
        DATABASE_URL         - Postgres connection string

    Optional env vars (with defaults for San Pedro, Laguna, PH):
        OPENWEATHER_LAT        (default: 14.3597)
        OPENWEATHER_LON        (default: 121.0583)
        OPENWEATHER_CITY_NAME  (default: "San Pedro, Laguna, PH")

    Returns a summary dict suitable for the API response.
    """
    api_key = os.environ["OPENWEATHER_API_KEY"]
    database_url = os.environ["DATABASE_URL"]
    lat = float(os.getenv("OPENWEATHER_LAT", "14.3597"))
    lon = float(os.getenv("OPENWEATHER_LON", "121.0583"))
    fallback_city = os.getenv("OPENWEATHER_CITY_NAME", "San Pedro, Laguna, PH")

    payload = fetch_current_weather(api_key, lat, lon)
    row = to_row(payload, fallback_city, lat, lon)

    conn = psycopg2.connect(database_url)
    try:
        ensure_table(conn)
        upsert_row(conn, row)
    finally:
        conn.close()

    return {
        "dt": row["dt"],
        "dt_hour": row["dt_hour"],
        "lat": row["lat"],
        "lon": row["lon"],
        "city_name": row["city_name"],
        "weather_id": row["weather_id"],
        "weather_main": row["weather_main"],
        "temp": row["temp"],
        "humidity": row["humidity"],
    }