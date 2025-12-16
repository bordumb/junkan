"""
LSP Utilities.

Helper functions for URI handling and path normalization.
"""

import urllib.parse
from pathlib import Path


def uri_to_path(uri: str) -> Path:
    """
    Convert an LSP URI to a local file system path.
    
    Handles decoding (e.g., %20 -> space) and file:// stripping.

    Args:
        uri: The URI string (e.g., 'file:///Users/marcus/code/my%20app.py').

    Returns:
        Path: The corresponding absolute Path object.
    """
    parsed = urllib.parse.urlparse(uri)
    # unquote handles %20 and other encoded characters
    path_str = urllib.parse.unquote(parsed.path)
    return Path(path_str).resolve()