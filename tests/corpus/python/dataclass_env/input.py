"""
Dataclasses using default_factory for env vars.
"""
import os
from dataclasses import dataclass, field

@dataclass
class ServiceConfig:
    # Case 1: Lambda in default_factory
    host: str = field(default_factory=lambda: os.getenv("SERVICE_HOST", "localhost"))
    
    # Case 2: Function ref (harder to catch, but lambda is common)
    port: int = field(default_factory=lambda: int(os.getenv("SERVICE_PORT", "8080")))
    
    # Case 3: List factory
    tags: list = field(default_factory=lambda: os.getenv("TAGS", "").split(","))

@dataclass
class PostInitConfig:
    api_key: str = field(init=False)
    
    def __post_init__(self):
        # Case 4: Inside __post_init__
        self.api_key = os.environ["API_KEY"]