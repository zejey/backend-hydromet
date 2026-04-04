"""
System Logs service

- Centralized creation of audit logs
- List/search/filter/sort/paginate logs for admin UI
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from app.database import get_db_cursor, get_db_connection

ALLOWED_SORT_FIELDS = {"created_at", "status", "category", "action", "user_label"}
ALLOWED_SORT_DIR = {"asc", "desc"}

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


class SystemLogsService:
    @staticmethod
    def ensure_table_exists() -> None:
        """
        Ensure the system_logs table exists.

        Note: In production, prefer migrations. This is a safe fallback.
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_logs (
                      id SERIAL PRIMARY KEY,
                      created_at TIMESTAMP NOT NULL DEFAULT NOW(),

                      user_id INTEGER NULL,
                      user_label VARCHAR(120) NULL,
                      role VARCHAR(50) NULL,

                      action VARCHAR(120) NOT NULL,
                      category VARCHAR(80) NOT NULL,
                      status VARCHAR(20) NOT NULL,
                      details TEXT NOT NULL,

                      ip_address VARCHAR(64) NULL,
                      user_agent TEXT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_system_logs_created_at
                    ON system_logs(created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_system_logs_status
                    ON system_logs(status)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_system_logs_category
                    ON system_logs(category)
                    """
                )
                conn.commit()

    @staticmethod
    def create_log(
        *,
        action: str,
        category: str,
        status: str,
        details: str,
        user: Optional[str] = None,
        user_id: Optional[int] = None,
        role: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a single system log row.

        Keep this call small and safe: never raise to break the main flow.
        If logging fails, swallow error (but you may want to print/log server-side).
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO system_logs
                          (user_id, user_label, role, action, category, status, details, ip_address, user_agent)
                        VALUES
                          (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING
                          id,
                          created_at,
                          user_id,
                          user_label AS "user",
                          role,
                          action,
                          category,
                          status,
                          details,
                          ip_address,
                          user_agent
                        """,
                        (
                            user_id,
                            user,
                            role,
                            action,
                            category,
                            status,
                            details,
                            ip_address,
                            user_agent,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()
                    return dict(row) if row else {}
        except Exception as e:
            # Avoid breaking core flows due to logging errors
            # You can replace this with proper server logger if you have one configured.
            print(f"[SystemLogsService] create_log failed: {e}")
            return {}

    @staticmethod
    def list_logs(
        *,
        q: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Returns (total_count, logs[])
        """
        # Sanitize paging
        page = max(page, 1)
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        offset = (page - 1) * page_size

        # Validate sorting
        if sort_by not in ALLOWED_SORT_FIELDS:
            sort_by = "created_at"
        sort_dir = (sort_dir or "desc").lower()
        if sort_dir not in ALLOWED_SORT_DIR:
            sort_dir = "desc"

        where: List[str] = []
        params: List[Any] = []

        if q:
            where.append(
                """
                (
                  LOWER(COALESCE(user_label, '')) LIKE %s OR
                  LOWER(action) LIKE %s OR
                  LOWER(details) LIKE %s OR
                  LOWER(category) LIKE %s OR
                  LOWER(status) LIKE %s
                )
                """
            )
            like = f"%{q.lower()}%"
            params.extend([like, like, like, like, like])

        if category and category != "All":
            where.append("category = %s")
            params.append(category)

        if status and status != "All":
            where.append("status = %s")
            params.append(status)

        if date_from:
            where.append("created_at >= %s")
            params.append(date_from)

        if date_to:
            where.append("created_at <= %s")
            params.append(date_to)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        # If user requests sort_by=user (frontend naming), map to user_label
        if sort_by == "user":
            sort_by = "user_label"

        with get_db_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM system_logs {where_sql}", params)
            total = int(cur.fetchone()["cnt"])

            cur.execute(
                f"""
                SELECT
                  id,
                  created_at,
                  user_id,
                  user_label AS "user",
                  role,
                  action,
                  category,
                  status,
                  details
                FROM system_logs
                {where_sql}
                ORDER BY {sort_by} {sort_dir}
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = cur.fetchall()
            logs = [dict(r) for r in rows]
            return total, logs
