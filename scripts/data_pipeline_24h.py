"""
WeatherLink 24h incremental data collection.
Run daily via cron to accumulate historical data.
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import requests
from database import DatabaseManager
from logger_util import get_logger

load_dotenv()
logger = get_logger(__name__)

class WeatherLink24hClient:
    """Client for WeatherLink 24h Historic API."""
    
    BASE_URL = "https://api.weatherlink.com/v2/historic"
    
    def __init__(self):
        self.api_key = os.getenv("WEATHERLINK_API_KEY")
        self.api_secret = os.getenv("WEATHERLINK_API_SECRET")
        self.station_id = os.getenv("WEATHERLINK_STATION_ID")
        self.lsid = int(os.getenv("WEATHERLINK_LSID"))
        
        if not all([self.api_key, self.api_secret, self.station_id]):
            raise ValueError("WeatherLink credentials missing in .env")
    
    def fetch_last_24h(self):
        """Fetch last 24 hours of data."""
        end_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - (24 * 3600)
        
        url = f"{self.BASE_URL}/{self.station_id}"
        params = {
            "api-key": self.api_key,
            "start-timestamp": start_ts,
            "end-timestamp": end_ts,
        }
        headers = {"x-api-secret": self.api_secret}
        
        logger.info(f"Fetching 24h data: {datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M')} "
                   f"to {datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M')}")
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        
        payload = response.json()
        
        sensor = next(
            (s for s in payload.get("sensors", []) if int(s.get("lsid", -1)) == self.lsid),
            None
        )
        
        if not sensor:
            logger.error(f"Sensor LSID {self.lsid} not found")
            return []
        
        records = sensor.get("data", [])
        logger.info(f"Retrieved {len(records)} observations")
        
        return records

class DataPipeline24h:
    """Pipeline for incremental 24h data collection."""
    
    def __init__(self):
        self.client = WeatherLink24hClient()
        self.db = DatabaseManager()
    
    def setup(self):
        """Initialize database tables."""
        logger.info("Initializing database schema...")
        self.db.create_tables()
        logger.info("✅ Database ready")
    
    def collect_daily(self):
        """Fetch and store last 24h of data."""
        logger.info("=" * 70)
        logger.info(f"Daily data collection: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info("=" * 70)
        
        try:
            # Fetch from API
            records = self.client.fetch_last_24h()
            
            if not records:
                logger.warning("No records retrieved from API")
                return 0
            
            # Add station/lsid info to each record
            for record in records:
                record['station_id'] = self.client.station_id
                record['lsid'] = self.client.lsid
            
            logger.info(f"Processing {len(records)} records")
            
            # Insert into database (no normalization, all fields)
            inserted = self.db.insert_observations(records)
            logger.info(f"✅ Inserted {inserted} new observations (attempted {len(records)})")
            
            # Show stats
            self.get_statistics()
            
            return inserted
            
        except Exception as e:
            logger.error(f"❌ Collection failed: {e}", exc_info=True)
            return 0
    
    def get_statistics(self):
        """Show database statistics."""
        count = self.db.get_observation_count()
        latest_ts = self.db.get_latest_timestamp()
        
        logger.info("-" * 70)
        logger.info(f"Database Statistics:")
        logger.info(f"  Total observations: {count}")
        
        if latest_ts:
            latest_dt = datetime.fromtimestamp(latest_ts)
            age_hours = (datetime.now(timezone.utc).timestamp() - latest_ts) / 3600
            days_of_data = count / 96  # Assuming ~96 readings per day (15-min intervals)
            
            logger.info(f"  Latest record: {latest_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            logger.info(f"  Data freshness: {age_hours:.1f} hours ago")
            logger.info(f"  Estimated days of data: {days_of_data:.1f} days")
            
            if days_of_data >= 7:
                logger.warning(f"✅ Ready to train model! ({days_of_data:.1f} days of data)")
        
        logger.info("-" * 70)
    
    def export_training_data(self, output_path="training_data.csv", days=None):
        """Export all data to CSV for model training."""
        if days:
            end_ts = int(datetime.now(timezone.utc).timestamp())
            start_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
            logger.info(f"Exporting last {days} days to {output_path}")
            self.db.export_to_csv(output_path, start_ts, end_ts)
        else:
            logger.info(f"Exporting all data to {output_path}")
            self.db.export_to_csv(output_path)
        
        logger.info(f"✅ Export complete")
    
    def close(self):
        """Clean up."""
        self.db.close_all()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="24h incremental weather data collection")
    parser.add_argument("--setup", action="store_true", help="Initialize database schema")
    parser.add_argument("--collect", action="store_true", help="Fetch and store last 24h")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    parser.add_argument("--export", type=str, help="Export to CSV file")
    parser.add_argument("--export-days", type=int, help="Export last N days only")
    
    args = parser.parse_args()
    
    pipeline = DataPipeline24h()
    
    try:
        if args.setup:
            pipeline.setup()
        
        if args.collect:
            pipeline.collect_daily()
        
        if args.stats:
            pipeline.get_statistics()
        
        if args.export:
            pipeline.export_training_data(args.export, args.export_days)
    
    finally:
        pipeline.close()

if __name__ == "__main__":
    main()