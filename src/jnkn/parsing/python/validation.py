from typing import Set

# Common default values to filter out (false positive prevention)
COMMON_DEFAULTS: Set[str] = {
    "localhost",
    "true",
    "false",
    "null",
    "none",
    "default",
    "dev",
    "prod",
    "staging",
    "test",
    "development",
    "production",
    "info",
    "warning",
    "error",
    "critical",  # Removed 'debug'
    "utf-8",
    "utf8",
    "ascii",
    "dev-secret",
    "secret",
    "yes",
    "no",
    "on",
    "off",
    "enabled",
    "disabled",
    "myapp",
    "app",
    "main",
    "root",
    "admin",
    "user",
}


def is_valid_env_var_name(name: str) -> bool:
    """
    Validate that a string looks like an environment variable name.
    """
    # Empty or too short
    if not name or len(name) < 2:
        return False

    # Pure digits = port number, timeout, etc.
    if name.isdigit():
        return False

    # Known common default values
    if name.lower() in COMMON_DEFAULTS:
        return False

    # Contains spaces = description or sentence, not env var
    if " " in name:
        return False

    # Starts with digit = invalid variable name
    if name[0].isdigit():
        return False

    # Looks like a path or URL = default value
    if name.startswith(
        ("/", "http://", "https://", "./", "../", "redis://", "postgresql://", "mysql://")
    ):
        return False

    # All lowercase, no separators, long string = probably an English word/default
    # Real env vars are typically UPPER_CASE or have underscores
    # Exception: "debug" or "port" might be lowercase, but usually handled by common defaults check
    if name.islower() and "_" not in name and "-" not in name and len(name) > 6:
        return False

    # Looks like a file extension or mime type
    if name.startswith(".") or "/" in name:
        return False

    return True
