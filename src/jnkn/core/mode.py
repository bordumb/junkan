"""
Scan Mode Management for Jnkn.

This module implements the "Discovery Mode" vs "Enforcement Mode" system.
- Discovery Mode: Low confidence threshold, shows more connections, educates users
- Enforcement Mode: Higher threshold, respects suppressions, used after first review

The mode auto-transitions from Discovery to Enforcement after first review completion.
"""

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ScanMode(StrEnum):
    """Available scanning modes."""

    DISCOVERY = "discovery"
    ENFORCEMENT = "enforcement"


class ModeConfig(BaseModel):
    """Configuration for a specific scan mode."""

    min_confidence: float = Field(ge=0.0, le=1.0)
    show_low_confidence: bool = True
    show_explanations: bool = True
    max_findings_display: int = 100


class ModeSettings(BaseModel):
    """Complete mode settings including both modes."""

    current_mode: ScanMode = ScanMode.DISCOVERY
    auto_transition: bool = True  # Auto-switch to enforcement after first review
    review_completed: bool = False

    discovery: ModeConfig = Field(
        default_factory=lambda: ModeConfig(
            min_confidence=0.3,
            show_low_confidence=True,
            show_explanations=True,
            max_findings_display=100,
        )
    )

    enforcement: ModeConfig = Field(
        default_factory=lambda: ModeConfig(
            min_confidence=0.5,
            show_low_confidence=False,
            show_explanations=False,
            max_findings_display=50,
        )
    )

    def get_active_config(self) -> ModeConfig:
        """Get the configuration for the current mode."""
        if self.current_mode == ScanMode.DISCOVERY:
            return self.discovery
        return self.enforcement

    def should_show_connection(self, confidence: float) -> bool:
        """Determine if a connection should be shown based on current mode."""
        config = self.get_active_config()
        if confidence >= config.min_confidence:
            return True
        if config.show_low_confidence and confidence >= 0.2:
            return True
        return False


class ModeManager:
    """
    Manages scan mode state and transitions.

    State is persisted in .jnkn/mode.yaml
    """

    DEFAULT_PATH = Path(".jnkn/mode.yaml")

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or self.DEFAULT_PATH
        self._settings: ModeSettings | None = None

    @property
    def settings(self) -> ModeSettings:
        """Lazy-load settings from disk."""
        if self._settings is None:
            self._settings = self._load_or_create()
        return self._settings

    def _load_or_create(self) -> ModeSettings:
        """Load settings from disk or create default."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = yaml.safe_load(f) or {}
                return ModeSettings(**data)
            except Exception as e:
                logger.warning(f"Failed to load mode config: {e}, using defaults")
                return ModeSettings()
        return ModeSettings()

    def save(self) -> None:
        """Persist current settings to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "current_mode": self.settings.current_mode.value,
            "auto_transition": self.settings.auto_transition,
            "review_completed": self.settings.review_completed,
            "discovery": {
                "min_confidence": self.settings.discovery.min_confidence,
                "show_low_confidence": self.settings.discovery.show_low_confidence,
                "show_explanations": self.settings.discovery.show_explanations,
                "max_findings_display": self.settings.discovery.max_findings_display,
            },
            "enforcement": {
                "min_confidence": self.settings.enforcement.min_confidence,
                "show_low_confidence": self.settings.enforcement.show_low_confidence,
                "show_explanations": self.settings.enforcement.show_explanations,
                "max_findings_display": self.settings.enforcement.max_findings_display,
            },
        }

        with open(self.config_path, "w") as f:
            yaml.dump(data, f, sort_keys=False, default_flow_style=False)

    @property
    def current_mode(self) -> ScanMode:
        """Get the current scan mode."""
        return self.settings.current_mode

    @property
    def min_confidence(self) -> float:
        """Get the minimum confidence threshold for current mode."""
        return self.settings.get_active_config().min_confidence

    def set_mode(self, mode: ScanMode) -> None:
        """Manually set the scan mode."""
        self.settings.current_mode = mode
        self.save()
        logger.info(f"Scan mode set to: {mode.value}")

    def mark_review_completed(self) -> None:
        """Mark that the first review has been completed."""
        self.settings.review_completed = True

        # Auto-transition to enforcement if enabled
        if self.settings.auto_transition:
            self.settings.current_mode = ScanMode.ENFORCEMENT
            logger.info("Auto-transitioned to enforcement mode after review")

        self.save()

    def reset_to_discovery(self) -> None:
        """Reset to discovery mode (useful for re-onboarding)."""
        self.settings.current_mode = ScanMode.DISCOVERY
        self.settings.review_completed = False
        self.save()

    def get_mode_description(self) -> str:
        """Get a human-readable description of the current mode."""
        if self.current_mode == ScanMode.DISCOVERY:
            return (
                "Discovery Mode: Showing more connections to help you understand "
                "your architecture. Some may be false positives. "
                "Run 'jnkn review' to validate and switch to Enforcement Mode."
            )
        return (
            "Enforcement Mode: Showing validated connections only. "
            "Suppressions are respected. Use 'jnkn scan --mode discovery' "
            "to see all potential connections again."
        )


# Module-level convenience function
_manager: ModeManager | None = None


def get_mode_manager() -> ModeManager:
    """Get or create the global mode manager."""
    global _manager
    if _manager is None:
        _manager = ModeManager()
    return _manager


def get_min_confidence() -> float:
    """Get the minimum confidence threshold for the current mode."""
    return get_mode_manager().min_confidence


def get_current_mode() -> ScanMode:
    """Get the current scan mode."""
    return get_mode_manager().current_mode
