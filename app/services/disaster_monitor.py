"""
Disaster Monitor — Unified Multi-Source Disaster Tracking Service

Aggregates disaster data from:
  - USGS (earthquakes)
  - GDACS (typhoons, floods, volcanic, earthquakes)
  - Weather-based hazards (existing ML pipeline)
  - Admin manual alerts

Persists active disasters in the `active_disasters` table and dispatches
localized alerts using barangay vulnerability profiles.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from app.database import get_db_cursor, get_db_connection
from app.services.earthquake_client import EarthquakeClient
from app.services.gdacs_client import GDACSClient

logger = logging.getLogger(__name__)


class DisasterMonitor:
    """
    Central disaster monitoring service.

    Usage:
        monitor = DisasterMonitor()
        active = monitor.get_active_disasters()
        result = monitor.run_monitoring_cycle()
    """

    def __init__(self):
        self.earthquake_client = EarthquakeClient()
        self.gdacs_client = GDACSClient()
        self._ensure_table()

    # ── Table bootstrap ──────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        """Create the active_disasters table if it doesn't exist."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS active_disasters (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            source VARCHAR(32) NOT NULL,
                            source_event_id VARCHAR(128),
                            disaster_type VARCHAR(32) NOT NULL,
                            title VARCHAR(512) NOT NULL,
                            description TEXT,

                            lat FLOAT,
                            lng FLOAT,
                            affected_radius_km FLOAT,

                            severity VARCHAR(16) NOT NULL,
                            magnitude FLOAT,
                            category VARCHAR(32),

                            status VARCHAR(16) DEFAULT 'active',
                            detected_at TIMESTAMP NOT NULL,
                            resolved_at TIMESTAMP,
                            last_updated TIMESTAMP DEFAULT NOW(),

                            alerts_dispatched BOOLEAN DEFAULT FALSE,
                            alert_count INTEGER DEFAULT 0,

                            extra_data JSONB,

                            UNIQUE(source, source_event_id)
                        )
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_active_disasters_status
                        ON active_disasters (status, disaster_type)
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_active_disasters_time
                        ON active_disasters (detected_at DESC)
                    """)
                    conn.commit()
            logger.debug("active_disasters table ready")
        except Exception as exc:
            logger.error(f"Failed to create active_disasters table: {exc}")

    # ── Public API ───────────────────────────────────────────────────────

    def get_active_disasters(
        self,
        disaster_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch all active disasters from the database."""
        try:
            conditions = ["status IN ('active', 'monitoring')"]
            params: list = []

            if disaster_type:
                conditions.append("disaster_type = %s")
                params.append(disaster_type)
            if severity:
                conditions.append("severity = %s")
                params.append(severity)

            where = " AND ".join(conditions)
            params.append(limit)

            with get_db_cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM active_disasters
                    WHERE {where}
                    ORDER BY
                        CASE severity
                            WHEN 'critical' THEN 0
                            WHEN 'warning' THEN 1
                            WHEN 'watch' THEN 2
                            WHEN 'advisory' THEN 3
                            ELSE 4
                        END,
                        detected_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
                return [self._serialize_row(r) for r in rows]
        except Exception as exc:
            logger.error(f"Failed to fetch active disasters: {exc}")
            return []

    def get_disaster_by_id(self, disaster_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single disaster by ID."""
        try:
            with get_db_cursor() as cur:
                cur.execute(
                    "SELECT * FROM active_disasters WHERE id = %s",
                    (disaster_id,),
                )
                row = cur.fetchone()
                return self._serialize_row(row) if row else None
        except Exception as exc:
            logger.error(f"Failed to fetch disaster {disaster_id}: {exc}")
            return None

    def get_disaster_history(
        self, days: int = 30, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch resolved disasters for historical view."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            with get_db_cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM active_disasters
                    WHERE detected_at >= %s
                    ORDER BY detected_at DESC
                    LIMIT %s
                    """,
                    (cutoff, limit),
                )
                rows = cur.fetchall()
                return [self._serialize_row(r) for r in rows]
        except Exception as exc:
            logger.error(f"Failed to fetch disaster history: {exc}")
            return []

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the disaster dashboard."""
        try:
            with get_db_cursor() as cur:
                # Active count by type
                cur.execute("""
                    SELECT disaster_type, COUNT(*) as count,
                           MAX(severity) as max_severity
                    FROM active_disasters
                    WHERE status IN ('active', 'monitoring')
                    GROUP BY disaster_type
                """)
                by_type = {
                    r["disaster_type"]: {
                        "count": r["count"],
                        "max_severity": r["max_severity"],
                    }
                    for r in cur.fetchall()
                }

                # Total active
                cur.execute("""
                    SELECT COUNT(*) as total,
                           COUNT(*) FILTER (WHERE severity = 'critical') as critical,
                           COUNT(*) FILTER (WHERE severity = 'warning') as warning
                    FROM active_disasters
                    WHERE status IN ('active', 'monitoring')
                """)
                totals = dict(cur.fetchone())

                # Last 24h alerts
                cur.execute("""
                    SELECT COUNT(*) as recent
                    FROM active_disasters
                    WHERE detected_at >= NOW() - INTERVAL '24 hours'
                """)
                recent = cur.fetchone()["recent"]

            return {
                "total_active": totals.get("total", 0),
                "critical_count": totals.get("critical", 0),
                "warning_count": totals.get("warning", 0),
                "by_type": by_type,
                "new_last_24h": recent,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Dashboard summary failed: {exc}")
            return {
                "total_active": 0,
                "critical_count": 0,
                "warning_count": 0,
                "by_type": {},
                "new_last_24h": 0,
                "timestamp": datetime.utcnow().isoformat(),
            }

    # ── Monitoring cycle ─────────────────────────────────────────────────

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Run a full monitoring cycle:
          1. Fetch earthquakes from USGS
          2. Fetch alerts from GDACS
          3. Upsert into active_disasters
          4. Return summary

        Designed to be called periodically by the scheduler.
        """
        logger.info("Starting disaster monitoring cycle")

        new_count = 0
        updated_count = 0
        errors = []

        # ── 1. Earthquakes ───────────────────────────────────────────
        try:
            quakes = self.earthquake_client.fetch_recent(
                hours=6, min_magnitude=3.0
            )
            for q in quakes:
                result = self._upsert_disaster(q)
                if result == "new":
                    new_count += 1
                elif result == "updated":
                    updated_count += 1
            logger.info(f"Processed {len(quakes)} earthquake(s)")
        except Exception as exc:
            errors.append(f"earthquake: {exc}")
            logger.error(f"Earthquake monitoring failed: {exc}")

        # ── 2. GDACS alerts ──────────────────────────────────────────
        try:
            alerts = self.gdacs_client.fetch_active_alerts(days_back=3)
            for a in alerts:
                result = self._upsert_disaster(a)
                if result == "new":
                    new_count += 1
                elif result == "updated":
                    updated_count += 1
            logger.info(f"Processed {len(alerts)} GDACS alert(s)")
        except Exception as exc:
            errors.append(f"gdacs: {exc}")
            logger.error(f"GDACS monitoring failed: {exc}")

        # ── 3. Auto-resolve stale disasters ──────────────────────────
        resolved = self._auto_resolve_stale(hours=48)

        result = {
            "success": len(errors) == 0,
            "new_disasters": new_count,
            "updated_disasters": updated_count,
            "auto_resolved": resolved,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info(f"Monitoring cycle complete: {result}")
        return result

    # ── Manual alert creation ────────────────────────────────────────────

    def create_manual_alert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Admin creates a manual disaster alert."""
        disaster = {
            "source": "manual",
            "source_event_id": str(uuid.uuid4()),
            "disaster_type": data.get("disaster_type", "other"),
            "title": data["title"],
            "description": data.get("description", ""),
            "lat": data.get("lat"),
            "lng": data.get("lng"),
            "affected_radius_km": data.get("affected_radius_km"),
            "severity": data.get("severity", "advisory"),
            "magnitude": data.get("magnitude"),
            "category": data.get("category"),
            "detected_at": datetime.utcnow().isoformat(),
            "status": "active",
        }
        self._upsert_disaster(disaster)
        return disaster

    def resolve_disaster(self, disaster_id: str) -> bool:
        """Mark a disaster as resolved."""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE active_disasters
                        SET status = 'resolved',
                            resolved_at = NOW(),
                            last_updated = NOW()
                        WHERE id = %s
                        """,
                        (disaster_id,),
                    )
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to resolve disaster {disaster_id}: {exc}")
            return False

    # ── Internal helpers ─────────────────────────────────────────────────

    def _upsert_disaster(self, disaster: Dict[str, Any]) -> str:
        """
        Insert or update a disaster record.
        Returns 'new', 'updated', or 'skipped'.
        """
        try:
            detected_at = disaster.get("detected_at")
            if isinstance(detected_at, str):
                try:
                    detected_at = datetime.fromisoformat(
                        detected_at.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    detected_at = datetime.utcnow()
            elif not detected_at:
                detected_at = datetime.utcnow()

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO active_disasters (
                            source, source_event_id, disaster_type,
                            title, description,
                            lat, lng, affected_radius_km,
                            severity, magnitude, category,
                            status, detected_at, last_updated
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            'active', %s, NOW()
                        )
                        ON CONFLICT (source, source_event_id) DO UPDATE SET
                            severity = EXCLUDED.severity,
                            magnitude = EXCLUDED.magnitude,
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            last_updated = NOW()
                        RETURNING (xmax = 0) AS is_new
                        """,
                        (
                            disaster.get("source"),
                            disaster.get("source_event_id"),
                            disaster.get("disaster_type"),
                            disaster.get("title", "Unknown Disaster"),
                            disaster.get("description", ""),
                            disaster.get("lat"),
                            disaster.get("lng"),
                            disaster.get("affected_radius_km"),
                            disaster.get("severity", "advisory"),
                            disaster.get("magnitude"),
                            disaster.get("category"),
                            detected_at,
                        ),
                    )
                    row = cur.fetchone()
                    conn.commit()

                    if row and row[0]:
                        return "new"
                    return "updated"
        except Exception as exc:
            logger.error(f"Disaster upsert failed: {exc}")
            return "skipped"

    def _auto_resolve_stale(self, hours: int = 48) -> int:
        """Auto-resolve disasters that haven't been updated in N hours."""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE active_disasters
                        SET status = 'resolved',
                            resolved_at = NOW()
                        WHERE status IN ('active', 'monitoring')
                          AND last_updated < %s
                        """,
                        (cutoff,),
                    )
                    count = cur.rowcount
                    conn.commit()
            if count:
                logger.info(f"Auto-resolved {count} stale disaster(s)")
            return count
        except Exception as exc:
            logger.error(f"Auto-resolve failed: {exc}")
            return 0

    @staticmethod
    def _serialize_row(row) -> Dict[str, Any]:
        """Convert a DB row dict, handling datetime serialization."""
        if not row:
            return {}
        d = dict(row)
        for key in ("detected_at", "resolved_at", "last_updated", "created_at"):
            if key in d and isinstance(d[key], datetime):
                d[key] = d[key].isoformat()
        # UUID → str
        if "id" in d:
            d["id"] = str(d["id"])
        return d


# Singleton
_monitor: Optional[DisasterMonitor] = None


def get_disaster_monitor() -> DisasterMonitor:
    """Get or create a singleton DisasterMonitor."""
    global _monitor
    if _monitor is None:
        _monitor = DisasterMonitor()
    return _monitor
