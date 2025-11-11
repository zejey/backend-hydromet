"""
Shared database connection pool for all APIs
Uses connection pooling for optimal performance
"""

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from backend.config import Config

# Global connection pool
_connection_pool = None


def init_connection_pool():
    """Initialize the database connection pool"""
    global _connection_pool
    
    if _connection_pool is None:
        try:
            _connection_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                host=Config.DB_HOST,
                port=Config.DB_PORT,
            )
            print(f"✅ Database connection pool created: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
        except Exception as e:
            print(f"❌ Error creating connection pool: {e}")
            raise
    
    return _connection_pool


def get_connection_pool():
    """Get the connection pool (create if doesn't exist)"""
    if _connection_pool is None:
        return init_connection_pool()
    return _connection_pool


@contextmanager
def get_db_connection():
    """
    Context manager for database connections
    Automatically manages connection lifecycle
    
    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users")
                result = cur.fetchall()
    """
    pool_instance = get_connection_pool()
    conn = pool_instance.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        pool_instance.putconn(conn)


@contextmanager
def get_db_cursor():
    """
    Context manager for database cursor with RealDictCursor
    Returns results as dictionaries
    
    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM users")
            users = cur.fetchall()
            # users is a list of dicts
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
        finally:
            cursor.close()


def close_connection_pool():
    """Close all connections in the pool"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        print("✅ Database connection pool closed")


def test_connection():
    """Test database connection"""
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            if result:
                print("✅ Database connection test successful")
                return True
    except Exception as e:
        print(f"❌ Database connection test failed: {e}")
        return False
    return False
