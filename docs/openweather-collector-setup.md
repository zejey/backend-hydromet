# OpenWeather Current Weather Collector – Setup Guide

This document explains how to configure and verify the automated hourly
OpenWeather current weather collection feature.

## Overview

A FastAPI internal endpoint (`POST /internal/collect/openweather`) fetches
current weather data from the OpenWeather API and upserts it into the
`openweather_observations` Postgres table.  A GitHub Actions workflow calls
this endpoint on an hourly schedule.

---

## Environment Variables

### Required (Railway)

| Variable | Description |
|---|---|
| `OPENWEATHER_API_KEY` | Your OpenWeather API key |
| `DATABASE_URL` | Postgres connection string (Railway internal URL recommended) |
| `INTERNAL_COLLECTOR_TOKEN` | Shared secret used to authenticate the internal endpoint |

### Optional (Railway) – defaults to San Pedro, Laguna, PH

| Variable | Default | Description |
|---|---|---|
| `OPENWEATHER_LAT` | `14.3597` | Latitude of the collection point |
| `OPENWEATHER_LON` | `121.0583` | Longitude of the collection point |
| `OPENWEATHER_CITY_NAME` | `San Pedro, Laguna, PH` | Fallback city name if the API returns a different name |

---

## Step 1 – Add secrets to Railway

1. Open your Railway project and select the backend service.
2. Go to **Variables**.
3. Add each required variable listed above.  Generate a long random value for
   `INTERNAL_COLLECTOR_TOKEN` (e.g. `openssl rand -hex 32`).
4. Redeploy the service so the new variables take effect.

---

## Step 2 – Add the secret to GitHub Actions

1. Open the GitHub repository and go to **Settings → Secrets and variables →
   Actions**.
2. Click **New repository secret**.
3. Name: `INTERNAL_COLLECTOR_TOKEN`  
   Value: the same token you set in Railway.

---

## Step 3 – Verify the endpoint manually

```bash
curl -X POST \
  -H "X-Internal-Token: <your-token>" \
  https://caring-kindness-production.up.railway.app/internal/collect/openweather
```

A successful response looks like:

```json
{
  "success": true,
  "dt": 1700000000,
  "dt_hour": 1699999200,
  "lat": 14.3597,
  "lon": 121.0583,
  "city_name": "San Roque",
  "weather_id": 802,
  "weather_main": "Clouds",
  "temp": 28.5,
  "humidity": 74
}
```

> **Note:** The city name returned by the provider may be *San Roque*; this is
> expected and the fallback name is used only when the provider returns an empty
> string.

---

## Step 4 – Verify data in Postgres

Connect to the Railway Postgres instance and run:

```sql
SELECT dt_hour, city_name, weather_main, temp, humidity, inserted_at
FROM openweather_observations
ORDER BY dt_hour DESC
LIMIT 10;
```

---

## GitHub Actions Schedule

The workflow file is at `.github/workflows/openweather-collector.yml`.  It runs
automatically at the top of every hour (`cron: '0 * * * *'`).  You can also
trigger it manually from the **Actions** tab → **OpenWeather Current Collector**
→ **Run workflow**.

### Workflow failure behaviour

If the endpoint returns a non-2xx HTTP status the workflow step fails and
GitHub marks the run as failed.  You will receive the usual GitHub Actions
failure notification.

---

## Table schema

The `openweather_observations` table is created automatically on first run:

| Column | Type | Description |
|---|---|---|
| `id` | SERIAL | Auto-increment primary key |
| `dt` | BIGINT | Original Unix timestamp from OpenWeather |
| `dt_hour` | BIGINT | `dt` bucketed to the start of the hour (`dt - dt % 3600`) |
| `lat` | DOUBLE PRECISION | Collection latitude |
| `lon` | DOUBLE PRECISION | Collection longitude |
| `city_name` | TEXT | City name (provider or fallback) |
| `country` | TEXT | Country code |
| `weather_id` | INTEGER | OpenWeather condition code |
| `weather_main` | TEXT | e.g. `Clouds`, `Rain` |
| `weather_description` | TEXT | e.g. `scattered clouds` |
| `weather_icon` | TEXT | OpenWeather icon code |
| `temp` | DOUBLE PRECISION | Temperature (°C) |
| `feels_like` | DOUBLE PRECISION | Feels-like temperature (°C) |
| `temp_min` | DOUBLE PRECISION | Min temperature (°C) |
| `temp_max` | DOUBLE PRECISION | Max temperature (°C) |
| `pressure` | INTEGER | Atmospheric pressure (hPa) |
| `humidity` | INTEGER | Humidity (%) |
| `visibility` | INTEGER | Visibility (m) |
| `wind_speed` | DOUBLE PRECISION | Wind speed (m/s) |
| `wind_deg` | INTEGER | Wind direction (°) |
| `wind_gust` | DOUBLE PRECISION | Wind gust (m/s) |
| `clouds_all` | INTEGER | Cloudiness (%) |
| `rain_1h` | DOUBLE PRECISION | Rain volume last 1 h (mm) |
| `snow_1h` | DOUBLE PRECISION | Snow volume last 1 h (mm) |
| `sunrise` | BIGINT | Sunrise Unix timestamp |
| `sunset` | BIGINT | Sunset Unix timestamp |
| `inserted_at` | TIMESTAMPTZ | Row insert/update timestamp |

The unique constraint `uq_openweather_dt_hour_lat_lon` on `(dt_hour, lat, lon)`
prevents duplicate rows for the same hour and location.
