"""
Unit tests for the Telemetry Core Module.

Refactored to test TelemetryService and TelemetryBackend protocol.
"""

import json
import threading
import uuid
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import yaml

from jnkn.core.telemetry import TelemetryService, TelemetryBackend


class MockBackend:
    """Mock backend for testing without network calls."""
    def __init__(self):
        self.events = []
        self._lock = threading.Lock()

    def send(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self.events.append(payload)


class TestTelemetryService:
    """Test the TelemetryService class."""

    @pytest.fixture
    def mock_config_path(self, tmp_path):
        """Create a temporary config file."""
        return tmp_path / "config.yaml"

    @pytest.fixture
    def mock_backend(self):
        return MockBackend()

    def test_is_enabled_default_false(self, mock_config_path):
        """Test telemetry is disabled by default if config is missing."""
        service = TelemetryService(config_path=mock_config_path)
        assert service.is_enabled is False

    def test_is_enabled_explicit_true(self, mock_config_path, mock_backend):
        """Test telemetry is enabled when config says so."""
        config_data = {"telemetry": {"enabled": True}}
        mock_config_path.write_text(yaml.dump(config_data))

        service = TelemetryService(config_path=mock_config_path, backend=mock_backend)
        assert service.is_enabled is True
        service.shutdown()

    def test_distinct_id_generation(self, mock_config_path):
        """Test distinct_id generation when config is missing."""
        service = TelemetryService(config_path=mock_config_path)
        
        # Should generate a valid UUID
        distinct_id = service.distinct_id
        assert uuid.UUID(distinct_id)
        
        # Should be persistent in memory for the instance
        assert service.distinct_id == distinct_id

    def test_distinct_id_from_config(self, mock_config_path):
        """Test distinct_id is read from config if present."""
        fixed_id = "user_123"
        config_data = {"telemetry": {"distinct_id": fixed_id}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        service = TelemetryService(config_path=mock_config_path)
        assert service.distinct_id == fixed_id

    @patch("jnkn.core.telemetry.POSTHOG_API_KEY", "fake_key")
    def test_track_queues_event(self, mock_config_path, mock_backend):
        """Test that track() queues an event that is processed by the backend."""
        # Enable telemetry
        config_data = {"telemetry": {"enabled": True}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        service = TelemetryService(config_path=mock_config_path, backend=mock_backend)
        
        # Track event
        service.track("test_event", {"foo": "bar"})
        
        # Shutdown to ensure worker finishes processing
        service.shutdown()
        
        assert len(mock_backend.events) == 1
        event = mock_backend.events[0]
        
        assert event["event"] == "test_event"
        assert event["properties"]["foo"] == "bar"
        assert event["properties"]["distinct_id"] == service.distinct_id

    def test_track_does_nothing_when_disabled(self, mock_config_path, mock_backend):
        """Test that track() exists early when disabled."""
        # Config exists but enabled=False (default)
        service = TelemetryService(config_path=mock_config_path, backend=mock_backend)
        
        service.track("test_event")
        service.shutdown()
        
        assert len(mock_backend.events) == 0
