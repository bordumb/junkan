"""
Unit tests for the Parser Engine.
Achieves 100% coverage for src/jnkn/parsing/engine.py.
"""

import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the global config to verify defaults
from jnkn import config as global_config
from jnkn.core.result import Ok, Err
from jnkn.core.types import Node, Edge, NodeType, RelationshipType, ScanMetadata
from jnkn.parsing.base import LanguageParser, ParseResult, ParserContext
from jnkn.parsing.engine import (
    ParserEngine,
    ParserRegistry,
    ScanConfig,
    ScanStats,
    ScanError,
    create_default_engine,
)


# --- Mocks & Fixtures ---

class MockParser(LanguageParser):
    def __init__(self, name="mock", extensions=None):
        super().__init__()
        self._name = name
        self._extensions = extensions or [".mock"]

    @property
    def name(self) -> str:
        return self._name

    @property
    def extensions(self):
        return self._extensions

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return file_path.suffix in self.extensions

    def parse(self, file_path: Path, content: bytes):
        return []


@pytest.fixture
def mock_storage():
    """Mock storage adapter."""
    storage = MagicMock()
    storage.get_all_scan_metadata.return_value = []
    return storage


@pytest.fixture
def engine():
    """ParserEngine instance with a mock parser registered."""
    engine = ParserEngine()
    parser = MockParser(extensions=[".py"])
    engine.register(parser)
    return engine


# --- Test ScanConfig ---

def test_scan_config_defaults():
    """Verify ScanConfig uses values from jnkn.config."""
    config = ScanConfig()
    
    # It should copy the defaults from the global config
    assert config.skip_dirs == global_config.IGNORE_DIRECTORIES
    assert config.skip_patterns == global_config.IGNORE_FILE_PATTERNS
    assert config.incremental is True


def test_scan_config_skips():
    """Test skip logic."""
    config = ScanConfig(skip_dirs={"skip_me"}, skip_patterns={"*.ignore"})
    
    assert config.should_skip_dir("skip_me") is True
    assert config.should_skip_dir("keep_me") is False
    
    # We patch the binary check to focus on pattern matching
    with patch("jnkn.config.is_binary_extension", return_value=False):
        assert config.should_skip_file(Path("file.ignore")) is True
        assert config.should_skip_file(Path("file.keep")) is False

    # Test binary check delegation
    with patch("jnkn.config.is_binary_extension", return_value=True):
        assert config.should_skip_file(Path("binary.exe")) is True


# --- Test ParserRegistry ---

def test_registry_registration_and_lookup():
    registry = ParserRegistry()
    parser_py = MockParser(name="python", extensions=[".py"])
    parser_js = MockParser(name="js", extensions=[".js"])
    
    registry.register(parser_py)
    registry.register(parser_js)
    
    # Hit
    parsers = registry.get_parsers_for_file(Path("test.py"))
    assert len(parsers) == 1
    assert parsers[0] == parser_py
    
    # Miss
    assert registry.get_parsers_for_file(Path("test.rs")) == []
    
    # Case Insensitivity
    assert len(registry.get_parsers_for_file(Path("TEST.PY"))) == 1


def test_registry_discover_parsers():
    """Ensure placeholder method runs without error."""
    registry = ParserRegistry()
    registry.discover_parsers()


# --- Test ParserEngine: Initialization ---

def test_engine_init():
    ctx = ParserContext(root_dir=Path("/tmp"))
    eng = ParserEngine(ctx)
    assert eng.registry is not None


# --- Test ParserEngine: create_default_engine ---

