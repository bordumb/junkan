"""
Tests for the Mode Management system.
"""

import pytest
from pathlib import Path
import tempfile
import yaml
from unittest.mock import patch, MagicMock

from jnkn.core.mode import (
    ScanMode,
    ModeConfig,
    ModeSettings,
    ModeManager,
    get_mode_manager,
    get_min_confidence,
    get_current_mode,
    _manager as global_manager
)

# Reset singleton before/after tests
@pytest.fixture(autouse=True)
def reset_singleton():
    from jnkn.core import mode
    mode._manager = None
    yield
    mode._manager = None

class TestModeConfig:
    """Tests for ModeConfig."""
    
    def test_default_discovery_config(self):
        settings = ModeSettings()
        config = settings.discovery
        
        assert config.min_confidence == 0.3
        assert config.show_low_confidence is True
        assert config.show_explanations is True
    
    def test_default_enforcement_config(self):
        settings = ModeSettings()
        config = settings.enforcement
        
        assert config.min_confidence == 0.5
        assert config.show_low_confidence is False

class TestModeSettings:
    """Tests for ModeSettings."""
    
    def test_get_active_config(self):
        settings = ModeSettings()
        
        settings.current_mode = ScanMode.DISCOVERY
        assert settings.get_active_config() == settings.discovery
        
        settings.current_mode = ScanMode.ENFORCEMENT
        assert settings.get_active_config() == settings.enforcement
    
    def test_should_show_connection(self):
        settings = ModeSettings()
        
        # Discovery Mode (min 0.3, show_low 0.2)
        settings.current_mode = ScanMode.DISCOVERY
        assert settings.should_show_connection(0.8) is True  # High
        assert settings.should_show_connection(0.3) is True  # At threshold
        assert settings.should_show_connection(0.25) is True # Low but allowed
        assert settings.should_show_connection(0.1) is False # Too low
        
        # Enforcement Mode (min 0.5, no low)
        settings.current_mode = ScanMode.ENFORCEMENT
        assert settings.should_show_connection(0.8) is True
        assert settings.should_show_connection(0.4) is False # Below threshold
        assert settings.should_show_connection(0.25) is False # Low not allowed

class TestModeManager:
    """Tests for ModeManager."""
    
    @pytest.fixture
    def temp_config_path(self, tmp_path):
        return tmp_path / "mode.yaml"
    
    def test_load_defaults_if_missing(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        assert manager.current_mode == ScanMode.DISCOVERY
    
    def test_load_corrupted_yaml(self, temp_config_path):
        temp_config_path.write_text("{ invalid yaml")
        manager = ModeManager(temp_config_path)
        # Should fallback to default safely
        assert manager.current_mode == ScanMode.DISCOVERY

    def test_save_and_load(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        manager.set_mode(ScanMode.ENFORCEMENT)
        
        # Verify file written
        assert temp_config_path.exists()
        content = yaml.safe_load(temp_config_path.read_text())
        assert content["current_mode"] == "enforcement"
        
        # Load new manager
        manager2 = ModeManager(temp_config_path)
        assert manager2.current_mode == ScanMode.ENFORCEMENT

    def test_mark_review_completed_auto_transition(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        manager.settings.auto_transition = True
        
        manager.mark_review_completed()
        
        assert manager.settings.review_completed is True
        assert manager.current_mode == ScanMode.ENFORCEMENT
        
        # Verify persistence
        manager2 = ModeManager(temp_config_path)
        assert manager2.settings.review_completed is True

    def test_mark_review_completed_no_transition(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        manager.settings.auto_transition = False
        
        manager.mark_review_completed()
        
        assert manager.settings.review_completed is True
        assert manager.current_mode == ScanMode.DISCOVERY  # Stayed in discovery

    def test_reset_to_discovery(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        manager.set_mode(ScanMode.ENFORCEMENT)
        manager.mark_review_completed()
        
        manager.reset_to_discovery()
        
        assert manager.current_mode == ScanMode.DISCOVERY
        assert manager.settings.review_completed is False

    def test_get_mode_description(self, temp_config_path):
        manager = ModeManager(temp_config_path)
        
        manager.set_mode(ScanMode.DISCOVERY)
        assert "Discovery Mode" in manager.get_mode_description()
        
        manager.set_mode(ScanMode.ENFORCEMENT)
        assert "Enforcement Mode" in manager.get_mode_description()

    def test_global_helpers(self, temp_config_path):
        # Patch the default path in the class so the global getter uses our temp path
        with patch.object(ModeManager, 'DEFAULT_PATH', temp_config_path):
            mgr = get_mode_manager()
            assert isinstance(mgr, ModeManager)
            # Idempotency
            assert get_mode_manager() is mgr
            
            assert get_min_confidence() == 0.3
            assert get_current_mode() == ScanMode.DISCOVERY