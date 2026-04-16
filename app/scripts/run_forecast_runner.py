#!/usr/bin/env python
"""
Manual script to invoke the forecast runner locally for testing.

Usage:
    # Run for all users
    python scripts/run_forecast_runner.py

    # Run for a single test user
    python scripts/run_forecast_runner.py --user-id <user_uuid>

    # Dry-run: analyze hazards only (no DB writes / SMS sends)
    python scripts/run_forecast_runner.py --dry-run

Required environment variables (set in .env or shell):
    OPENWEATHER_API_KEY   - OpenWeather API key
    DATABASE_URL          - PostgreSQL connection string (or PG* vars)
    SEMAPHORE_API_KEY     - Semaphore SMS API key (optional for dry-run)

Optional:
    FORECAST_DEFAULT_LAT  - Latitude  (default: 14.3597)
    FORECAST_DEFAULT_LON  - Longitude (default: 121.0583)
    FORECAST_DEDUPE_HOURS - Deduplication window in hours (default: 6)
    OPENWEATHER_CITY_NAME - Location label in notifications
"""

import argparse
import json
import logging
import os
import sys

# Ensure project root is on the path so app.* imports work.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run the forecast alert pipeline manually.")
    parser.add_argument(
        "--user-id",
        metavar="USER_ID",
        default=None,
        help="Restrict to a single user (test mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze forecast and print hazards without writing to DB or sending SMS.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    if not api_key:
        logger.error("OPENWEATHER_API_KEY is not set. Exiting.")
        sys.exit(1)

    lat = float(os.environ.get("FORECAST_DEFAULT_LAT", os.environ.get("OPENWEATHER_LAT", "14.3597")))
    lon = float(os.environ.get("FORECAST_DEFAULT_LON", os.environ.get("OPENWEATHER_LON", "121.0583")))
    location = os.environ.get("OPENWEATHER_CITY_NAME", "San Pedro, Laguna, PH")

    print("\n" + "=" * 60)
    print("HYDROMET FORECAST RUNNER - MANUAL TEST")
    print("=" * 60)
    print(f"  Location : {location} ({lat}, {lon})")
    print(f"  Scope    : {'user:' + args.user_id if args.user_id else 'all'}")
    print(f"  Dry-run  : {args.dry_run}")
    print("=" * 60 + "\n")

    from app.services.forecast_runner import fetch_forecast, analyze_forecast

    logger.info("Fetching OpenWeather forecast …")
    forecast_data = fetch_forecast(api_key, lat, lon, cnt=8)
    city_info = forecast_data.get("city", {})
    logger.info(f"Forecast city: {city_info.get('name', '?')}, items: {len(forecast_data.get('list', []))}")

    logger.info("Analyzing forecast for hazards …")
    hazards = analyze_forecast(forecast_data)

    if not hazards:
        print("✅ No hazards detected in the forecast window.")
    else:
        print(f"⚠️  {len(hazards)} hazard(s) detected:\n")
        for h in hazards:
            print(
                f"  • {h['hazard']:<15}  severity={h['severity']:<8}  "
                f"prob={h['probability']:.0%}  horizon={h['horizon_h']}h  "
                f"({h['weather_main']} – {h['description']})"
            )
        print()

    if args.dry_run:
        print("ℹ️  Dry-run mode: skipping DB writes and SMS sends.\n")
        sys.exit(0)

    logger.info("Running full forecast pipeline …")
    from app.services.forecast_runner import run_forecast

    result = run_forecast(test_user_id=args.user_id)

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    print("=" * 60 + "\n")

    if result.get("success"):
        print("✅ Forecast run completed successfully.")
    else:
        print("❌ Forecast run encountered errors.")
        sys.exit(1)


if __name__ == "__main__":
    main()