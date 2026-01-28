"""
Full backup:  Copy Railway database to local PostgreSQL
"""
import subprocess
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def backup_railway_to_local():
    """Use pg_dump to backup Railway database"""
    
    # Railway credentials
    railway_host = os.getenv("DB_HOST")
    railway_port = os.getenv("DB_PORT", "5432")
    railway_db = os.getenv("DB_NAME")
    railway_user = os.getenv("DB_USER")
    railway_password = os.getenv("DB_PASSWORD")
    
    # Output file
    backup_file = f"railway_backup_{os.getenv('DB_NAME')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    
    print(f"🔄 Backing up Railway database to {backup_file}...")
    
    # Set password as environment variable for pg_dump
    env = os.environ.copy()
    env['PGPASSWORD'] = railway_password
    
    # Run pg_dump
    cmd = [
        "pg_dump",
        "-h", railway_host,
        "-p", railway_port,
        "-U", railway_user,
        "-d", railway_db,
        "-F", "p",  # Plain SQL format
        "-f", backup_file
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True)
        print(f"✅ Backup complete:  {backup_file}")
        print(f"💾 Size: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")
        
        print("\n📖 To restore to local PostgreSQL:")
        print(f"   psql -U your_local_user -d your_local_db -f {backup_file}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Backup failed: {e}")
    except FileNotFoundError:
        print("❌ pg_dump not found.  Install PostgreSQL client tools:")
        print("   macOS: brew install postgresql")
        print("   Ubuntu:  sudo apt-get install postgresql-client")
        print("   Windows: Download from postgresql.org")

if __name__ == "__main__":
    backup_railway_to_local()