def test_create_default_engine():
    """
    Test that the factory attempts to import and register standard parsers.
    """
    # Create a dict of mocks for the modules we expect
    modules = {
        "jnkn.parsing.python.parser": MagicMock(),
        "jnkn.parsing.terraform.parser": MagicMock(),
        "jnkn.parsing.javascript.parser": MagicMock(),
        "jnkn.parsing.kubernetes.parser": MagicMock(),
        "jnkn.parsing.dbt.source_parser": MagicMock(),
        "jnkn.parsing.dbt.parser": MagicMock(),
        "jnkn.parsing.pyspark.parser": MagicMock(),
        "jnkn.parsing.spark_yaml.parser": MagicMock(),
        "jnkn.parsing.go.parser": MagicMock(),
        "jnkn.parsing.java.parser": MagicMock(),
        "jnkn.parsing.openlineage.parser": MagicMock(),
    }
    
    # Mock specific classes
    modules["jnkn.parsing.python.parser"].PythonParser = MockParser
    modules["jnkn.parsing.terraform.parser"].TerraformParser = MockParser
    
    with patch.dict("sys.modules", modules):
        with patch("jnkn.parsing.engine.ParserEngine.register") as mock_reg:
            create_default_engine()
            # Verify it tried to register something
            assert mock_reg.call_count > 0


# --- Test ParserEngine: _discover_files ---

def test_discover_files(engine, tmp_path):
    """Test recursive discovery with skipping."""
    # Setup:
    # /root
    #   /node_modules/ (skipped dir)
    #     lib.js
    #   /src/
    #     main.py (kept)
    #     ignored.lock (skipped file)
    #     unknown.xyz (skipped - no parser)
    
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").touch()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").touch()
    (tmp_path / "src" / "ignored.lock").touch()
    (tmp_path / "src" / "unknown.xyz").touch()
    
    # Configure
    scan_config = ScanConfig(
        root_dir=tmp_path,
        skip_dirs={"node_modules"},
        skip_patterns={"*.lock"}
    )
    
    # Mock registry to only accept .py files (simulating no parser for .xyz)
    with patch.object(engine.registry, 'get_parsers_for_file') as mock_get:
        mock_get.side_effect = lambda p: [MockParser()] if p.suffix == ".py" else []
        
        files = list(engine._discover_files(scan_config))
        
    assert len(files) == 1
    assert files[0].name == "main.py"


# --- Test ParserEngine: _parse_file_full (Detailed) ---

def test_parse_file_full_no_candidate_parser(engine, tmp_path):
    p = tmp_path / "test.unknown"
    p.touch()
    res = engine._parse_file_full(p, "hash")
    assert res.success is False
    assert len(res.errors) == 0

@patch("pathlib.Path.read_bytes")
def test_parse_file_full_read_error(mock_read, engine, tmp_path):
    p = tmp_path / "test.py"
    mock_read.side_effect = PermissionError("Locked")
    
    res = engine._parse_file_full(p, "hash")
    assert res.success is False
    assert "Locked" in str(res.errors[0])

def test_parse_file_full_parser_rejects(engine, tmp_path):
    """Registry returns a parser, but parser.can_parse returns False."""
    p = tmp_path / "test.py"
    p.write_text("content")
    
    # Parser matches extension but rejects content
    parser = MockParser(extensions=[".py"])
    parser.can_parse = MagicMock(return_value=False)
    
    engine.registry._parsers = {} # Reset
    engine.registry._extension_map = {}
    engine.register(parser)
    
    res = engine._parse_file_full(p, "hash")
    assert res.success is False

def test_parse_file_full_exception_during_parse(engine, tmp_path):
    p = tmp_path / "test.py"
    p.write_text("content")
    
    parser = MockParser(extensions=[".py"])
    parser.parse = MagicMock(side_effect=Exception("Boom"))
    
    engine.registry._parsers = {}
    engine.register(parser)
    
    res = engine._parse_file_full(p, "hash")
    assert res.success is False
    assert "Boom" in str(res.errors[0])

def test_parse_file_full_success_with_hash_injection(engine, tmp_path):
    p = tmp_path / "test.py"
    p.write_text("content")
    
    # Return a node without a hash
    node = Node(id="1", name="1", type=NodeType.CODE_FILE)
    parser = MockParser(extensions=[".py"])
    parser.parse = MagicMock(return_value=[node])
    
    engine.registry._parsers = {}
    engine.register(parser)
    
    res = engine._parse_file_full(p, "my_hash")
    assert res.success is True
    # Verify engine injected the hash into the node
    assert res.nodes[0].file_hash == "my_hash"


