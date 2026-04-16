"""
Firebase Cloud Messaging (FCM) service

Sends push notifications to mobile devices via Firebase Admin SDK.
Requires:
  - firebase-admin package
  - FIREBASE_CREDENTIALS env var (path to service account JSON, or the JSON itself)
  - Or GOOGLE_APPLICATION_CREDENTIALS env var (standard GCP approach)
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy initialisation — Firebase Admin SDK is only set up on first send.
# This avoids crashing the app if credentials are not configured.
# ---------------------------------------------------------------------------
_firebase_app = None


def _init_firebase():
    """Initialise the Firebase Admin app (once)."""
    global _firebase_app
    if _firebase_app is not None:
        return

    try:
        import firebase_admin
        from firebase_admin import credentials as fb_credentials

        cred_source = os.environ.get("FIREBASE_CREDENTIALS", "")
        if cred_source:
            # Could be a file path or raw JSON string
            if os.path.isfile(cred_source):
                cred = fb_credentials.Certificate(cred_source)
            else:
                cred = fb_credentials.Certificate(json.loads(cred_source))
        elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = fb_credentials.Certificate(
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
            )
        else:
            logger.warning(
                "FCM: No Firebase credentials configured. "
                "Set FIREBASE_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS."
            )
            return

        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("FCM: Firebase Admin SDK initialised.")
    except Exception as exc:
        logger.error("FCM: Failed to initialise Firebase Admin SDK: %s", exc)


def _is_available() -> bool:
    """Return True if Firebase has been initialised."""
    _init_firebase()
    return _firebase_app is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_to_device(token: str, title: str, body: str, data: dict | None = None) -> bool:
    """
    Send a push notification to a single device token.

    Returns True on success, False on failure / not configured.
    """
    if not _is_available():
        logger.warning("FCM: send_to_device skipped — Firebase not configured.")
        return False

    from firebase_admin import messaging

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        token=token,
    )
    try:
        messaging.send(message)
        return True
    except Exception as exc:
        logger.error("FCM: Failed to send to device %s: %s", token[:12], exc)
        return False


def send_to_topic(topic: str, title: str, body: str, data: dict | None = None) -> bool:
    """
    Send a push notification to all devices subscribed to a topic.

    Useful for broadcast notifications (e.g. topic="all", topic="barangay_xyz").
    """
    if not _is_available():
        logger.warning("FCM: send_to_topic skipped — Firebase not configured.")
        return False

    from firebase_admin import messaging

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        topic=topic,
    )
    try:
        messaging.send(message)
        return True
    except Exception as exc:
        logger.error("FCM: Failed to send to topic '%s': %s", topic, exc)
        return False


def send_to_tokens(
    tokens: list[str], title: str, body: str, data: dict | None = None
) -> dict:
    """
    Send a push notification to multiple device tokens (batch).

    Returns {"success_count": N, "failure_count": N}.
    """
    if not _is_available():
        logger.warning("FCM: send_to_tokens skipped — Firebase not configured.")
        return {"success_count": 0, "failure_count": len(tokens)}

    if not tokens:
        return {"success_count": 0, "failure_count": 0}

    from firebase_admin import messaging

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        tokens=tokens,
    )
    try:
        response = messaging.send_each_for_multicast(message)
        return {
            "success_count": response.success_count,
            "failure_count": response.failure_count,
        }
    except Exception as exc:
        logger.error("FCM: Batch send failed: %s", exc)
        return {"success_count": 0, "failure_count": len(tokens)}
