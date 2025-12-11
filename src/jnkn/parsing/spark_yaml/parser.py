"""
Spark YAML Parser for jnkn.

This parser extracts job configuration and dependencies from spark.yml files:
- Job definitions (name, schedule, entry point)
- Job dependencies (upstream/downstream relationships)
- Environment variables and secrets
- Spark configurations
- Input/output tables (if specified)

Designed for organizations using YAML-based Spark job orchestration.

Supported Configuration Patterns:
- job_name / name
- schedule / cron
- dependencies / depends_on / upstream
- environment / env / env_vars
- spark_config / spark_conf
- inputs / outputs / tables
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Union

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)


class SparkYamlParser(LanguageParser):
    """
    Spark YAML configuration parser.
    
    Features:
    - Extracts job definitions and metadata
    - Maps job dependencies (DAG structure)
    - Extracts environment variable references
    - Identifies input/output tables
    - Handles various YAML schema conventions
    """

    # Common key names for job properties (different orgs use different conventions)
    JOB_NAME_KEYS = {'job_name', 'name', 'job_id', 'id', 'task_name'}
    SCHEDULE_KEYS = {'schedule', 'cron', 'cron_schedule', 'trigger'}
    DEPENDENCY_KEYS = {'dependencies', 'depends_on', 'upstream', 'upstream_jobs', 'requires'}
    ENVIRONMENT_KEYS = {'environment', 'env', 'env_vars', 'environment_variables', 'variables'}
    SPARK_CONFIG_KEYS = {'spark_config', 'spark_conf', 'spark', 'spark_settings'}
    INPUT_KEYS = {'inputs', 'input_tables', 'source_tables', 'reads', 'sources'}
    OUTPUT_KEYS = {'outputs', 'output_tables', 'target_tables', 'writes', 'targets', 'sink'}
    ENTRY_POINT_KEYS = {'entry_point', 'main', 'script', 'main_class', 'main_file', 'py_file'}

    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def name(self) -> str:
        return "spark_yaml"

    @property
    def extensions(self) -> List[str]:
        return [".yml", ".yaml"]

    @property
    def description(self) -> str:
        return "Spark YAML configuration parser for job orchestration"

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.DEPENDENCIES,
            ParserCapability.ENV_VARS,
            ParserCapability.DATA_LINEAGE,
        ]

    def can_parse(self, file_path: Path, content: Optional[bytes] = None) -> bool:
        """
        Determine if this file should be parsed as Spark YAML.
        
        Checks for:
        - .yml or .yaml extension
        - Contains Spark job indicators
        """
        if file_path.suffix not in ('.yml', '.yaml'):
            return False

        # Check filename patterns
        spark_file_patterns = [
            'spark', 'job', 'pipeline', 'workflow', 'dag',
            'etl', 'batch', 'streaming',
        ]
        filename_lower = file_path.stem.lower()
        if any(pattern in filename_lower for pattern in spark_file_patterns):
            return True

        if content is None:
            return False

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return False

        # Check for Spark job indicators in content
        spark_indicators = [
            'spark_config', 'spark_conf', 'SparkSession',
            'saveAsTable', 'spark.sql', 'pyspark',
            'job_name', 'spark.executor', 'spark.driver',
        ]

        return any(indicator in text for indicator in spark_indicators)

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Spark YAML file and yield nodes and edges.
        
        Args:
            file_path: Path to the YAML file
            content: File contents as bytes
            
        Yields:
            Node and Edge objects for jobs, dependencies, and data lineage
        """
        if not YAML_AVAILABLE:
            self._logger.error("PyYAML not available, cannot parse YAML files")
            return

        # Create file node
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="yaml",
            metadata={"parser": "spark_yaml"},
        )

        # Decode and parse YAML
        try:
            text = content.decode(self.context.encoding)
            config = yaml.safe_load(text)
        except yaml.YAMLError as e:
            self._logger.error(f"Failed to parse YAML {file_path}: {e}")
            return
        except Exception as e:
            self._logger.error(f"Failed to decode {file_path}: {e}")
            return

        if not isinstance(config, dict):
            self._logger.debug(f"YAML root is not a dict in {file_path}")
            return

        # Check if this is a single job or multiple jobs
        if self._looks_like_job_config(config):
            yield from self._parse_single_job(file_id, file_path, config)
        elif 'jobs' in config:
            # Multiple jobs in a list
            for job_config in config.get('jobs', []):
                if isinstance(job_config, dict):
                    yield from self._parse_single_job(file_id, file_path, job_config)
        else:
            # Maybe jobs are top-level keys
            for key, value in config.items():
                if isinstance(value, dict) and self._looks_like_job_config(value):
                    # Use the key as job name if not specified
                    if not any(k in value for k in self.JOB_NAME_KEYS):
                        value['_inferred_name'] = key
                    yield from self._parse_single_job(file_id, file_path, value)

    def _looks_like_job_config(self, config: Dict[str, Any]) -> bool:
        """Check if a config dict looks like a Spark job definition."""
        job_indicators = (
            self.JOB_NAME_KEYS |
            self.SCHEDULE_KEYS |
            self.SPARK_CONFIG_KEYS |
            self.ENTRY_POINT_KEYS |
            self.INPUT_KEYS |
            self.OUTPUT_KEYS
        )
        return any(key in config for key in job_indicators)

    def _parse_single_job(
        self,
        file_id: str,
        file_path: Path,
        config: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Parse a single job configuration."""
        # Extract job name
        job_name = None
        for key in self.JOB_NAME_KEYS:
            if key in config:
                job_name = config[key]
                break

        if not job_name:
            job_name = config.get('_inferred_name', file_path.stem)

        job_id = f"job:{job_name}"

        # Extract metadata
        schedule = None
        for key in self.SCHEDULE_KEYS:
            if key in config:
                schedule = config[key]
                break

        entry_point = None
        for key in self.ENTRY_POINT_KEYS:
            if key in config:
                entry_point = config[key]
                break

        # Create job node
        yield Node(
            id=job_id,
            name=job_name,
            type=NodeType.CODE_ENTITY,
            path=str(file_path),
            metadata={
                "entity_type": "spark_job",
                "schedule": schedule,
                "entry_point": entry_point,
                "file": str(file_path),
            },
        )

        # Link file to job
        yield Edge(
            source_id=file_id,
            target_id=job_id,
            type=RelationshipType.CONTAINS,
        )

        # Extract dependencies
        yield from self._extract_dependencies(job_id, config)

        # Extract environment variables
        yield from self._extract_env_vars(job_id, file_path, config)

        # Extract input/output tables
        yield from self._extract_data_lineage(job_id, file_path, config)

    def _extract_dependencies(
        self,
        job_id: str,
        config: Dict[str, Any],
    ) -> Generator[Edge, None, None]:
        """Extract job dependencies."""
        for key in self.DEPENDENCY_KEYS:
            if key not in config:
                continue

            deps = config[key]
            if isinstance(deps, str):
                deps = [deps]
            elif not isinstance(deps, list):
                continue

            for dep in deps:
                if isinstance(dep, str):
                    dep_job_id = f"job:{dep}"
                    yield Edge(
                        source_id=job_id,
                        target_id=dep_job_id,
                        type=RelationshipType.DEPENDS_ON,
                        metadata={"dependency_type": "job"},
                    )

    def _extract_env_vars(
        self,
        job_id: str,
        file_path: Path,
        config: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract environment variable references."""
        for key in self.ENVIRONMENT_KEYS:
            if key not in config:
                continue

            env_config = config[key]
            if not isinstance(env_config, dict):
                continue

            for env_name, env_value in env_config.items():
                env_id = f"env:{env_name}"

                yield Node(
                    id=env_id,
                    name=env_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "spark_yaml",
                        "file": str(file_path),
                        "default_value": str(env_value) if env_value else None,
                    },
                )

                yield Edge(
                    source_id=job_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"config_key": key},
                )

        # Also extract ${VAR} patterns from string values
        yield from self._extract_env_var_references(job_id, file_path, config)

    def _extract_env_var_references(
        self,
        job_id: str,
        file_path: Path,
        config: Dict[str, Any],
        seen: Optional[Set[str]] = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract ${VAR} style environment variable references from config values."""
        if seen is None:
            seen = set()

        var_pattern = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')

        def search_value(value: Any) -> Generator[str, None, None]:
            if isinstance(value, str):
                for match in var_pattern.finditer(value):
                    yield match.group(1)
            elif isinstance(value, dict):
                for v in value.values():
                    yield from search_value(v)
            elif isinstance(value, list):
                for item in value:
                    yield from search_value(item)

        for env_name in search_value(config):
            if env_name in seen:
                continue
            seen.add(env_name)

            env_id = f"env:{env_name}"

            yield Node(
                id=env_id,
                name=env_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "spark_yaml_reference",
                    "file": str(file_path),
                },
            )

            yield Edge(
                source_id=job_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"reference_type": "variable_substitution"},
            )

    def _extract_data_lineage(
        self,
        job_id: str,
        file_path: Path,
        config: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract input/output table references."""
        # Extract inputs
        for key in self.INPUT_KEYS:
            if key not in config:
                continue

            inputs = config[key]
            if isinstance(inputs, str):
                inputs = [inputs]
            elif not isinstance(inputs, list):
                continue

            for table in inputs:
                if isinstance(table, str):
                    table_id = f"data:{table}"

                    yield Node(
                        id=table_id,
                        name=table,
                        type=NodeType.DATA_ASSET,
                        metadata={
                            "source": "spark_yaml",
                            "file": str(file_path),
                        },
                    )

                    yield Edge(
                        source_id=job_id,
                        target_id=table_id,
                        type=RelationshipType.READS,
                        metadata={"config_key": key},
                    )

        # Extract outputs
        for key in self.OUTPUT_KEYS:
            if key not in config:
                continue

            outputs = config[key]
            if isinstance(outputs, str):
                outputs = [outputs]
            elif not isinstance(outputs, list):
                continue

            for table in outputs:
                if isinstance(table, str):
                    table_id = f"data:{table}"

                    yield Node(
                        id=table_id,
                        name=table,
                        type=NodeType.DATA_ASSET,
                        metadata={
                            "source": "spark_yaml",
                            "file": str(file_path),
                        },
                    )

                    yield Edge(
                        source_id=job_id,
                        target_id=table_id,
                        type=RelationshipType.WRITES,
                        metadata={"config_key": key},
                    )


def create_spark_yaml_parser(context: Optional[ParserContext] = None) -> SparkYamlParser:
    """Factory function to create a Spark YAML parser."""
    return SparkYamlParser(context)
