"""
USGS Earthquake Client
Polls the USGS FDSN Event Web Service for real-time earthquake data
near the Philippines and normalizes results for the disaster pipeline.

API Docs: https://earthquake.usgs.gov/fdsnws/event/1/
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Philippine bounding box
PH_BOUNDING_BOX = {
    "minlatitude": 4.5,
    "maxlatitude": 21.5,
    "minlongitude": 116.0,
    "maxlongitude": 127.0,
}

# Default location for distance calculation (San Pedro, Laguna)
DEFAULT_LAT = 14.3597
DEFAULT_LON = 121.0583


class EarthquakeClient:
    """
    Fetch and normalize earthquake data from USGS.

    Usage:
        client = EarthquakeClient()
        quakes = client.fetch_recent(hours=24, min_magnitude=3.0)
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def fetch_recent(
        self,
        hours: int = 24,
        min_magnitude: float = 3.0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent earthquakes within the Philippine bounding box.

        Args:
            hours: Look-back window in hours
            min_magnitude: Minimum magnitude filter
            limit: Maximum number of results

        Returns:
            List of normalized earthquake dicts
        """
        start_time = (datetime.utcnow() - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        params = {
            "format": "geojson",
            "starttime": start_time,
            "minmagnitude": min_magnitude,
            "limit": limit,
            "orderby": "time",
            **PH_BOUNDING_BOX,
        }

        try:
            resp = requests.get(USGS_API, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return [self._normalize(f) for f in data.get("features", [])]
        except requests.RequestException as exc:
            logger.error(f"USGS API request failed: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Earthquake fetch error: {exc}")
            return []

    def fetch_significant(
        self, days: int = 7, min_magnitude: float = 5.0
    ) -> List[Dict[str, Any]]:
        """Fetch significant earthquakes (M5.0+) in the last N days."""
        return self.fetch_recent(
            hours=days * 24,
            min_magnitude=min_magnitude,
            limit=20,
        )

    def fetch_nearest(
        self,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        radius_km: float = 300,
        hours: int = 72,
        min_magnitude: float = 2.5,
    ) -> List[Dict[str, Any]]:
        """
        Fetch earthquakes within a radius of a specific point.

        Args:
            lat, lon: Center coordinates
            radius_km: Search radius in kilometers
            hours: Look-back window
            min_magnitude: Minimum magnitude

        Returns:
            List of normalized earthquake dicts sorted by distance
        """
        start_time = (datetime.utcnow() - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        params = {
            "format": "geojson",
            "starttime": start_time,
            "latitude": lat,
            "longitude": lon,
            "maxradiuskm": radius_km,
            "minmagnitude": min_magnitude,
            "orderby": "time",
            "limit": 30,
        }

        try:
            resp = requests.get(USGS_API, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            results = [self._normalize(f) for f in data.get("features", [])]

            # Add distance from the search center
            for r in results:
                r["distance_km"] = self._haversine(
                    lat, lon, r["lat"], r["lng"]
                )

            results.sort(key=lambda r: r["distance_km"])
            return results
        except requests.RequestException as exc:
            logger.error(f"USGS nearest query failed: {exc}")
            return []

    # ── Normalization ────────────────────────────────────────────────────

    @staticmethod
    def _normalize(feature: dict) -> Dict[str, Any]:
        """Convert a GeoJSON Feature from USGS into a flat dict."""
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [0, 0, 0])

        magnitude = props.get("mag", 0)
        # Determine severity from magnitude
        if magnitude >= 7.0:
            severity = "critical"
        elif magnitude >= 5.0:
            severity = "warning"
        elif magnitude >= 4.0:
            severity = "watch"
        else:
            severity = "advisory"

        epoch_ms = props.get("time", 0)
        detected_at = datetime.utcfromtimestamp(epoch_ms / 1000) if epoch_ms else None

        return {
            "source": "usgs",
            "source_event_id": feature.get("id", ""),
            "disaster_type": "earthquake",
            "title": props.get("title", f"M{magnitude} Earthquake"),
            "description": props.get("place", ""),
            "lat": coords[1] if len(coords) > 1 else 0,
            "lng": coords[0] if len(coords) > 0 else 0,
            "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": magnitude,
            "severity": severity,
            "detected_at": detected_at.isoformat() if detected_at else None,
            "url": props.get("url", ""),
            "felt": props.get("felt"),  # Number of felt reports
            "tsunami": bool(props.get("tsunami", 0)),
            "status": props.get("status", ""),
            "alert_level": props.get("alert"),  # green/yellow/orange/red
        }

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in km between two lat/lon points."""
        import math

        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
