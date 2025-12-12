"""
Cross-Domain Linker Interfaces.

Defines protocols that parsers implement to expose their artifacts
for cross-domain stitching (e.g., matching Env Vars to Terraform outputs).
"""

from typing import List, Protocol, Tuple

from ..core.types import Edge, Node


class EnvVarProvider(Protocol):
    """Parser that provides environment variable nodes."""

    def get_env_var_nodes(self) -> List[Node]: ...


class EnvVarConsumer(Protocol):
    """Parser that consumes environment variables."""

    def get_env_var_reads(self) -> List[Tuple[str, Node]]: ...  # (env_name, reading_node)


class InfraProvider(Protocol):
    """Parser that provides infrastructure resources."""

    def get_infra_outputs(self) -> List[Node]: ...


class DataAssetProvider(Protocol):
    """Parser that provides data assets (tables, files)."""

    def get_data_assets(self) -> List[Node]: ...
    def get_data_lineage(self) -> List[Edge]: ...


class ConfigProvider(Protocol):
    """Parser that provides configuration values."""

    def get_config_keys(self) -> List[Node]: ...
