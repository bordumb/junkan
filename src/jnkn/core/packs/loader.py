"""
Framework Pack Loader.

Handles loading, validating, and applying framework packs to jnkn configuration.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BoostPattern(BaseModel):
    """A pattern that boosts confidence when matched."""

    pattern: str
    boost: float = Field(ge=0.0, le=0.5)
    reason: str = ""


class AutoSuppression(BaseModel):
    """An automatic suppression rule."""

    source: str
    target: str
    reason: str = ""


class FrameworkPack(BaseModel):
    """
    A Framework Pack containing optimized settings for a technology stack.
    """

    name: str
    version: str = "1.0.0"
    description: str = ""

    # Patterns that increase confidence
    boost_patterns: List[BoostPattern] = Field(default_factory=list)

    # Known false positives to auto-suppress
    auto_suppress: List[AutoSuppression] = Field(default_factory=list)

    # Token weight overrides (token -> weight)
    token_weights: Dict[str, float] = Field(default_factory=dict)

    # Additional tokens to block (too noisy)
    blocked_tokens: List[str] = Field(default_factory=list)

    # Technologies this pack applies to
    technologies: List[str] = Field(default_factory=list)

    # File patterns that indicate this pack should be used
    detection_patterns: List[str] = Field(default_factory=list)

    def get_boost_for_pattern(self, source_name: str, target_name: str) -> float:
        """
        Calculate total confidence boost for a source/target pair.
        """
        import fnmatch

        total_boost = 0.0
        combined = f"{source_name}:{target_name}"

        for bp in self.boost_patterns:
            if (
                fnmatch.fnmatch(source_name, bp.pattern)
                or fnmatch.fnmatch(target_name, bp.pattern)
                or fnmatch.fnmatch(combined, bp.pattern)
            ):
                total_boost += bp.boost

        return min(total_boost, 0.3)  # Cap total boost at 0.3

    def should_auto_suppress(self, source_id: str, target_id: str) -> Tuple[bool, str]:
        """
        Check if a connection should be auto-suppressed.

        Returns (should_suppress, reason)
        """
        import fnmatch

        for supp in self.auto_suppress:
            if fnmatch.fnmatch(source_id, supp.source) and fnmatch.fnmatch(target_id, supp.target):
                return True, supp.reason

        return False, ""

    def get_token_weight(self, token: str) -> Optional[float]:
        """Get custom weight for a token, or None if not overridden."""
        return self.token_weights.get(token.lower())

    def is_blocked_token(self, token: str) -> bool:
        """Check if a token should be blocked (ignored)."""
        return token.lower() in [t.lower() for t in self.blocked_tokens]


class PackLoader:
    """
    Loads framework packs from built-in definitions and custom paths.
    """

    # Built-in packs directory (relative to this file)
    BUILTIN_DIR = Path(__file__).parent / "definitions"

    # User packs directory
    USER_DIR = Path(".jnkn/packs")

    def __init__(self):
        self._cache: Dict[str, FrameworkPack] = {}

    def get_available_packs(self) -> List[str]:
        """Get list of available pack names."""
        packs = []

        # Built-in packs
        if self.BUILTIN_DIR.exists():
            for f in self.BUILTIN_DIR.glob("*.yaml"):
                packs.append(f.stem)

        # User packs
        if self.USER_DIR.exists():
            for f in self.USER_DIR.glob("*.yaml"):
                packs.append(f.stem)

        return sorted(set(packs))

    def load(self, name: str) -> FrameworkPack | None:
        """
        Load a framework pack by name.

        Looks in user directory first, then built-in.
        """
        if name in self._cache:
            return self._cache[name]

        # Try user directory first
        user_path = self.USER_DIR / f"{name}.yaml"
        if user_path.exists():
            pack = self._load_from_file(user_path)
            if pack:
                self._cache[name] = pack
                return pack

        # Try built-in
        builtin_path = self.BUILTIN_DIR / f"{name}.yaml"
        if builtin_path.exists():
            pack = self._load_from_file(builtin_path)
            if pack:
                self._cache[name] = pack
                return pack

        logger.warning(f"Framework pack not found: {name}")
        return None

    def _load_from_file(self, path: Path) -> FrameworkPack | None:
        """Load a pack from a YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            return FrameworkPack(**data)
        except Exception as e:
            logger.error(f"Failed to load pack from {path}: {e}")
            return None

    def detect_pack(self, root_dir: Path) -> str | None:
        """
        Auto-detect which pack to use based on project files.

        Returns pack name or None if no match.
        """
        # Check for framework indicators
        # Structure: key = pack_name, value = list of checks
        # If an item in the list is a List, it is treated as an OR condition (match any)
        # If an item is a Tuple, it is treated as an AND condition (must match)
        indicators = {
            "django-aws": [
                [  # OR: requirements.txt OR pyproject.toml
                    ("requirements.txt", "django"),
                    ("pyproject.toml", "django"),
                ],
                ("*.tf", None),  # AND: Terraform must exist
            ],
            "fastapi-aws": [
                [
                    ("requirements.txt", "fastapi"),
                    ("pyproject.toml", "fastapi"),
                ],
                ("*.tf", None),
            ],
            "express-aws": [
                ("package.json", "express"),
                ("*.tf", None),
            ],
            "rails-heroku": [
                ("Gemfile", "rails"),
                ("Procfile", None),
            ],
        }

        for pack_name, checks in indicators.items():
            if self._check_indicators(root_dir, checks):
                return pack_name

        return None

    def _check_indicators(
        self,
        root_dir: Path,
        checks: List[Union[Tuple[str, Optional[str]], List[Tuple[str, Optional[str]]]]],
    ) -> bool:
        """
        Check if all indicators for a pack are present.
        Supports OR logic via nested lists.
        """
        for check_item in checks:
            # Handle OR logic (List of options)
            if isinstance(check_item, list):
                if not any(self._check_single_indicator(root_dir, p, c) for p, c in check_item):
                    return False
            # Handle standard AND logic (Single Tuple)
            else:
                file_pattern, content_check = check_item
                if not self._check_single_indicator(root_dir, file_pattern, content_check):
                    return False

        return True

    def _check_single_indicator(
        self, root_dir: Path, file_pattern: str, content_check: Optional[str]
    ) -> bool:
        """Check a single file pattern and content string."""
        # Find matching files
        if "*" in file_pattern:
            matches = list(root_dir.glob(f"**/{file_pattern}"))
        else:
            matches = [root_dir / file_pattern]

        # Check if any file exists and matches content
        for path in matches:
            if path.exists():
                if content_check is None:
                    return True

                # Check file content
                try:
                    content = path.read_text().lower()
                    if content_check.lower() in content:
                        return True
                except Exception:
                    continue

        return False


