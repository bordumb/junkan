"""
Workspace management for the Jnkn LSP.

This module handles the lifecycle of the Jnkn environment, including:
1. Bootstrapping the .jnkn directory and database.
2. Managing the background 'watch' process.
3. Performing integrity checks on the graph data.
"""

import logging
import subprocess
import sys
import sqlite3
from pathlib import Path
from typing import Optional, List

# Import utility for robust URI handling
from jnkn_lsp.utils import uri_to_path

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """
    Manages the Jnkn workspace lifecycle, ensuring the graph is ready and up-to-date.
    
    Attributes:
        root_path (Path): The root directory of the workspace.
        watcher_process (Optional[subprocess.Popen]): The handle for the background watcher.
    """

    def __init__(self, root_uri: str):
        """
        Initialize the manager.

        Args:
            root_uri (str): The root URI from the LSP initialize request.
        """
        self.root_path = uri_to_path(root_uri)
        self.watcher_process: Optional[subprocess.Popen] = None
        self._db_path = self.root_path / ".jnkn" / "jnkn.db"

    @property
    def db_path(self) -> Path:
        """Return the resolved path to the SQLite database."""
        return self._db_path

    def setup(self) -> None:
        """
        Ensure the workspace is fully initialized and ready for queries.
        
        This method is idempotent:
        1. If .jnkn is missing, it runs 'init' and 'scan'.
        2. If .jnkn exists but the DB is empty, it runs 'scan'.
        3. Finally, it starts the background 'watch' process.
        """
        logger.info(f"Setting up Jnkn workspace at: {self.root_path}")

        # 1. Bootstrap Configuration
        if not self._is_initialized():
            logger.info("⚠️ No .jnkn directory found. Initializing fresh workspace...")
            self._run_cli_command("init", input_str="n\n")
            # Force a scan immediately after init to populate tables
            self._run_cli_command("scan")
        
        # 2. Verify Data Integrity
        elif self._is_db_empty():
            logger.info("⚠️ Database exists but appears empty. Triggering full scan...")
            self._run_cli_command("scan")
        else:
            logger.info("✅ Valid existing database found.")

        # 3. Start Background Daemon
        self.start_watcher()

    def teardown(self) -> None:
        """Cleanup resources, including terminating the watcher process."""
        self.stop_watcher()

    def start_watcher(self) -> None:
        """
        Spawn the 'jnkn watch' command as a detached subprocess.
        
        This keeps the graph synchronized as the user edits files.
        """
        if self.watcher_process and self.watcher_process.poll() is None:
            logger.info("Watcher is already running.")
            return

        logger.info("🚀 Starting background watcher...")
        cmd = self._get_cli_command("watch")
        
        try:
            self.watcher_process = subprocess.Popen(
                cmd,
                cwd=str(self.root_path),
                stdout=subprocess.DEVNULL,  # Redirect to avoid clogging LSP pipe
                stderr=subprocess.PIPE,     # Capture errors if needed
            )
            logger.info(f"Watcher started (PID: {self.watcher_process.pid})")
        except Exception as e:
            logger.error(f"Failed to start watcher: {e}")

    def stop_watcher(self) -> None:
        """Terminate the watcher process if it is running."""
        if self.watcher_process:
            logger.info(f"Stopping watcher (PID: {self.watcher_process.pid})...")
            self.watcher_process.terminate()
            try:
                self.watcher_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.watcher_process.kill()
            self.watcher_process = None

    def trigger_scan(self) -> None:
        """
        Manually trigger a scan.
        Useful if the user requests a refresh or if the watcher is lagging.
        """
        logger.info("Triggering manual scan...")
        self._run_cli_command("scan")

    # --- Internal Helpers ---

    def _is_initialized(self) -> bool:
        """Check if the .jnkn directory and config exist."""
        return (self.root_path / ".jnkn" / "config.yaml").exists()

    def _is_db_empty(self) -> bool:
        """
        Check if the nodes table exists and has data.
        
        Returns:
            bool: True if tables are missing or count is 0.
        """
        if not self._db_path.exists():
            return True
            
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                # Check if table exists
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='nodes'")
                if cursor.fetchone()[0] == 0:
                    return True
                
                # Check if it has data
                cursor.execute("SELECT count(*) FROM nodes")
                count = cursor.fetchone()[0]
                return count == 0
        except sqlite3.Error:
            return True

    def _get_cli_command(self, subcommand: str) -> List[str]:
        """
        Resolve the correct command to run jnkn.
        
        Tries to find the 'jnkn' executable in the same bin/ folder as python.
        Falls back to 'python -m jnkn' if needed.
        """
        # Strategy 1: Look for 'jnkn' binary next to python executable
        # This handles the uv/venv installation case correctly
        bin_dir = Path(sys.executable).parent
        jnkn_bin = bin_dir / "jnkn"
        
        if jnkn_bin.exists():
            return [str(jnkn_bin), subcommand]
            
        # Strategy 2: Windows might have jnkn.exe
        jnkn_exe = bin_dir / "jnkn.exe"
        if jnkn_exe.exists():
            return [str(jnkn_exe), subcommand]

        # Strategy 3: Fallback to module execution (might fail if __main__.py is missing)
        return [sys.executable, "-m", "jnkn", subcommand]

    def _run_cli_command(self, command: str, args: List[str] = None, input_str: Optional[str] = None) -> None:
        """
        Run a jnkn CLI command synchronously.
        """
        cmd = self._get_cli_command(command)
        if args:
            cmd.extend(args)
            
        logger.info(f"Running command: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.root_path),
                capture_output=True,
                text=True,
                check=True,
                # ADD THIS: Feed the input to the command
                input=input_str 
            )
            logger.debug(f"Command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            # Add explicit stderr logging to help debug future issues
            logger.error(f"Command failed with return code {e.returncode}")
            logger.error(f"STDERR: {e.stderr}")