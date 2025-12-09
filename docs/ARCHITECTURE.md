# jnkn Architecture

> **Version:** 0.4.0  
> **Last Updated:** December 2024

This document provides a comprehensive technical overview of jnkn's architecture, including system design, data flows, module responsibilities, and extension points.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Core Concepts](#core-concepts)
4. [Module Architecture](#module-architecture)
5. [Data Flow](#data-flow)
6. [Parser System](#parser-system)
7. [Stitching Engine](#stitching-engine)
8. [Storage Layer](#storage-layer)
9. [Analysis Engine](#analysis-engine)
10. [CLI Layer](#cli-layer)
11. [Extension Points](#extension-points)
12. [Directory Structure](#directory-structure)

---

## System Overview

jnkn is a **cross-domain dependency analysis engine** that discovers hidden relationships between infrastructure (Terraform), data pipelines (dbt), and application code (Python, JavaScript, Kubernetes).

### The Problem jnkn Solves

```mermaid
graph TB
    subgraph "Traditional Tooling (Siloed)"
        TF_TOOL[Terraform Plan] --> TF_ONLY[Only sees infra changes]
        DBT_TOOL[dbt Lineage] --> DBT_ONLY[Only sees data dependencies]
        CODE_TOOL[Linters/Tests] --> CODE_ONLY[Only sees code imports]
    end
    
    subgraph "The Gap"
        BREAK1[❌ Infra rename breaks code]
        BREAK2[❌ Schema change breaks API]
        BREAK3[❌ Deleted resource breaks worker]
    end
    
    TF_ONLY -.-> BREAK1
    DBT_ONLY -.-> BREAK2
    CODE_ONLY -.-> BREAK3
    
    style BREAK1 fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style BREAK2 fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style BREAK3 fill:#ff6b6b,stroke:#c92a2a,color:#fff
```

### jnkn's Solution

```mermaid
graph TB
    subgraph "jnkn (Unified View)"
        PARSE[Multi-Language Parsers]
        GRAPH[Unified Dependency Graph]
        STITCH[Cross-Domain Stitching]
        ANALYZE[Impact Analysis]
    end
    
    PARSE --> GRAPH
    GRAPH --> STITCH
    STITCH --> ANALYZE
    
    ANALYZE --> SAFE[✅ Safe to deploy]
    ANALYZE --> WARN[⚠️ Impact detected]
    
    style STITCH fill:#4dabf7,stroke:#1971c2,color:#fff
    style SAFE fill:#40c057,stroke:#2f9e44,color:#fff
    style WARN fill:#fab005,stroke:#f59f00,color:#000
```

---

## High-Level Architecture

```mermaid
graph TB
    subgraph External["External Inputs"]
        PY_FILES[".py files"]
        TF_FILES[".tf files"]
        K8S_FILES["K8s YAML"]
        JS_FILES[".js/.ts files"]
        DBT_MANIFEST["dbt manifest.json"]
    end
    
    subgraph CLI["CLI Layer"]
        SCAN_CMD["jnkn scan"]
        BLAST_CMD["jnkn blast-radius"]
        STATS_CMD["jnkn stats"]
        EXPLAIN_CMD["jnkn explain"]
        SUPPRESS_CMD["jnkn suppress"]
    end
    
    subgraph Parsing["Parsing Layer"]
        ENGINE[ParserEngine]
        REGISTRY[ParserRegistry]
        
        subgraph Parsers["Language Parsers"]
            PY_PARSER[PythonParser]
            TF_PARSER[TerraformParser]
            K8S_PARSER[KubernetesParser]
            JS_PARSER[JavaScriptParser]
            DBT_PARSER[DbtManifestParser]
        end
    end
    
    subgraph Core["Core Engine"]
        GRAPH_MOD[DependencyGraph]
        TOKEN_IDX[TokenIndex]
        STITCHER[Stitcher]
        
        subgraph Rules["Stitching Rules"]
            ENV_INFRA[EnvVarToInfraRule]
            INFRA_INFRA[InfraToInfraRule]
            CODE_DATA[CodeToDataRule]
        end
    end
    
    subgraph Analysis["Analysis Layer"]
        BLAST[BlastRadiusAnalyzer]
        EXPLAIN[ExplainEngine]
        SUPPRESS[SuppressionManager]
    end
    
    subgraph Storage["Storage Layer"]
        SQLITE[(SQLite DB)]
        MEMORY[(In-Memory)]
    end
    
    %% Connections
    PY_FILES --> ENGINE
    TF_FILES --> ENGINE
    K8S_FILES --> ENGINE
    JS_FILES --> ENGINE
    DBT_MANIFEST --> ENGINE
    
    ENGINE --> REGISTRY
    REGISTRY --> Parsers
    
    Parsers --> GRAPH_MOD
    GRAPH_MOD --> TOKEN_IDX
    TOKEN_IDX --> STITCHER
    STITCHER --> Rules
    
    Rules --> SQLITE
    
    SCAN_CMD --> ENGINE
    BLAST_CMD --> BLAST
    STATS_CMD --> SQLITE
    EXPLAIN_CMD --> EXPLAIN
    SUPPRESS_CMD --> SUPPRESS
    
    BLAST --> GRAPH_MOD
    EXPLAIN --> GRAPH_MOD
    SUPPRESS --> SQLITE
    
    GRAPH_MOD <--> SQLITE
    GRAPH_MOD <--> MEMORY
```

---

## Core Concepts

### Node Types

Nodes represent entities in the dependency graph:

```mermaid
graph LR
    subgraph "Node Types"
        CODE_FILE["CODE_FILE<br/>Source files"]
        CODE_ENTITY["CODE_ENTITY<br/>Functions, classes"]
        ENV_VAR["ENV_VAR<br/>Environment variables"]
        INFRA_RESOURCE["INFRA_RESOURCE<br/>Terraform resources"]
        DATA_ASSET["DATA_ASSET<br/>dbt models, tables"]
        CONFIG_KEY["CONFIG_KEY<br/>Configuration values"]
    end
    
    style ENV_VAR fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style INFRA_RESOURCE fill:#4dabf7,stroke:#1971c2,color:#fff
    style DATA_ASSET fill:#40c057,stroke:#2f9e44,color:#fff
```

### Relationship Types

Edges represent directed relationships between nodes:

```mermaid
graph LR
    subgraph "Relationship Types"
        direction TB
        IMPORTS["IMPORTS<br/>Code imports"]
        READS["READS<br/>Env var access"]
        PROVIDES["PROVIDES<br/>Infra provides value"]
        TRANSFORMS["TRANSFORMS<br/>dbt lineage"]
        CONFIGURES["CONFIGURES<br/>K8s config refs"]
    end
```

### Node and Edge Data Model

```mermaid
classDiagram
    class Node {
        +str id
        +str name
        +NodeType type
        +str path
        +str language
        +str file_hash
        +List~str~ tokens
        +Dict metadata
        +datetime created_at
    }
    
    class Edge {
        +str source_id
        +str target_id
        +RelationshipType type
        +float confidence
        +MatchStrategy match_strategy
        +Dict metadata
    }
    
    class NodeType {
        <<enumeration>>
        CODE_FILE
        CODE_ENTITY
        ENV_VAR
        INFRA_RESOURCE
        DATA_ASSET
        CONFIG_KEY
    }
    
    class RelationshipType {
        <<enumeration>>
        IMPORTS
        READS
        WRITES
        PROVIDES
        CONFIGURES
        TRANSFORMS
    }
    
    Node --> NodeType
    Edge --> RelationshipType
```

---

## Module Architecture

### Package Structure

```mermaid
graph TB
    subgraph jnkn["jnkn package"]
        CLI_PKG["cli/<br/>Command-line interface"]
        CORE_PKG["core/<br/>Graph, types, stitching"]
        PARSING_PKG["parsing/<br/>Language parsers"]
        ANALYSIS_PKG["analysis/<br/>Impact analysis"]
        STITCHING_PKG["stitching/<br/>Matchers, suppressions"]
    end
    
    CLI_PKG --> CORE_PKG
    CLI_PKG --> PARSING_PKG
    CLI_PKG --> ANALYSIS_PKG
    
    PARSING_PKG --> CORE_PKG
    ANALYSIS_PKG --> CORE_PKG
    STITCHING_PKG --> CORE_PKG
    
    CORE_PKG --> STORAGE["core/storage/"]
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `core/types.py` | Data models (Node, Edge, enums) |
| `core/graph.py` | DependencyGraph and TokenIndex |
| `core/stitching.py` | Cross-domain link discovery |
| `core/storage/` | SQLite and in-memory backends |
| `parsing/base.py` | Parser base classes and interfaces |
| `parsing/engine.py` | Parser orchestration and registry |
| `parsing/python/` | Python source parser |
| `parsing/terraform/` | Terraform HCL parser |
| `parsing/kubernetes/` | K8s YAML parser |
| `parsing/javascript/` | JS/TS parser |
| `parsing/dbt/` | dbt manifest parser |
| `analysis/blast_radius.py` | Impact calculation |
| `analysis/explain.py` | Match explanation |
| `stitching/matchers.py` | Token matching utilities |
| `stitching/suppressions.py` | False positive management |
| `cli/main.py` | CLI commands |

---

## Data Flow

### Scan Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Engine as ParserEngine
    participant Parser as Language Parser
    participant Graph as DependencyGraph
    participant Stitcher
    participant Storage as SQLite
    
    User->>CLI: jnkn scan --dir ./src
    CLI->>Engine: scan(root_dir)
    
    loop For each file
        Engine->>Engine: route_to_parser(file)
        Engine->>Parser: parse(file_path, content)
        Parser-->>Engine: nodes[], edges[]
        Engine->>Graph: add_nodes(nodes)
        Engine->>Graph: add_edges(edges)
    end
    
    CLI->>Stitcher: stitch(graph)
    
    loop For each rule
        Stitcher->>Graph: get_nodes_by_type()
        Stitcher->>Stitcher: match_tokens()
        Stitcher->>Graph: add_edge(stitched_edge)
    end
    
    CLI->>Storage: persist(graph)
    CLI-->>User: ✅ Scan complete
```

### Blast Radius Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Storage as SQLite
    participant Graph as DependencyGraph
    participant Analyzer as BlastRadiusAnalyzer
    
    User->>CLI: jnkn blast-radius env:DB_HOST
    CLI->>Storage: load_graph()
    Storage-->>Graph: nodes, edges
    
    CLI->>Analyzer: calculate([env:DB_HOST])
    
    Analyzer->>Graph: get_descendants(env:DB_HOST)
    Graph->>Graph: BFS traversal
    Graph-->>Analyzer: impacted_nodes[]
    
    Analyzer->>Analyzer: categorize_by_type()
    Analyzer-->>CLI: BlastRadiusResult
    
    CLI-->>User: JSON impact report
```

---

## Parser System

### Parser Class Hierarchy

```mermaid
classDiagram
    class LanguageParser {
        <<abstract>>
        +name: str
        +extensions: Set~str~
        +context: ParserContext
        +parse(path, content)*
        +get_capabilities()
        +parse_file(path)
    }
    
    class PythonParser {
        +name = "python"
        +extensions = {".py", ".pyi"}
        -_parse_with_tree_sitter()
        -_parse_with_regex()
        -_extract_env_vars()
        -_extract_imports()
    }
    
    class TerraformParser {
        +name = "terraform"
        +extensions = {".tf"}
        -_extract_resources()
        -_extract_variables()
        -_extract_outputs()
    }
    
    class KubernetesParser {
        +name = "kubernetes"
        +extensions = {".yaml", ".yml"}
        -_extract_workloads()
        -_extract_env_vars()
        -_extract_config_refs()
    }
    
    class JavaScriptParser {
        +name = "javascript"
        +extensions = {".js", ".ts", ".jsx", ".tsx"}
        -_extract_process_env()
        -_extract_imports()
    }
    
    class DbtManifestParser {
        +name = "dbt_manifest"
        +extensions = {".json"}
        -_extract_models()
        -_extract_sources()
        -_extract_lineage()
    }
    
    LanguageParser <|-- PythonParser
    LanguageParser <|-- TerraformParser
    LanguageParser <|-- KubernetesParser
    LanguageParser <|-- JavaScriptParser
    LanguageParser <|-- DbtManifestParser
```

### Parser Engine Architecture

```mermaid
graph TB
    subgraph ParserEngine["ParserEngine"]
        REGISTRY[ParserRegistry]
        ROUTER[Extension Router]
        HASHER[File Hasher]
        SCANNER[Directory Scanner]
    end
    
    subgraph Registration["Parser Registration"]
        REG_PY["register(PythonParser)"]
        REG_TF["register(TerraformParser)"]
        REG_K8S["register(KubernetesParser)"]
        REG_JS["register(JavaScriptParser)"]
        REG_DBT["register(DbtManifestParser)"]
    end
    
    REG_PY --> REGISTRY
    REG_TF --> REGISTRY
    REG_K8S --> REGISTRY
    REG_JS --> REGISTRY
    REG_DBT --> REGISTRY
    
    SCANNER --> ROUTER
    ROUTER --> REGISTRY
    
    subgraph Routing["File Routing"]
        FILE_PY["app.py"] --> PY_P[PythonParser]
        FILE_TF["main.tf"] --> TF_P[TerraformParser]
        FILE_K8S["deploy.yaml"] --> K8S_P[KubernetesParser]
        FILE_JS["config.ts"] --> JS_P[JavaScriptParser]
        FILE_DBT["manifest.json"] --> DBT_P[DbtManifestParser]
    end
```

### Python Parser - Env Var Detection Patterns

```mermaid
graph TB
    subgraph "Detected Patterns"
        P1["os.getenv('VAR')"]
        P2["os.environ.get('VAR')"]
        P3["os.environ['VAR']"]
        P4["getenv('VAR')<br/>(from os import getenv)"]
        P5["environ.get('VAR')<br/>(from os import environ)"]
        P6["Field(env='VAR')<br/>(Pydantic)"]
        P7["env.str('VAR')<br/>(environs)"]
    end
    
    P1 --> NODE["ENV_VAR Node"]
    P2 --> NODE
    P3 --> NODE
    P4 --> NODE
    P5 --> NODE
    P6 --> NODE
    P7 --> NODE
    
    NODE --> TOKENS["Tokens:<br/>[var, name, parts]"]
    
    style NODE fill:#ff6b6b,stroke:#c92a2a,color:#fff
```

---

## Stitching Engine

The stitching engine is jnkn's **core innovation** - it discovers implicit dependencies across domains.

### Stitching Process

```mermaid
flowchart TB
    subgraph Input["1. Input Nodes"]
        ENV["env:PAYMENT_DB_HOST<br/>tokens: [payment, db, host]"]
        INFRA["infra:payment_db_host<br/>tokens: [payment, db, host]"]
    end
    
    subgraph Matching["2. Token Matching"]
        NORMALIZE["Normalize Names<br/>PAYMENT_DB_HOST → paymentdbhost"]
        TOKENIZE["Tokenize<br/>→ [payment, db, host]"]
        OVERLAP["Calculate Overlap<br/>Jaccard = 1.0"]
    end
    
    subgraph Scoring["3. Confidence Scoring"]
        STRATEGY["Strategy: NORMALIZED"]
        WEIGHT["Weight: 0.95"]
        CONFIDENCE["Confidence: 0.95"]
    end
    
    subgraph Output["4. Create Edge"]
        EDGE["Edge:<br/>env:PAYMENT_DB_HOST<br/>→ infra:payment_db_host<br/>confidence: 0.95"]
    end
    
    ENV --> NORMALIZE
    INFRA --> NORMALIZE
    NORMALIZE --> TOKENIZE
    TOKENIZE --> OVERLAP
    OVERLAP --> STRATEGY
    STRATEGY --> WEIGHT
    WEIGHT --> CONFIDENCE
    CONFIDENCE --> EDGE
    
    style EDGE fill:#40c057,stroke:#2f9e44,color:#fff
```

### Matching Strategies

```mermaid
graph LR
    subgraph Strategies["Match Strategies"]
        EXACT["EXACT<br/>confidence: 1.0<br/>DB_HOST = DB_HOST"]
        NORMALIZED["NORMALIZED<br/>confidence: 0.95<br/>DB_HOST ≈ db_host"]
        TOKEN["TOKEN_OVERLAP<br/>confidence: 0.85<br/>PAYMENT_DB ∩ payment_db_instance"]
        SUFFIX["SUFFIX<br/>confidence: 0.75<br/>DB_HOST ⊂ aws_rds_db_host"]
        PREFIX["PREFIX<br/>confidence: 0.75<br/>PAYMENT_ ⊂ payment_service"]
    end
    
    EXACT --> |highest| RESULT[Match Result]
    NORMALIZED --> RESULT
    TOKEN --> RESULT
    SUFFIX --> RESULT
    PREFIX --> |lowest| RESULT
```

### Stitching Rules

```mermaid
classDiagram
    class StitchingRule {
        <<abstract>>
        +get_name() str
        +apply(graph) List~Edge~
    }
    
    class EnvVarToInfraRule {
        +get_name() "EnvVarToInfraRule"
        +apply(graph)
        -_find_infra_candidates()
        -_score_match()
    }
    
    class InfraToInfraRule {
        +get_name() "InfraToInfraRule"
        +apply(graph)
        -_find_related_resources()
    }
    
    class Stitcher {
        -rules: List~StitchingRule~
        -config: MatchConfig
        +stitch(graph) List~Edge~
        +add_rule(rule)
        +get_stats() Dict
    }
    
    StitchingRule <|-- EnvVarToInfraRule
    StitchingRule <|-- InfraToInfraRule
    Stitcher --> StitchingRule
```

### Token Index for O(n) Matching

```mermaid
graph TB
    subgraph "Without Token Index: O(n×m)"
        ENV1[env:A] --> INFRA1[infra:1]
        ENV1 --> INFRA2[infra:2]
        ENV1 --> INFRA3[infra:3]
        ENV2[env:B] --> INFRA1
        ENV2 --> INFRA2
        ENV2 --> INFRA3
        ENV3[env:C] --> INFRA1
        ENV3 --> INFRA2
        ENV3 --> INFRA3
    end
    
    subgraph "With Token Index: O(n)"
        direction TB
        TOKEN_payment["token: payment"] --> NODES_payment["env:PAYMENT_DB<br/>infra:payment_host"]
        TOKEN_db["token: db"] --> NODES_db["env:DB_HOST<br/>infra:db_instance"]
        TOKEN_host["token: host"] --> NODES_host["env:DB_HOST<br/>infra:payment_host"]
    end
    
    style TOKEN_payment fill:#4dabf7,stroke:#1971c2,color:#fff
    style TOKEN_db fill:#4dabf7,stroke:#1971c2,color:#fff
    style TOKEN_host fill:#4dabf7,stroke:#1971c2,color:#fff
```

---

## Storage Layer

### Storage Architecture

```mermaid
graph TB
    subgraph Interface["Storage Interface"]
        BASE[StorageBackend<br/><<abstract>>]
    end
    
    subgraph Implementations["Implementations"]
        SQLITE[SQLiteStorage<br/>.jnkn/jnkn.db]
        MEMORY[MemoryStorage<br/>In-process]
    end
    
    BASE <|-- SQLITE
    BASE <|-- MEMORY
    
    subgraph "SQLite Schema"
        NODES_TABLE["nodes<br/>id, name, type, path,<br/>language, file_hash,<br/>tokens, metadata"]
        EDGES_TABLE["edges<br/>source_id, target_id,<br/>type, confidence,<br/>match_strategy, metadata"]
        FILES_TABLE["tracked_files<br/>path, hash, scanned_at"]
        META_TABLE["schema_meta<br/>version, created_at"]
    end
    
    SQLITE --> NODES_TABLE
    SQLITE --> EDGES_TABLE
    SQLITE --> FILES_TABLE
    SQLITE --> META_TABLE
```

### Database Schema

```mermaid
erDiagram
    nodes {
        TEXT id PK
        TEXT name
        TEXT type
        TEXT path
        TEXT language
        TEXT file_hash
        TEXT tokens_json
        TEXT metadata_json
        TIMESTAMP created_at
    }
    
    edges {
        TEXT source_id FK
        TEXT target_id FK
        TEXT type
        REAL confidence
        TEXT match_strategy
        TEXT metadata_json
        TIMESTAMP created_at
    }
    
    tracked_files {
        TEXT path PK
        TEXT hash
        TIMESTAMP scanned_at
    }
    
    suppressions {
        TEXT id PK
        TEXT source_pattern
        TEXT target_pattern
        TEXT reason
        TIMESTAMP created_at
    }
    
    nodes ||--o{ edges : "source_id"
    nodes ||--o{ edges : "target_id"
```

---

## Analysis Engine

### Blast Radius Algorithm

```mermaid
flowchart TB
    subgraph Input
        SOURCE["Source Artifacts<br/>[env:DB_HOST]"]
    end
    
    subgraph Algorithm["BFS Traversal"]
        QUEUE["Queue: [env:DB_HOST]"]
        VISITED["Visited: {}"]
        
        STEP1["1. Pop env:DB_HOST"]
        STEP2["2. Get outgoing edges"]
        STEP3["3. Add targets to queue"]
        STEP4["4. Mark visited"]
        STEP5["5. Repeat until empty"]
    end
    
    subgraph Output
        RESULT["BlastRadiusResult<br/>total: 5<br/>breakdown: {...}"]
    end
    
    SOURCE --> QUEUE
    QUEUE --> STEP1 --> STEP2 --> STEP3 --> STEP4 --> STEP5
    STEP5 --> |queue empty| RESULT
    STEP5 --> |queue not empty| STEP1
```

### Blast Radius Result Structure

```mermaid
graph TB
    subgraph Result["BlastRadiusResult"]
        SOURCE_ARTS["source_artifacts:<br/>[env:DATABASE_URL]"]
        TOTAL["total_impacted_count: 5"]
        
        subgraph Breakdown
            INFRA_B["infra: [aws_db_instance.main]"]
            CODE_B["code: [db/conn.py, api/users.py]"]
            DATA_B["data: [fct_orders]"]
            ENV_B["env: []"]
        end
        
        PATHS["impact_paths: {<br/>  api/users.py: [<br/>    env:DB → conn.py → users.py<br/>  ]<br/>}"]
    end
```

---

## CLI Layer

### Command Structure

```mermaid
graph TB
    subgraph "CLI Commands"
        MAIN["jnkn<br/>(main entry)"]
        
        SCAN["scan<br/>--dir, --db, --full,<br/>--min-confidence"]
        BLAST["blast-radius<br/>--db, --max-depth, --lazy"]
        STATS["stats<br/>--db"]
        CLEAR["clear<br/>--db, --force"]
        EXPLAIN["explain<br/>--source, --target"]
        SUPPRESS["suppress<br/>add/remove/list"]
    end
    
    MAIN --> SCAN
    MAIN --> BLAST
    MAIN --> STATS
    MAIN --> CLEAR
    MAIN --> EXPLAIN
    MAIN --> SUPPRESS
```

### CLI Flow

```mermaid
sequenceDiagram
    participant User
    participant Click as Click Framework
    participant Command as Command Handler
    participant Core as Core Modules
    participant Output as Rich Output
    
    User->>Click: jnkn scan --dir ./src
    Click->>Click: Parse arguments
    Click->>Command: scan(dir="./src", ...)
    
    Command->>Core: ParserEngine.scan()
    Core->>Core: Parse files
    Core->>Core: Build graph
    Core->>Core: Stitch domains
    Core-->>Command: ScanResult
    
    Command->>Output: Format results
    Output-->>User: ✅ Scan complete
```

---

## Extension Points

### Adding a New Parser

```mermaid
flowchart TB
    subgraph Steps["Steps to Add New Parser"]
        S1["1. Create parser class<br/>extends LanguageParser"]
        S2["2. Implement required methods<br/>name, extensions, parse()"]
        S3["3. Add tree-sitter queries<br/>(optional)"]
        S4["4. Register with engine"]
        S5["5. Add tests"]
    end
    
    S1 --> S2 --> S3 --> S4 --> S5
    
    subgraph Example["Example: GoParser"]
        CODE["class GoParser(LanguageParser):<br/>    name = 'go'<br/>    extensions = {'.go'}<br/>    <br/>    def parse(self, path, content):<br/>        yield from self._extract_imports()<br/>        yield from self._extract_env_vars()"]
    end
```

### Adding a New Stitching Rule

```mermaid
flowchart TB
    subgraph Steps["Steps to Add Stitching Rule"]
        S1["1. Create rule class<br/>extends StitchingRule"]
        S2["2. Implement get_name()"]
        S3["3. Implement apply(graph)"]
        S4["4. Register with Stitcher"]
        S5["5. Add tests"]
    end
    
    S1 --> S2 --> S3 --> S4 --> S5
    
    subgraph Example["Example: CodeToDataRule"]
        CODE["class CodeToDataRule(StitchingRule):<br/>    def get_name(self):<br/>        return 'CodeToDataRule'<br/>    <br/>    def apply(self, graph):<br/>        # Find code files that query data assets<br/>        ..."]
    end
```

---

## Directory Structure

```
jnkn/
├── src/jnkn/
│   ├── __init__.py
│   ├── cli.py                      # Legacy CLI entry
│   ├── models.py                   # Legacy models
│   │
│   ├── cli/                        # CLI Layer
│   │   ├── __init__.py
│   │   └── main.py                 # Click commands
│   │
│   ├── core/                       # Core Engine
│   │   ├── __init__.py
│   │   ├── types.py                # Node, Edge, enums
│   │   ├── graph.py                # DependencyGraph, TokenIndex
│   │   ├── stitching.py            # Stitcher, rules
│   │   ├── confidence.py           # Confidence scoring
│   │   └── storage/                # Storage backends
│   │       ├── __init__.py
│   │       ├── base.py             # StorageBackend ABC
│   │       ├── sqlite.py           # SQLite implementation
│   │       └── memory.py           # In-memory implementation
│   │
│   ├── parsing/                    # Parser System
│   │   ├── __init__.py
│   │   ├── base.py                 # LanguageParser ABC
│   │   ├── engine.py               # ParserEngine, Registry
│   │   │
│   │   ├── python/                 # Python Parser
│   │   │   ├── __init__.py
│   │   │   ├── parser.py
│   │   │   └── queries/
│   │   │       ├── imports.scm
│   │   │       └── definitions.scm
│   │   │
│   │   ├── terraform/              # Terraform Parser
│   │   │   ├── __init__.py
│   │   │   ├── parser.py
│   │   │   └── queries/
│   │   │       └── resources.scm
│   │   │
│   │   ├── kubernetes/             # Kubernetes Parser
│   │   │   ├── __init__.py
│   │   │   └── parser.py
│   │   │
│   │   ├── javascript/             # JavaScript/TypeScript Parser
│   │   │   ├── __init__.py
│   │   │   ├── parser.py
│   │   │   └── queries/
│   │   │       └── env_vars.scm
│   │   │
│   │   └── dbt/                    # dbt Parser
│   │       ├── __init__.py
│   │       └── manifest_parser.py
│   │
│   ├── analysis/                   # Analysis Engine
│   │   ├── __init__.py
│   │   ├── blast_radius.py         # Impact calculation
│   │   └── explain.py              # Match explanation
│   │
│   └── stitching/                  # Stitching Utilities
│       ├── __init__.py
│       ├── matchers.py             # Token matching
│       └── suppressions.py         # False positive suppression
│
├── tests/
│   ├── unit/
│   │   ├── core/
│   │   ├── parsing/
│   │   ├── analysis/
│   │   └── stitching/
│   └── e2e_live/
│
├── scripts/
│   ├── verify_parsers.py           # Parser verification
│   └── verify_e2e.sh               # E2E verification
│
├── pyproject.toml
├── README.md
└── ARCHITECTURE.md                 # This file
```

---

## Performance Considerations

### Token Index Optimization

The TokenIndex enables O(n) stitching instead of O(n×m):

```mermaid
graph LR
    subgraph "Naive Approach"
        N1["100 env vars"] --> |"× 500 infra"| N2["50,000 comparisons"]
    end
    
    subgraph "Token Index"
        T1["100 env vars"] --> |"index by token"| T2["~600 lookups"]
    end
    
    N2 --> |"~80x slower"| SLOW[❌]
    T2 --> |"~80x faster"| FAST[✅]
    
    style FAST fill:#40c057,stroke:#2f9e44,color:#fff
    style SLOW fill:#ff6b6b,stroke:#c92a2a,color:#fff
```

### Incremental Scanning

File hashes enable incremental scans:

```mermaid
flowchart LR
    FILE["app.py"] --> HASH["xxhash"]
    HASH --> CHECK{"Hash<br/>changed?"}
    CHECK --> |Yes| PARSE["Parse file"]
    CHECK --> |No| SKIP["Skip file"]
    PARSE --> UPDATE["Update DB"]
    
    style SKIP fill:#40c057,stroke:#2f9e44,color:#fff
```

---

## Future Roadmap

```mermaid
timeline
    title jnkn Roadmap
    
    section Epic 1 - Foundation
        Core Types : Node, Edge models
        Graph Engine : DependencyGraph
        Basic CLI : scan, blast-radius
    
    section Epic 2 - Parser Expansion
        Python Parser : env vars, imports
        Terraform Parser : resources, variables
        Kubernetes Parser : deployments, env vars
        JavaScript Parser : process.env
        dbt Parser : manifest lineage
    
    section Epic 3 - Intelligence
        Semantic Matching : LLM-assisted stitching
        Change Detection : Git diff integration
        Risk Scoring : Impact severity
    
    section Epic 4 - Integration
        GitHub Action : PR comments
        CI/CD Gates : Block risky deploys
        IDE Extension : VSCode plugin
```

---

## References

- [README.md](./README.md) - User documentation
- [pyproject.toml](./pyproject.toml) - Project configuration
- [Tree-sitter](https://tree-sitter.github.io/) - Parser framework
- [NetworkX](https://networkx.org/) - Graph algorithms
- [Pydantic](https://docs.pydantic.dev/) - Data validation