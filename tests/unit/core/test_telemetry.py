"""
Unit tests for the Telemetry Core Module.
"""

import json
import uuid
from unittest.mock import ANY, Mock, patch

import pytest
import yaml

from jnkn.core.telemetry import TelemetryClient, track_event


class TestTelemetryClient:
    """Test the TelemetryClient class."""

    @pytest.fixture
    def mock_config_path(self, tmp_path):
        """Create a temporary config file."""
        return tmp_path / "config.yaml"

    def test_is_enabled_default_false(self, mock_config_path):
        """Test telemetry is disabled by default if config is missing."""
        client = TelemetryClient(config_path=mock_config_path)
        assert client.is_enabled is False

    def test_is_enabled_explicit_true(self, mock_config_path):
        """Test telemetry is enabled when config says so."""
        config_data = {"telemetry": {"enabled": True}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        client = TelemetryClient(config_path=mock_config_path)
        assert client.is_enabled is True

    def test_is_enabled_explicit_false(self, mock_config_path):
        """Test telemetry is disabled when config says so."""
        config_data = {"telemetry": {"enabled": False}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        client = TelemetryClient(config_path=mock_config_path)
        assert client.is_enabled is False

    def test_distinct_id_generation(self, mock_config_path):
        """Test distinct_id generation when config is missing."""
        client = TelemetryClient(config_path=mock_config_path)
        
        # Should generate a valid UUID
        distinct_id = client.distinct_id
        assert uuid.UUID(distinct_id)
        
        # Should be persistent in memory for the instance
        assert client.distinct_id == distinct_id

    def test_distinct_id_from_config(self, mock_config_path):
        """Test distinct_id is read from config if present."""
        fixed_id = "user_123"
        config_data = {"telemetry": {"distinct_id": fixed_id}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        client = TelemetryClient(config_path=mock_config_path)
        assert client.distinct_id == fixed_id

    @patch("jnkn.core.telemetry.request.urlopen")
    @patch("jnkn.core.telemetry.request.Request")
    def test_track_sends_request_when_enabled(self, mock_request, mock_urlopen, mock_config_path):
        """Test that track() sends an HTTP request when enabled."""
        # Enable telemetry
        config_data = {"telemetry": {"enabled": True}}
        mock_config_path.write_text(yaml.dump(config_data))
        
        client = TelemetryClient(config_path=mock_config_path)
        
        # We need to wait for the thread to complete in a real scenario,
        # but for unit tests we can mock the threading to run synchronously
        # or just verify the logic inside _send_request if we expose it.
        # Here we rely on the fact that track() calls threading.Thread.
        
        with patch("threading.Thread") as mock_thread:
            client.track("test_event", {"foo": "bar"})
            
            assert mock_thread.called
            args, kwargs = mock_thread.call_args
            target = kwargs.get("target") or args[0]
            payload_arg = kwargs.get("args")[0] if kwargs.get("args") else args[1][0]
            
            # Manually invoke the target to test the network logic
            target(payload_arg)
            
            # Verify Request construction
            assert mock_request.called
            call_args = mock_request.call_args
            url = call_args[0][0]
            data = call_args[1]["data"]
            
            assert "posthog.com" in url
            decoded_data = json.loads(data)
            assert decoded_data["event"] == "test_event"
            assert decoded_data["properties"]["foo"] == "bar"
            assert decoded_data["properties"]["distinct_id"] == client.distinct_id

    def test_track_does_nothing_when_disabled(self, mock_config_path):
        """Test that track() exits early when disabled."""
        client = TelemetryClient(config_path=mock_config_path)
        
        with patch("threading.Thread") as mock_thread:
            client.track("test_event")
            assert not mock_thread.called


    @patch("jnkn.core.telemetry._client")
    def test_global_track_event(self, mock_client):
        """Test the global helper function."""
        track_event("global_test", {"a": 1})
        mock_client.track.assert_called_once_with("global_test", {"a": 1})