import os
import sys
import uuid
import json
import psycopg2
from datetime import datetime, timedelta
from passlib.context import CryptContext

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

# Database connection
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "hydromet_db")
DB_USER = os.getenv("DB_USER", "weather_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "weather_pass")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def seed_db():
    print(f"🚀 Starting database seeding to {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # 1. Create Tables (derived from app logic)
        print("📁 Creating tables...")
        
        # admin
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                role VARCHAR(50) DEFAULT 'admin',
                username VARCHAR(100) UNIQUE NOT NULL,
                uid VARCHAR(255),
                password_hash TEXT NOT NULL
            );
        """)

        # users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                first_name VARCHAR(64) NOT NULL,
                middle_name VARCHAR(64),
                last_name VARCHAR(64) NOT NULL,
                suffix VARCHAR(16),
                house_address TEXT NOT NULL,
                barangay VARCHAR(64) NOT NULL,
                phone_number VARCHAR(11) UNIQUE NOT NULL,
                role VARCHAR(32) DEFAULT 'resident',
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # barangays
        cur.execute("""
            CREATE TABLE IF NOT EXISTS barangays (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # emergency_hotlines
        cur.execute("""
            CREATE TABLE IF NOT EXISTS emergency_hotlines (
                id VARCHAR(255) PRIMARY KEY,
                service_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(50) NOT NULL,
                category VARCHAR(50) NOT NULL,
                icon_color VARCHAR(50),
                icon_type VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # safety_categories
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safety_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                order_num INTEGER DEFAULT 1,
                icon VARCHAR(100),
                gradient_colors TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            );
        """)

        # safety_tips
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safety_tips (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES safety_categories(id) ON DELETE CASCADE,
                range_label VARCHAR(100),
                level VARCHAR(50),
                color VARCHAR(50),
                order_num INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # safety_tip_details
        cur.execute("""
            CREATE TABLE IF NOT EXISTS safety_tip_details (
                id SERIAL PRIMARY KEY,
                tip_id INTEGER REFERENCES safety_tips(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                order_num INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # system_settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key VARCHAR(100) PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # government_agencies
        cur.execute("""
            CREATE TABLE IF NOT EXISTS government_agencies (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                location_latitude DOUBLE PRECISION,
                location_longitude DOUBLE PRECISION,
                type VARCHAR(100),
                contact VARCHAR(100),
                facilities TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Insert Sample Data
        print("🌱 Inserting sample data...")

        # Admin
        cur.execute("SELECT id FROM admin WHERE email = 'admin@hydromet.ph'")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO admin (email, role, username, password_hash, uid)
                VALUES (%s, %s, %s, %s, %s)
            """, ('admin@hydromet.ph', 'admin', 'admin', hash_password('admin123'), str(uuid.uuid4())))
            print("  ✓ Admin created (admin@hydromet.ph / admin123)")

        # Barangays (San Pedro, Laguna)
        barangays = [
            "Poblacion", "San Vicente", "San Antonio", "Cuyab", 
            "Landayan", "Roque", "United Bayanihan", "GSIS"
        ]
        for b in barangays:
            cur.execute("SELECT id FROM barangays WHERE name = %s", (b,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO barangays (id, name, is_active)
                    VALUES (%s, %s, %s)
                """, (str(uuid.uuid4()), b, True))
        print(f"  ✓ {len(barangays)} Barangays created")

        # Emergency Hotlines
        hotlines = [
            ("San Pedro Fire Station", "02-8808-1234", "Fire", "red", "fire", 1),
            ("San Pedro Police HQ", "02-8808-5678", "Police", "blue", "police", 2),
            ("San Pedro Community Hospital", "02-8808-9999", "Medical", "green", "hospital", 3),
            ("San Pedro Rescue (CDRRM)", "02-8808-0000", "Rescue", "orange", "rescue", 0),
        ]
        for name, phone, cat, color, icon, prio in hotlines:
            cur.execute("SELECT id FROM emergency_hotlines WHERE service_name = %s", (name,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO emergency_hotlines (id, service_name, phone_number, category, icon_color, icon_type, priority)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), name, phone, cat, color, icon, prio))
        print("  ✓ Emergency Hotlines created")

        # Safety Categories & Tips
        categories = [
            ("Heat Stress", "Safety tips for extreme heat conditions.", 1, "sunny", '["#FF5722", "#F44336"]'),
            ("Heavy Rain", "Safety tips for heavy rainfall and flooding.", 2, "rainy", '["#2196F3", "#3F51B5"]'),
            ("Thunderstorm", "Safety tips for lightning and thunder storms.", 3, "thunderstorm", '["#673AB7", "#512DA8"]'),
        ]
        for name, desc, order, icon, colors in categories:
            cur.execute("SELECT id FROM safety_categories WHERE name = %s", (name,))
            existing_cat = cur.fetchone()
            if not existing_cat:
                cur.execute("""
                    INSERT INTO safety_categories (name, description, order_num, icon, gradient_colors)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (name, desc, order, icon, colors))
                cat_id = cur.fetchone()[0]
                
                # Add a sample tip for this category
                cur.execute("""
                    INSERT INTO safety_tips (category_id, range_label, level, color, order_num)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (cat_id, "Extreme Caution", "Moderate", "orange", 1))
                tip_id = cur.fetchone()[0]
                
                # Add sample details
                details = ["Drink plenty of water.", "Avoid direct sunlight.", "Wear light clothing."]
                for i, d in enumerate(details):
                    cur.execute("""
                        INSERT INTO safety_tip_details (tip_id, description, order_num)
                        VALUES (%s, %s, %s)
                    """, (tip_id, d, i))
        print("  ✓ Safety Categories, Tips, and Details created")

        # Sample User
        cur.execute("SELECT id FROM users WHERE phone_number = '09123456789'")
        if not cur.fetchone():
            now = datetime.utcnow()
            cur.execute("""
                INSERT INTO users (id, first_name, last_name, house_address, barangay, phone_number, role, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (str(uuid.uuid4()), 'Juan', 'Dela Cruz', '123 Rizal St.', 'Poblacion', '09123456789', 'resident', True))
            print("  ✓ Sample User created (Juan Dela Cruz / 09123456789)")

        print("✅ Database seeding completed successfully!")

    except Exception as e:
        print(f"❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_db()
