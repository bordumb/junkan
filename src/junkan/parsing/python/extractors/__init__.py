from typing import List, Type
from .base import BaseExtractor
from .stdlib import StdlibExtractor
from .pydantic import PydanticExtractor
from .click_typer import ClickTyperExtractor
from .dotenv import DotenvExtractor
from .django import DjangoExtractor
from .airflow import AirflowExtractor
from .environs import EnvironsExtractor
from .heuristic import HeuristicExtractor

# Registry of extractor classes
EXTRACTORS: List[Type[BaseExtractor]] = [
    StdlibExtractor,      # 100
    PydanticExtractor,    # 90
    ClickTyperExtractor,  # 80
    DotenvExtractor,      # 70
    DjangoExtractor,      # 60
    AirflowExtractor,     # 50
    EnvironsExtractor,    # 40
    HeuristicExtractor,   # 10
]

def get_extractors() -> List[BaseExtractor]:
    """Factory function to instantiate and sort extractors."""
    # 1. Instantiate all classes first
    instances = [cls() for cls in EXTRACTORS]
    
    # 2. Sort instances by priority (descending)
    # Now c.priority accesses the instance property, returning an int
    return sorted(instances, key=lambda c: -c.priority)