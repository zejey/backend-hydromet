import os
import json
import urllib.request
from datetime import datetime, timezone

import psycopg2


OPENWEATHER_LAT = float(os.getenv("OPENWEATHER_LAT", "14.3644"))
OPENWEATHER_LON = float(os.getenv("OPENWEATHER_LON", "121.0619"))
OPENWEATHER_CITY_NAME = os.getenv("OPENWEATHER_CITY_NAME", "San Pedro, Laguna, PH")


def fetch_current_weather(api_key: str, lat: float, lon: float) -> dict:
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "backend-hydromet/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_row(payload: dict, fallback_city: str, lat: float, lon: float) -> dict:
    weather0 = (payload.get("weather") or [{}])[0] or {}
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    clouds = payload.get("clouds") or {}
    rain = payload.get("rain") or {}
    snow = payload.get("snow") or {}

    # OpenWeather "dt" is unix seconds
    dt = int(payload["dt"])
    dt = dt - (dt % 3600)

    row = {
        "dt": dt,
        "city_name": payload.get("name") or fallback_city,
        "lat": float(payload.get("coord", {}).get("lat", lat)),
        "lon": float(payload.get("coord", {}).get("lon", lon)),

        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "temp_min": main.get("temp_min"),
        "temp_max": main.get("temp_max"),

        # Not provided by Current Weather endpoint; keep null unless you compute it.
        "dew_point": None,

        "pressure": main.get("pressure"),
        "sea_level": main.get("sea_level"),
        "grnd_level": main.get("grnd_level"),
        "humidity": main.get("humidity"),
        "visibility": payload.get("visibility"),

        "wind_speed": wind.get("speed"),
        "wind_deg": wind.get("deg"),
        "wind_gust": wind.get("gust"),

        # These keys appear depending on conditions
        "rain_1h": rain.get("1h"),
        "rain_3h": rain.get("3h"),
        "snow_1h": snow.get("1h"),
        "snow_3h": snow.get("3h"),

        "clouds_all": clouds.get("all"),

        "weather_id": weather0.get("id"),
        "weather_main": weather0.get("main"),
        "weather_description": weather0.get("description"),
        "weather_icon": weather0.get("icon"),

        # DB default handles synced_at; but okay to set explicitly if you prefer:
        # "synced_at": datetime.now(timezone.utc),
        "data_source": "openweather",
    }
    return row


def ensure_table(conn):
    # Optional: create table if missing (safe to run every time).
    # If you prefer migrations, you can delete this and run SQL manually once.
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
    cols = list(row.keys())
    values = [row[c] for c in cols]

    col_sql = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))

    # Update everything except the conflict key; keep synced_at fresh
    non_key_cols = [c for c in cols if c not in ("dt", "lat", "lon")]
    set_sql = ", ".join([f"{c} = EXCLUDED.{c}" for c in non_key_cols])
    if set_sql:
        set_sql += ", synced_at = CURRENT_TIMESTAMP"
    else:
        set_sql = "synced_at = CURRENT_TIMESTAMP"

    sql = f"""
    INSERT INTO openweather_observations ({col_sql})
    VALUES ({placeholders})
    ON CONFLICT (dt, lat, lon) DO UPDATE
    SET {set_sql};
    """

    with conn.cursor() as cur:
        cur.execute(sql, values)
    conn.commit()


def main():
    api_key = os.getenv("OPENWEATHER_API_KEY")
    db_url = os.getenv("DATABASE_URL")

    if not api_key:
        raise RuntimeError("Missing env var: OPENWEATHER_API_KEY")
    if not db_url:
        raise RuntimeError("Missing env var: DATABASE_URL")

    payload = fetch_current_weather(api_key, OPENWEATHER_LAT, OPENWEATHER_LON)
    row = to_row(payload, OPENWEATHER_CITY_NAME, OPENWEATHER_LAT, OPENWEATHER_LON)

    # Simple log (helpful in Railway logs)
    dt = row["dt"]
    dt_iso = datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
    print(f"[collector] fetched dt={dt} ({dt_iso}) temp={row.get('temp')} rain_1h={row.get('rain_1h')} weather_id={row.get('weather_id')}")

    conn = psycopg2.connect(db_url)
    try:
        ensure_table(conn)
        upsert_row(conn, row)
        print("[collector] upsert ok")
    finally:
        conn.close()


if __name__ == "__main__":
    main()