# --- Test ParserEngine: scan_and_store (Workflows) ---

@patch("jnkn.parsing.engine.ScanMetadata.compute_hash")
@patch("pathlib.Path.read_bytes")
def test_scan_new_file_success(mock_read_bytes, mock_compute_hash, engine, mock_storage, tmp_path):
    """
    Test scanning a NEW file:
    - Should parse and save
    - Should NOT call delete_nodes_by_file (optimization)
    """
    f = tmp_path / "test.py"
    f.touch()
    mock_compute_hash.return_value = "new_hash"
    mock_read_bytes.return_value = b"content"
    
    # Mock parse result
    with patch.object(engine, '_parse_file_full') as mock_pf:
        mock_pf.return_value = ParseResult(f, "new_hash", nodes=[MagicMock()], edges=[], success=True)
        
        # Ensure no existing metadata
        mock_storage.get_all_scan_metadata.return_value = []
        
        res = engine.scan_and_store(mock_storage, ScanConfig(root_dir=tmp_path))
        
    assert res.is_ok()
    stats = res.unwrap()
    assert stats.files_scanned == 1
    
    # Verify DB calls
    mock_storage.delete_nodes_by_file.assert_not_called() # <-- Corrected Assertion
    mock_storage.save_nodes_batch.assert_called()
    mock_storage.save_scan_metadata.assert_called()


@patch("jnkn.parsing.engine.ScanMetadata.compute_hash")
@patch("pathlib.Path.read_bytes")
def test_scan_update_file_success(mock_read_bytes, mock_compute_hash, engine, mock_storage, tmp_path):
    """
    Test scanning an EXISTING (modified) file:
    - Should call delete_nodes_by_file before saving new ones
    """
    f = tmp_path / "test.py"
    f.touch()
    path_str = str(f)
    mock_compute_hash.return_value = "new_hash_content"
    mock_read_bytes.return_value = b"new_content"
    
    # Mock parse result
    with patch.object(engine, '_parse_file_full') as mock_pf:
        mock_pf.return_value = ParseResult(f, "new_hash_content", nodes=[MagicMock()], edges=[], success=True)
        
        # Simulate existing metadata with different hash
        existing_meta = ScanMetadata(file_path=path_str, file_hash="old_hash")
        mock_storage.get_all_scan_metadata.return_value = [existing_meta]
        
        res = engine.scan_and_store(mock_storage, ScanConfig(root_dir=tmp_path))
        
    assert res.is_ok()
    stats = res.unwrap()
    assert stats.files_scanned == 1
    
    # Verify DB calls
    mock_storage.delete_nodes_by_file.assert_called_once_with(path_str) # <-- Cleanup occurred
    mock_storage.save_nodes_batch.assert_called()


def test_scan_file_discovery_failure(engine, mock_storage):
    """File discovery raises exception."""
    config = MagicMock()
    config.root_dir.walk.side_effect = OSError("Disk failure")
    
    res = engine.scan_and_store(mock_storage, config)
    assert res.is_err()
    assert "File discovery failed" in res.unwrap_err().message


def test_scan_metadata_read_failure(engine, mock_storage, tmp_path):
    """DB read fails, should log warning but proceed."""
    (tmp_path / "test.py").touch()
    
    mock_storage.get_all_scan_metadata.side_effect = Exception("DB error")
    
    # Mock _discover_files to avoid complexity
    with patch.object(engine, '_discover_files', return_value=[tmp_path/"test.py"]):
        with patch.object(engine, '_parse_file_full') as mock_pf:
            mock_pf.return_value = ParseResult(Path("x"), "h", success=True)
            
            res = engine.scan_and_store(mock_storage)
            
    assert res.is_ok()
    assert res.unwrap().files_scanned == 1


