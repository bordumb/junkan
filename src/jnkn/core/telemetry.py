import atexit
import json
import logging
import os
import platform
import threading
import uuid
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
from urllib import request, error

import yaml

# Prefer environment variables for config.
POSTHOG_API_KEY = os.getenv("JNKN_POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("JNKN_POSTHOG_HOST", "https://app.posthog.com")

logger = logging.getLogger(__name__)

class TelemetryClient:
    """
    Handles anonymous usage tracking for the CLI.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(".jnkn/config.yaml")
        self._enabled: Optional[bool] = None
        self._distinct_id: Optional[str] = None
        self._threads: List[threading.Thread] = []

        # Register cleanup to wait for pending requests on exit
        atexit.register(self._flush)

    def _flush(self):
        """Wait for pending telemetry requests to finish."""
        pending = [t for t in self._threads if t.is_alive()]
        if pending:
            for t in pending:
                t.join(timeout=2.0)

    @property
    def is_enabled(self) -> bool:
        """Check if telemetry is enabled in config."""
        # Always re-read config in dev/beta to catch 'init' changes immediately
        if not self.config_path.exists():
            return False

        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                # Default to False if not explicitly set
                enabled = data.get("telemetry", {}).get("enabled", False)
                return enabled
        except Exception:
            return False

    @property
    def distinct_id(self) -> str:
        """Get or generate persistent anonymous ID."""
        if self._distinct_id:
            return self._distinct_id

        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    data = yaml.safe_load(f) or {}
                    self._distinct_id = data.get("telemetry", {}).get("distinct_id")
        except Exception:
            pass

        if not self._distinct_id:
            self._distinct_id = str(uuid.uuid4())

        return self._distinct_id

    def track(self, event_name: str, properties: Dict[str, Any] = None):
        """Fire and forget an event."""
        if not self.is_enabled:
            return

        if not POSTHOG_API_KEY:
            return

        payload = {
            "api_key": POSTHOG_API_KEY,
            "event": event_name,
            "properties": {
                "distinct_id": self.distinct_id,
                "$lib": "jnkn-cli",
                "$os": platform.system(),
                "$python_version": platform.python_version(),
                "timestamp": datetime.utcnow().isoformat(),
                **(properties or {})
            }
        }

        # Track thread so we can join it at exit
        thread = threading.Thread(target=self._send_request, args=(payload,))
        thread.daemon = False  # Important: Let it finish if possible
        self._threads.append(thread)
        thread.start()

    def _send_request(self, payload: Dict[str, Any]):
        """Internal method to send HTTP request via urllib."""
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{POSTHOG_HOST}/capture/",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with request.urlopen(req, timeout=5.0) as _:
                pass
        except Exception:
            # Silent fail for telemetry
            pass

# Singleton instance
_client = TelemetryClient()

def track_event(name: str, properties: Dict[str, Any] = None):
    """Public API for tracking events."""
    _client.track(name, properties)