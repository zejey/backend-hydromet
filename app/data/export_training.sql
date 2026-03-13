COPY (
  WITH unified AS (
    SELECT
      (dt - (dt % 3600))::bigint AS dt,
      city_name,
      lat, lon,
      temp, feels_like, temp_min, temp_max, dew_point,
      pressure, sea_level, grnd_level, humidity, visibility,
      wind_speed,
      wind_deg::double precision AS wind_deg,
      wind_gust,
      rain_1h, rain_3h, snow_1h, snow_3h,
      clouds_all,
      weather_id, weather_main, weather_description, weather_icon,
      COALESCE(data_source, 'openweather') AS data_source,
      0 AS source_priority,
      synced_at::timestamptz AS synced_at
    FROM openweather_observations_staging

    UNION ALL

    SELECT
      (dt - (dt % 3600))::bigint AS dt,
      city_name,
      lat, lon,
      temp, feels_like, temp_min, temp_max, dew_point,
      pressure, sea_level, grnd_level, humidity, visibility,
      wind_speed,
      wind_deg::double precision AS wind_deg,
      wind_gust,
      rain_1h, rain_3h, snow_1h, snow_3h,
      clouds_all,
      weather_id, weather_main, weather_description, weather_icon,
      COALESCE(data_source, 'openweather') AS data_source,
      1 AS source_priority,
      synced_at
    FROM openweather_observations
  ),
  deduped AS (
    SELECT DISTINCT ON (dt)
      dt,
      city_name,
      lat, lon,
      temp, feels_like, temp_min, temp_max, dew_point,
      pressure, sea_level, grnd_level, humidity, visibility,
      wind_speed, wind_deg, wind_gust,
      rain_1h, rain_3h, snow_1h, snow_3h,
      clouds_all,
      weather_id, weather_main, weather_description, weather_icon,
      data_source,
      source_priority,
      synced_at
    FROM unified
    ORDER BY dt, source_priority DESC, synced_at DESC
  )
  SELECT
    dt,
    city_name,
    lat, lon,
    temp, feels_like, temp_min, temp_max, dew_point,
    pressure, sea_level, grnd_level, humidity, visibility,
    wind_speed, wind_deg, wind_gust,
    rain_1h, rain_3h, snow_1h, snow_3h,
    clouds_all,
    weather_id, weather_main, weather_description, weather_icon,
    data_source
  FROM deduped
  ORDER BY dt ASC
) TO STDOUT WITH CSV HEADER;