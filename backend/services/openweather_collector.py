"""
OpenWeather current weather collector service (minimal schema).

- Fetches current weather from OpenWeather /weather endpoint (metric units).
- Buckets payload dt to the start of the hour and stores it in `dt`.
- Upserts into openweather_observations with UNIQUE(dt, lat, lon).

This intentionally only uses a minimal column set so it works even if the
table was created earlier without optional fields like country/sunrise/sunset.
"""

import os

import psycopg2
import requests

OPENWEATHER_API_BASE = "https://api.openweathermap.org/data/2.5/weather"


def fetch_current_weather(api_key: str, lat: float, lon: float) -> dict:
    url = f"{OPENWEATHER_API_BASE}?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def to_row(payload: dict, fallback_city: str, lat: float, lon: float) -> dict:
    dt_raw = int(payload["dt"])
    dt_bucket = dt_raw - (dt_raw % 3600)

    weather0 = (payload.get("weather") or [{}])[0] or {}
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    clouds = payload.get("clouds") or {}
    rain = payload.get("rain") or {}
    snow = payload.get("snow") or {}

    coord = payload.get("coord") or {}

    return {
        "dt": dt_bucket,
        "city_name": payload.get("name") or fallback_city,
        "lat": float(coord.get("lat", lat)),
        "lon": float(coord.get("lon", lon)),

        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "temp_min": main.get("temp_min"),
        "temp_max": main.get("temp_max"),
        "dew_point": None,  # not available on /weather

        "pressure": main.get("pressure"),
        "sea_level": main.get("sea_level"),
        "grnd_level": main.get("grnd_level"),
        "humidity": main.get("humidity"),
        "visibility": payload.get("visibility"),

        "wind_speed": wind.get("speed"),
        "wind_deg": wind.get("deg"),
        "wind_gust": wind.get("gust"),

        "rain_1h": rain.get("1h"),
        "rain_3h": rain.get("3h"),
        "snow_1h": snow.get("1h"),
        "snow_3h": snow.get("3h"),

        "clouds_all": clouds.get("all"),

        "weather_id": weather0.get("id"),
        "weather_main": weather0.get("main"),
        "weather_description": weather0.get("description"),
        "weather_icon": weather0.get("icon"),

        "data_source": "openweather",
    }


def ensure_table(conn) -> None:
    # Minimal schema (matches what you initially created)
    ddl = """
    CREATE TABLE IF NOT EXISTS openweather_observations (
      id SERIAL PRIMARY KEY,
      dt BIGINT NOT NULL,
      city_name TEXT,
      lat DOUBLE PRECISION NOT NULL,
      lon DOUBLE PRECISION NOT NULL,

      temp DOUBLE PRECISION,
      feels_like DOUBLE PRECISION,
      temp_min DOUBLE PRECISION,
      temp_max DOUBLE PRECISION,
      dew_point DOUBLE PRECISION,

      pressure DOUBLE PRECISION,
      sea_level DOUBLE PRECISION,
      grnd_level DOUBLE PRECISION,
      humidity DOUBLE PRECISION,
      visibility DOUBLE PRECISION,

      wind_speed DOUBLE PRECISION,
      wind_deg DOUBLE PRECISION,
      wind_gust DOUBLE PRECISION,

      rain_1h DOUBLE PRECISION,
      rain_3h DOUBLE PRECISION,
      snow_1h DOUBLE PRECISION,
      snow_3h DOUBLE PRECISION,

      clouds_all DOUBLE PRECISION,

      weather_id INTEGER,
      weather_main TEXT,
      weather_description TEXT,
      weather_icon TEXT,

      synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      data_source VARCHAR(50) DEFAULT 'openweather',

      UNIQUE (dt, lat, lon)
    );

    CREATE INDEX IF NOT EXISTS idx_openweather_dt ON openweather_observations(dt);
    CREATE INDEX IF NOT EXISTS idx_openweather_lat_lon_dt ON openweather_observations(lat, lon, dt);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def upsert_row(conn, row: dict) -> None:
    sql = """
    INSERT INTO openweather_observations (
      dt, city_name, lat, lon,
      temp, feels_like, temp_min, temp_max, dew_point,
      pressure, sea_level, grnd_level, humidity, visibility,
      wind_speed, wind_deg, wind_gust,
      rain_1h, rain_3h, snow_1h, snow_3h,
      clouds_all,
      weather_id, weather_main, weather_description, weather_icon,
      data_source
    ) VALUES (
      %(dt)s, %(city_name)s, %(lat)s, %(lon)s,
      %(temp)s, %(feels_like)s, %(temp_min)s, %(temp_max)s, %(dew_point)s,
      %(pressure)s, %(sea_level)s, %(grnd_level)s, %(humidity)s, %(visibility)s,
      %(wind_speed)s, %(wind_deg)s, %(wind_gust)s,
      %(rain_1h)s, %(rain_3h)s, %(snow_1h)s, %(snow_3h)s,
      %(clouds_all)s,
      %(weather_id)s, %(weather_main)s, %(weather_description)s, %(weather_icon)s,
      %(data_source)s
    )
    ON CONFLICT (dt, lat, lon) DO UPDATE SET
      city_name = EXCLUDED.city_name,
      temp = EXCLUDED.temp,
      feels_like = EXCLUDED.feels_like,
      temp_min = EXCLUDED.temp_min,
      temp_max = EXCLUDED.temp_max,
      dew_point = EXCLUDED.dew_point,
      pressure = EXCLUDED.pressure,
      sea_level = EXCLUDED.sea_level,
      grnd_level = EXCLUDED.grnd_level,
      humidity = EXCLUDED.humidity,
      visibility = EXCLUDED.visibility,
      wind_speed = EXCLUDED.wind_speed,
      wind_deg = EXCLUDED.wind_deg,
      wind_gust = EXCLUDED.wind_gust,
      rain_1h = EXCLUDED.rain_1h,
      rain_3h = EXCLUDED.rain_3h,
      snow_1h = EXCLUDED.snow_1h,
      snow_3h = EXCLUDED.snow_3h,
      clouds_all = EXCLUDED.clouds_all,
      weather_id = EXCLUDED.weather_id,
      weather_main = EXCLUDED.weather_main,
      weather_description = EXCLUDED.weather_description,
      weather_icon = EXCLUDED.weather_icon,
      data_source = EXCLUDED.data_source,
      synced_at = CURRENT_TIMESTAMP;
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)
    conn.commit()


def run_collection() -> dict:
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
        "lat": row["lat"],
        "lon": row["lon"],
        "city_name": row["city_name"],
        "weather_id": row["weather_id"],
        "weather_main": row["weather_main"],
        "temp": row["temp"],
        "humidity": row["humidity"],
    }