def test_scan_pruning_logic(engine, mock_storage, tmp_path):
    """Files in DB but not on disk should be pruned."""
    deleted_path = str(tmp_path / "deleted.py")
    mock_storage.get_all_scan_metadata.return_value = [
        ScanMetadata(file_path=deleted_path, file_hash="h")
    ]
    
    config = ScanConfig(root_dir=tmp_path, incremental=True)
    res = engine.scan_and_store(mock_storage, config)
    
    assert res.is_ok()
    assert res.unwrap().files_deleted == 1
    mock_storage.delete_scan_metadata.assert_called_with(deleted_path)


def test_scan_pruning_failure(engine, mock_storage, tmp_path):
    """Pruning throws exception, should log and continue."""
    mock_storage.get_all_scan_metadata.return_value = [
        ScanMetadata(file_path=str(tmp_path / "deleted.py"), file_hash="h")
    ]
    mock_storage.delete_nodes_by_file.side_effect = Exception("Delete failed")
    
    config = ScanConfig(root_dir=tmp_path, incremental=True)
    res = engine.scan_and_store(mock_storage, config)
    
    assert res.is_ok()
    # Count shouldn't increment if it crashed
    assert res.unwrap().files_deleted == 0


@patch("jnkn.config.MAX_FILE_SIZE_BYTES", 10) # Set tiny limit
def test_scan_large_file_skip(engine, mock_storage, tmp_path):
    """Test skipping files exceeding size limit."""
    f = tmp_path / "huge.py"
    f.write_text("x" * 20) # 20 bytes > 10 bytes limit
    
    res = engine.scan_and_store(mock_storage, ScanConfig(root_dir=tmp_path))
    
    assert res.is_ok()
    assert res.unwrap().files_skipped == 1
    assert res.unwrap().files_scanned == 0


@patch("jnkn.parsing.engine.ScanMetadata.compute_hash")
def test_scan_incremental_skip(mock_hash, engine, mock_storage, tmp_path):
    """Test incremental skipping."""
    f = tmp_path / "test.py"
    f.touch()
    path_str = str(f)
    
    # DB matches disk
    mock_storage.get_all_scan_metadata.return_value = [
        ScanMetadata(file_path=path_str, file_hash="abc", node_count=5)
    ]
    mock_hash.return_value = "abc"
    
    res = engine.scan_and_store(mock_storage, ScanConfig(root_dir=tmp_path, incremental=True))
    
    stats = res.unwrap()
    assert stats.files_scanned == 0
    assert stats.files_unchanged == 1
    assert stats.total_nodes == 5


@patch("jnkn.parsing.engine.ScanMetadata.compute_hash")
def test_scan_persistence_failure(mock_hash, engine, mock_storage, tmp_path):
    """Saving results fails."""
    f = tmp_path / "test.py"
    f.touch()
    mock_hash.return_value = "h"
    
    # Mock cleanup failure (should not stop parse)
    mock_storage.delete_nodes_by_file.side_effect = Exception("Clean fail")
    
    # Mock save failure (should mark file as failed)
    mock_storage.save_nodes_batch.side_effect = Exception("Save fail")
    
    # Setup parse result
    with patch.object(engine, '_parse_file_full') as mock_pf:
        mock_pf.return_value = ParseResult(f, "h", nodes=[MagicMock()], success=True)
        
        # Existing metadata to trigger cleanup logic
        mock_storage.get_all_scan_metadata.return_value = [
            ScanMetadata(file_path=str(f), file_hash="old_hash")
        ]
        
        res = engine.scan_and_store(mock_storage, ScanConfig(root_dir=tmp_path, incremental=True))
        
    stats = res.unwrap()
    assert stats.files_scanned == 0
    assert stats.files_failed == 1


def test_scan_progress_callback(engine, mock_storage, tmp_path):
    """Test progress callback invocation."""
    (tmp_path / "1.py").touch()
    callback = MagicMock()

    with patch.object(engine, '_parse_file_full') as mock_parse:
        mock_parse.return_value = ParseResult(Path("x"), "h", success=True)
        
        engine.scan_and_store(
            storage=mock_storage, 
            config=ScanConfig(root_dir=tmp_path), 
            progress_callback=callback
        )
        
    assert callback.called