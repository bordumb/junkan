import json
import logging
import platform
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request, error

import yaml

# PUBLIC KEY: This is a write-only key for anonymous telemetry.
# It cannot read data or modify project settings.
# Safe to distribute in the CLI artifact.
POSTHOG_API_KEY = "phc_YOUR_REAL_KEY_HERE"
POSTHOG_API_KEY = "phc_YOUR_PUBLIC_KEY_HERE"
POSTHOG_HOST = "https://app.posthog.com"

logger = logging.getLogger(__name__)

class TelemetryClient:
    """
    Handles anonymous usage tracking for the CLI.

    This client is designed to be completely non-blocking and fail-safe.
    Network requests are dispatched to a background thread to ensure
    the CLI command finishes execution immediately, regardless of network latency.

    Attributes:
        config_path (Path): Path to the user configuration file.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the telemetry client.

        Args:
            config_path: Optional path to the configuration YAML file.
                Defaults to `.jnkn/config.yaml` in the current directory.
        """
        self.config_path = config_path or Path(".jnkn/config.yaml")
        self._enabled: Optional[bool] = None
        self._distinct_id: Optional[str] = None
        
    @property
    def is_enabled(self) -> bool:
        """
        Check if telemetry is enabled in the configuration.

        This method caches the result after the first read to avoid hitting the
        filesystem on every event.

        Returns:
            bool: True if `telemetry.enabled` is set to True in the config file.
            Returns False if the file is missing, invalid, or explicitly disabled.
        """
        if self._enabled is not None:
            return self._enabled
            
        if not self.config_path.exists():
            return False
            
        try:
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                # Default to False if not explicitly set
                self._enabled = data.get("telemetry", {}).get("enabled", False)
                return self._enabled
        except Exception:
            return False

    @property
    def distinct_id(self) -> str:
        """
        Retrieve or generate a persistent anonymous ID for the user.

        The ID is read from the configuration file if available. If missing,
        a temporary UUID is generated for the session.

        Returns:
            str: A UUID string representing the user or session.
        """
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
        """
        Fire and forget a telemetry event.

        This method immediately spawns a daemon thread to send the network request,
        allowing the main program to continue without waiting.

        Args:
            event_name: The name of the event (e.g., 'command_run', 'scan_completed').
            properties: A dictionary of additional metadata to attach to the event.
                Standard properties like timestamp, library version, and OS are added automatically.
        """
        if not self.is_enabled:
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

        # Run in thread to avoid blocking CLI execution
        thread = threading.Thread(target=self._send_request, args=(payload,))
        thread.daemon = True
        thread.start()

    def _send_request(self, payload: Dict[str, Any]):
        """
        Internal method to send the HTTP request via urllib.

        This method catches all exceptions to ensure telemetry failures
        never crash the application.

        Args:
            payload: The full JSON payload to send to the ingestion endpoint.
        """
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                f"{POSTHOG_HOST}/capture/",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with request.urlopen(req, timeout=2.0) as _:
                pass
        except (error.URLError, Exception):
            # Telemetry should never crash the app
            pass

# Singleton instance for easy import across the application
_client = TelemetryClient()

def track_event(name: str, properties: Dict[str, Any] = None):
    """
    Public API for tracking events.

    This is a wrapper around the singleton `TelemetryClient` instance.

    Args:
        name: The name of the event to track.
        properties: Optional dictionary of event properties.
    
    Example:
        >>> track_event("scan_started", {"file_count": 42})
    """
    _client.track(name, properties)