"""
Telemetry Core Module.

Refactored to remove global singletons in favor of Dependency Injection.
This aligns with Rust's ownership model where shared mutable state is restricted.
"""

import atexit
import json
import logging
import os
import platform
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any, Dict, Protocol
from urllib import request

import yaml

# Prefer environment variables for config.
POSTHOG_API_KEY = os.getenv("JNKN_POSTHOG_API_KEY", "")
POSTHOG_HOST = os.getenv("JNKN_POSTHOG_HOST", "https://app.posthog.com")

logger = logging.getLogger(__name__)


class TelemetryBackend(Protocol):
    """Protocol for sending telemetry events."""
    def send(self, payload: Dict[str, Any]) -> None:
        ...


class HttpBackend:
    """Standard HTTP implementation for PostHog."""
    def send(self, payload: Dict[str, Any]) -> None:
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


class TelemetryService:
    """
    Handles anonymous usage tracking via message passing.
    
    Architecture:
    - Uses a thread-safe Queue for events (Actor model style).
    - A background worker thread consumes the queue.
    - No global state; instances must be passed to consumers.
    """

    def __init__(self, config_path: Path | None = None, backend: TelemetryBackend | None = None):
        self.config_path = config_path or Path(".jnkn/config.yaml")
        self._backend = backend or HttpBackend()
        self._queue: Queue[Dict[str, Any] | None] = Queue()
        self._worker_thread: threading.Thread | None = None
        
        # Load config once
        self._config = self._load_config()
        self._distinct_id = self._get_or_create_id()
        
        # Start worker if enabled
        if self.is_enabled:
            self._start_worker()
            atexit.register(self.shutdown)

    @property
    def is_enabled(self) -> bool:
        return self._config.get("telemetry", {}).get("enabled", False)

    @property
    def distinct_id(self) -> str:
        return self._distinct_id

    def track(self, event_name: str, properties: Dict[str, Any] | None = None) -> None:
        """
        Enqueue an event for tracking. Non-blocking.
        """
        if not self.is_enabled or not POSTHOG_API_KEY:
            return

        payload = {
            "api_key": POSTHOG_API_KEY,
            "event": event_name,
            "properties": {
                "distinct_id": self.distinct_id,
                "$lib": "jnkn-cli",
                "$os": platform.system(),
                "$python_version": platform.python_version(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **(properties or {})
            }
        }
        self._queue.put(payload)

    def shutdown(self) -> None:
        """Gracefully shut down the worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            self._queue.put(None)  # Sentinel
            self._worker_thread.join(timeout=2.0)

    def _start_worker(self) -> None:
        def worker():
            while True:
                item = self._queue.get()
                if item is None:
                    break
                self._backend.send(item)
                self._queue.task_done()

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _get_or_create_id(self) -> str:
        # Check config first
        if "telemetry" in self._config and "distinct_id" in self._config["telemetry"]:
            return self._config["telemetry"]["distinct_id"]
        # Fallback to ephemeral ID
        return str(uuid.uuid4())


# Helper factory for DI
def create_telemetry(path: Path | None = None) -> TelemetryService:
    return TelemetryService(path)
