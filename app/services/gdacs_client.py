"""
GDACS (Global Disaster Alert and Coordination System) Client
Polls the GDACS Web API for active disaster alerts worldwide,
filtered to the Philippine region.

API Docs: https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

GDACS_EVENT_LIST_URL = (
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
)
GDACS_EVENT_DETAIL_URL = (
    "https://www.gdacs.org/gdacsapi/api/events/geteventdata"
)

# Philippine bounding box for proximity filtering
PH_CENTER_LAT = 12.8797
PH_CENTER_LON = 121.7740
PH_RADIUS_KM = 1500  # Generous radius to capture approaching disasters

# Event type mapping
_EVENT_TYPE_MAP = {
    "EQ": "earthquake",
    "TC": "typhoon",
    "FL": "flood",
    "VO": "volcanic",
    "DR": "drought",
    "WF": "wildfire",
    "TS": "tsunami",
}

_SEVERITY_MAP = {
    "Red": "critical",
    "Orange": "warning",
    "Green": "advisory",
}


class GDACSClient:
    """
    Fetch and normalize disaster alerts from GDACS.

    Usage:
        client = GDACSClient()
        alerts = client.fetch_active_alerts()
    """

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def fetch_active_alerts(
        self,
        event_types: Optional[List[str]] = None,
        days_back: int = 7,
        alert_level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch active disaster alerts from GDACS.

        Args:
            event_types: List of GDACS event types to filter.
                         Options: EQ (earthquake), TC (tropical cyclone),
                         FL (flood), VO (volcanic), DR (drought), WF (wildfire)
            days_back: How many days to look back
            alert_level: Filter by alert level: Red, Orange, Green

        Returns:
            List of normalized disaster dicts
        """
        if event_types is None:
            event_types = ["EQ", "TC", "FL", "VO"]

        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime(
            "%Y-%m-%d"
        )
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

        params: Dict[str, Any] = {
            "eventlist": ",".join(event_types),
            "fromdate": from_date,
            "todate": to_date,
        }
        if alert_level:
            params["alertlevel"] = alert_level

        try:
            resp = requests.get(
                GDACS_EVENT_LIST_URL,
                params=params,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", [])
            results = []

            for feature in features:
                normalized = self._normalize(feature)
                if normalized:
                    # Filter to Philippines vicinity
                    if self._is_near_philippines(
                        normalized.get("lat", 0), normalized.get("lng", 0)
                    ):
                        results.append(normalized)

            logger.info(
                f"GDACS: {len(features)} global events, "
                f"{len(results)} near Philippines"
            )
            return results

        except requests.RequestException as exc:
            logger.error(f"GDACS API request failed: {exc}")
            return []
        except Exception as exc:
            logger.error(f"GDACS fetch error: {exc}")
            return []

    def fetch_alert_detail(
        self, event_type: str, event_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific GDACS event."""
        try:
            params = {"eventtype": event_type, "eventid": event_id}
            resp = requests.get(
                GDACS_EVENT_DETAIL_URL,
                params=params,
                timeout=self.timeout,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            features = data.get("features", [])
            if features:
                return self._normalize(features[0])
            return None

        except requests.RequestException as exc:
            logger.error(f"GDACS detail request failed: {exc}")
            return None

    # ── Normalization ────────────────────────────────────────────────────

    @staticmethod
    def _normalize(feature: dict) -> Optional[Dict[str, Any]]:
        """Convert a GDACS GeoJSON feature into a normalized disaster dict."""
        try:
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [0, 0])

            event_type_raw = props.get("eventtype", "")
            disaster_type = _EVENT_TYPE_MAP.get(event_type_raw, event_type_raw.lower())

            alert_level = props.get("alertlevel", "Green")
            severity = _SEVERITY_MAP.get(alert_level, "advisory")

            # Parse dates
            from_date = props.get("fromdate", "")
            detected_at = None
            if from_date:
                try:
                    detected_at = datetime.fromisoformat(
                        from_date.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            return {
                "source": "gdacs",
                "source_event_id": str(props.get("eventid", "")),
                "disaster_type": disaster_type,
                "title": props.get("name", props.get("eventname", "Unknown Event")),
                "description": props.get("description", ""),
                "lat": coords[1] if len(coords) > 1 else 0,
                "lng": coords[0] if len(coords) > 0 else 0,
                "affected_radius_km": props.get("severitydata", {}).get(
                    "severity", None
                ),
                "magnitude": props.get("severitydata", {}).get(
                    "severityvalue", None
                ),
                "category": props.get("alertscore", None),
                "severity": severity,
                "alert_level": alert_level,
                "detected_at": (
                    detected_at.isoformat() if detected_at else None
                ),
                "status": "active",
                "url": props.get("url", {}).get("report", ""),
                "country": props.get("country", ""),
                "population_affected": props.get("population", {}).get(
                    "value", None
                ),
            }
        except Exception as exc:
            logger.error(f"GDACS normalization error: {exc}")
            return None

    @staticmethod
    def _is_near_philippines(lat: float, lng: float) -> bool:
        """Check if coordinates are within rough Philippines vicinity."""
        import math

        dlat = math.radians(lat - PH_CENTER_LAT)
        dlon = math.radians(lng - PH_CENTER_LON)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(PH_CENTER_LAT))
            * math.cos(math.radians(lat))
            * math.sin(dlon / 2) ** 2
        )
        distance_km = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return distance_km <= PH_RADIUS_KM
