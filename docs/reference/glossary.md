# Glossary

Terms used in Jnkn documentation.

## A

**Artifact**
: A node in the dependency graph representing code, configuration, or infrastructure. Examples: env var, file, Terraform resource.

## B

**Blast Radius**
: The set of artifacts that would be affected by a change to a given artifact. Computed by traversing downstream dependencies.

**Blocked Token**
: A token (like "id", "key") that provides no signal for matching and is ignored during stitching.

## C

**Confidence**
: A score from 0.0 to 1.0 indicating how likely a cross-domain match is correct. Higher = more certain.

**Cross-Domain Dependency**
: A dependency that spans different technology domains (e.g., Python code depending on a Terraform resource).

## D

**Dependency Graph**
: A directed graph where nodes are artifacts and edges are dependencies between them.

## E

**Edge**
: A connection between two nodes in the dependency graph. Has a type (reads, imports, etc.) and optional metadata.

**Extractor**
: A component that detects specific patterns in source code (e.g., `os.getenv()` calls).

## G

**Graph**
: See Dependency Graph.

## M

**Matcher**
: A component that determines if two artifacts should be linked based on name similarity.

## N

**Node**
: An entity in the dependency graph. Has an ID, type, and metadata.

**Normalized Name**
: A standardized form of an artifact name used for matching. Example: `DATABASE_URL` → `databaseurl`.

## P

**Parser**
: A component that reads source files and extracts nodes and edges.

**Pattern**
: A code construct that Jnkn recognizes (e.g., `os.getenv("VAR")`).

**Penalty**
: A multiplier that reduces confidence (e.g., 0.5 for short tokens).

## R

**Rule**
: See Stitching Rule.

## S

**Signal**
: A factor that increases confidence in a match (e.g., exact token overlap).

**Stitching**
: The process of creating edges between nodes from different domains based on name similarity.

**Stitching Rule**
: A rule that defines which node types can be matched and how confidence is calculated.

**Suppression**
: A user-defined rule to ignore specific matches (false positives).

## T

**Token**
: A word extracted from an artifact name. `DATABASE_URL` → `["database", "url"]`.

**Token Matching**
: The technique of linking artifacts by comparing their tokenized names.

## Artifact Types

**code_file**
: A source code file (`.py`, `.js`, etc.).

**code_entity**
: A function or class definition within a file.

**env_var**
: An environment variable.

**infra_resource**
: A Terraform resource, variable, output, or data source.

**k8s_resource**
: A Kubernetes resource (Deployment, ConfigMap, Secret, etc.).

**data_asset**
: A dbt model, source, or seed.

## Edge Types

**reads**
: Source reads a value from target (e.g., file reads env var).

**imports**
: Source imports target (e.g., Python import).

**provides**
: Source provides target (e.g., Terraform outputs an env var value).

**configures**
: Source configures target (e.g., K8s deployment uses ServiceAccount).

**contains**
: Source contains target (e.g., file contains function definition).

**references**
: Generic reference between artifacts.