# Module-level convenience functions
_loader: PackLoader | None = None


def _get_loader() -> PackLoader:
    """Get or create the global pack loader."""
    global _loader
    if _loader is None:
        _loader = PackLoader()
    return _loader


def get_available_packs() -> List[str]:
    """Get list of available framework pack names."""
    return _get_loader().get_available_packs()


def load_pack(name: str) -> FrameworkPack | None:
    """Load a framework pack by name."""
    return _get_loader().load(name)


def detect_and_suggest_pack(root_dir: Path | None = None) -> str | None:
    """
    Detect project type and suggest appropriate pack.

    Returns pack name or None.
    """
    root = root_dir or Path.cwd()
    return _get_loader().detect_pack(root)


def apply_pack_to_config(pack: FrameworkPack, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a framework pack's settings to a jnkn config dictionary.

    Returns the modified config.
    """
    # Add pack info to config
    if "pack" not in config:
        config["pack"] = {}

    config["pack"]["name"] = pack.name
    config["pack"]["version"] = pack.version

    # Merge token weights
    if "matching" not in config:
        config["matching"] = {}

    if "token_weights" not in config["matching"]:
        config["matching"]["token_weights"] = {}

    config["matching"]["token_weights"].update(pack.token_weights)

    # Merge blocked tokens
    if "blocked_tokens" not in config["matching"]:
        config["matching"]["blocked_tokens"] = []

    existing = set(config["matching"]["blocked_tokens"])
    existing.update(pack.blocked_tokens)
    config["matching"]["blocked_tokens"] = sorted(existing)

    return config
