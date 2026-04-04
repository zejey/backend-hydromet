"""
System Logs service (NO category)

- Centralized creation of audit logs
- List/search/filter/sort/paginate logs for admin UI
"""

from __future__ import annotations

from typing import Optional, List, Any, Tuple, Dict
from datetime import datetime

from app.database import get_db_cursor, get_db_connection

ALLOWED_SORT_FIELDS = {"created_at", "status", "action", "user_label"}
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
                conn.commit()

    @staticmethod
    def create_log(
        *,
        action: str,
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
        If logging fails, swallow error.
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO system_logs
                          (user_id, user_label, role, action, status, details, ip_address, user_agent)
                        VALUES
                          (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING
                          id,
                          created_at,
                          user_id,
                          user_label AS "user",
                          role,
                          action,
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
            print(f"[SystemLogsService] create_log failed: {e}")
            return {}

    @staticmethod
    def list_logs(
        *,
        q: Optional[str] = None,
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
        page = max(page, 1)
        page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        offset = (page - 1) * page_size

        if sort_by == "user":  # small convenience alias
            sort_by = "user_label"

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
                  LOWER(status) LIKE %s
                )
                """
            )
            like = f"%{q.lower()}%"
            params.extend([like, like, like, like])

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
                  status,
                  details,
                  ip_address,
                  user_agent
                FROM system_logs
                {where_sql}
                ORDER BY {sort_by} {sort_dir}
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = cur.fetchall()
            return total, [dict(r) for r in rows]
