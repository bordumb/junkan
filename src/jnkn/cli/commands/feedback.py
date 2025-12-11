"""
Feedback Command - User feedback and bug reporting.

This module implements the `jnkn feedback` command, which streamlines the process
of filing GitHub issues. It automatically gathers relevant system information
(OS, Python version, Jnkn version) and opens the user's default browser with
a pre-populated issue template.
"""

import platform
import sys
import urllib.parse
import webbrowser
from typing import Optional

import click

from jnkn import __version__

# The GitHub repository where issues should be filed
GITHUB_REPO = "bordumb/jnkn"


def _get_system_info() -> str:
    """
    Gather diagnostic information about the current environment.

    Collects version numbers and OS details to help maintainers triage issues.

    Returns:
        str: A formatted markdown block containing system diagnostics.
    """
    info = {
        "Jnkn Version": __version__,
        "Python Version": sys.version.split()[0],
        "Platform": platform.platform(),
        "System": platform.system(),
        "Release": platform.release(),
        "Architecture": platform.machine(),
    }
    
    lines = ["**System Information:**"]
    for key, value in info.items():
        lines.append(f"- {key}: {value}")
    
    return "\n".join(lines)


def _build_issue_url(title: str, body: str, labels: str | None = None) -> str:
    """
    Construct a GitHub issue URL with pre-filled fields.

    Args:
        title (str): The initial title for the issue.
        body (str): The initial body text (markdown supported).
        labels (str | None): Comma-separated list of labels to apply.

    Returns:
        str: A fully qualified HTTPS URL to the GitHub new issue page.
    """
    params = {
        "title": title,
        "body": body,
    }
    if labels:
        params["labels"] = labels
        
    query_string = urllib.parse.urlencode(params)
    return f"https://github.com/{GITHUB_REPO}/issues/new?{query_string}"


@click.command()
def feedback():
    """
    Open a GitHub issue with pre-filled system information.

    This command performs the following actions:
    1. Collects local environment details (OS, Python version, CLI version).
    2. Constructs a structured issue template.
    3. Opens the system's default web browser to the GitHub "New Issue" page.

    This ensures that all bug reports and feedback contain the necessary context
    for the maintenance team to respond effectively.

    Example:
        $ jnkn feedback
        Opening feedback form in browser...
    """
    system_info = _get_system_info()
    
    issue_body = (
        "**Description:**\n"
        "\n\n\n"
        "---\n"
        f"{system_info}"
    )
    
    url = _build_issue_url(
        title="[Feedback]: <Short Description>",
        body=issue_body,
        labels="feedback,triage"
    )
    
    click.echo("Opening feedback form in your browser...")
    click.echo(click.style(f"URL: {url}", dim=True))
    
    webbrowser.open(url)
