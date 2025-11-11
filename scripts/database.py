import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import execute_values
import os
from logger_util import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """Manage PostgreSQL connections and operations."""
    
    def __init__(self, min_conn=2, max_conn=10):
        self.connection_pool = SimpleConnectionPool(
            min_conn,
            max_conn,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "hydromet_db"),
            user=os.getenv("DB_USER", "weather_app"),
            password=os.getenv("DB_PASSWORD")
        )
        logger.info(f"Database pool created: {min_conn}-{max_conn} connections")
    
    def get_connection(self):
        """Get a connection from the pool."""
        return self.connection_pool.getconn()
    
    def return_connection(self, conn):
        """Return connection to the pool."""
        self.connection_pool.putconn(conn)
    
    def close_all(self):
        """Close all connections in the pool."""
        self.connection_pool.closeall()
        logger.info("Database pool closed")
    
    def create_tables(self):
        """Create weather_observations table with all WeatherLink historic API fields."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # SQL to create table - matches WeatherLink historic API
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS weather_observations (
                id SERIAL PRIMARY KEY,
                ts BIGINT NOT NULL UNIQUE,
                
                -- Station & Sensor Info
                station_id INTEGER,
                lsid INTEGER,
                tx_id INTEGER,
                
                -- Temperature Fields
                temp_last FLOAT,
                temp_hi FLOAT,
                temp_lo FLOAT,
                temp_avg FLOAT,
                temp_hi_at BIGINT,
                temp_lo_at BIGINT,
                
                -- Humidity Fields
                hum_last FLOAT,
                hum_hi FLOAT,
                hum_lo FLOAT,
                hum_hi_at BIGINT,
                hum_lo_at BIGINT,
                
                -- Heat Index
                heat_index_last FLOAT,
                heat_index_hi FLOAT,
                heat_index_hi_at BIGINT,
                
                -- Wind Chill
                wind_chill_last FLOAT,
                wind_chill_lo FLOAT,
                wind_chill_lo_at BIGINT,
                
                -- Wet Bulb
                wet_bulb_last FLOAT,
                wet_bulb_hi FLOAT,
                wet_bulb_lo FLOAT,
                wet_bulb_hi_at BIGINT,
                wet_bulb_lo_at BIGINT,
                
                -- Dew Point
                dew_point_last FLOAT,
                dew_point_hi FLOAT,
                dew_point_lo FLOAT,
                dew_point_hi_at BIGINT,
                dew_point_lo_at BIGINT,
                
                -- Wind Speed
                wind_speed_last FLOAT,
                wind_speed_hi FLOAT,
                wind_speed_avg FLOAT,
                wind_speed_hi_at BIGINT,
                
                -- Wind Direction
                wind_dir_last INTEGER,
                wind_dir_of_prevail INTEGER,
                wind_dir_of_avg INTEGER,
                wind_speed_hi_dir INTEGER,
                
                -- Wind Run
                wind_run FLOAT,
                
                -- Rainfall
                rainfall_mm FLOAT,
                rainfall_in FLOAT,
                rain_rate_hi_mm FLOAT,
                rain_rate_hi_in FLOAT,
                rain_rate_hi_at BIGINT,
                rain_size INTEGER,
                rainfall_clicks INTEGER,
                rain_rate_hi_clicks INTEGER,
                
                -- Solar & UV
                solar_rad_hi FLOAT,
                solar_rad_avg FLOAT,
                solar_energy FLOAT,
                solar_rad_hi_at BIGINT,
                uv_index_hi FLOAT,
                uv_index_avg FLOAT,
                uv_dose FLOAT,
                uv_index_hi_at BIGINT,
                
                -- THW/THSW Index
                thw_index_last FLOAT,
                thw_index_hi FLOAT,
                thw_index_lo FLOAT,
                thw_index_hi_at BIGINT,
                thw_index_lo_at BIGINT,
                thsw_index_last FLOAT,
                thsw_index_hi FLOAT,
                thsw_index_lo FLOAT,
                thsw_index_hi_at BIGINT,
                thsw_index_lo_at BIGINT,
                
                -- WBGT (Wet Bulb Globe Temperature)
                wbgt_last FLOAT,
                wbgt_hi FLOAT,
                wbgt_hi_at BIGINT,
                
                -- Pressure
                pressure FLOAT,
                
                -- Reception & Quality
                rssi INTEGER,
                reception FLOAT,
                packets_received INTEGER,
                packets_missed INTEGER,
                packets_received_streak INTEGER,
                packets_missed_streak INTEGER,
                crc_errors INTEGER,
                resyncs INTEGER,
                freq_error_avg INTEGER,
                freq_error_total INTEGER,
                
                -- Battery & Power
                trans_battery_volt FLOAT,
                trans_battery_flag INTEGER,
                supercap_volt_last FLOAT,
                solar_volt_last FLOAT,
                solar_rad_volt_last FLOAT,
                uv_volt_last INTEGER,
                spars_volt_last FLOAT,
                spars_rpm_last FLOAT,
                
                -- Degree Days
                hdd FLOAT,
                cdd FLOAT,
                
                -- Evapotranspiration
                et FLOAT,
                
                -- Archive Settings
                arch_int INTEGER,
                tz_offset INTEGER,
                
                -- GNSS/GPS
                gnss_fix BOOLEAN,
                gnss_clock BOOLEAN,
                latitude FLOAT,
                longitude FLOAT,
                elevation FLOAT,
                
                -- Metadata
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_source VARCHAR(50) DEFAULT 'weatherlink'
            );
            """
            
            cursor.execute(create_table_sql)
            
            # Create indexes for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ts ON weather_observations(ts);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lsid ON weather_observations(lsid);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_synced_at ON weather_observations(synced_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ts_lsid ON weather_observations(ts, lsid);")
            
            conn.commit()
            logger.info("✅ Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            self.return_connection(conn)
    
    def insert_observations(self, records):
        """
        Bulk insert weather observations.
        
        Args:
            records: List of dicts with observation data
        
        Returns:
            Number of rows inserted
        """
        if not records:
            return 0
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Build column list from first record
            columns = list(records[0].keys())
            columns_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            
            # Prepare INSERT OR IGNORE query
            query = f"""
            INSERT INTO weather_observations ({columns_str})
            VALUES %s
            ON CONFLICT (ts) DO NOTHING
            RETURNING id;
            """
            
            # Convert dicts to tuples in correct order
            values = [tuple(r.get(col) for col in columns) for r in records]
            
            # Execute bulk insert
            execute_values(cursor, query, values)
            inserted_count = len(cursor.fetchall())
            
            conn.commit()
            logger.info(f"✅ Inserted {inserted_count} observations (attempted {len(records)})")
            return inserted_count
            
        except Exception as e:
            logger.error(f"Failed to insert observations: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            self.return_connection(conn)
    
    def get_observation_count(self):
        """Get total observations in database."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM weather_observations;")
            count = cursor.fetchone()[0]
            return count
        finally:
            cursor.close()
            self.return_connection(conn)
    
    def get_latest_timestamp(self):
        """Get the most recent observation timestamp."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ts) FROM weather_observations;")
            result = cursor.fetchone()[0]
            return result
        finally:
            cursor.close()
            self.return_connection(conn)
    
    def export_to_csv(self, output_path, start_timestamp=None, end_timestamp=None):
        """
        Export observations to CSV file.
        
        Args:
            output_path: Path to save CSV
            start_timestamp: Unix timestamp for start (optional)
            end_timestamp: Unix timestamp for end (optional)
        """
        import csv
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Build query
            query = "SELECT * FROM weather_observations WHERE 1=1"
            params = []
            
            if start_timestamp:
                query += " AND ts >= %s"
                params.append(start_timestamp)
            
            if end_timestamp:
                query += " AND ts <= %s"
                params.append(end_timestamp)
            
            query += " ORDER BY ts ASC;"
            
            cursor.execute(query, params)
            
            # Get column names
            colnames = [desc[0] for desc in cursor.description]
            
            # Write to CSV
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=colnames)
                writer.writeheader()
                
                for row in cursor:
                    row_dict = dict(zip(colnames, row))
                    writer.writerow(row_dict)
            
            row_count = cursor.rowcount
            logger.info(f"✅ Exported {row_count} rows to {output_path}")
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise
        finally:
            cursor.close()
            self.return_connection(conn)