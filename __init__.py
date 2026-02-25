"""
Backend package initialization
"""

from backend.config import Config
from backend.database import (
    init_connection_pool,
    get_db_connection,
    get_db_cursor,
    close_connection_pool,
    test_connection
)

__all__ = [
    'Config',
    'init_connection_pool',
    'get_db_connection',
    'get_db_cursor',
    'close_connection_pool',
    'test_connection',
]
