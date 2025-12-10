# Supply Chain

Dependency security for jnkn itself and the codebases it analyzes.

## Current Design

jnkn takes a minimal-dependency approach to reduce supply chain attack surface. The tool analyzes your codebase's cross-domain dependencies but is itself intentionally lightweight in its third-party dependencies.

### jnkn's Dependencies

**Core dependencies** (required for basic functionality):

```toml
# pyproject.toml
dependencies = [
    "click>=8.1.7",           # CLI framework
    "networkx>=3.2.1",        # Graph operations
    "openlineage-python>=1.40.1",  # Runtime lineage (optional integration)
    "pydantic>=2.5.0",        # Data validation
    "pyyaml>=6.0.0",          # Configuration parsing
    "rich>=13.7.0",           # CLI output formatting
]
```

**Optional dependencies** (for advanced features):

```toml
[project.optional-dependencies]
full = [
    "sqlglot>=20.0.0",        # SQL parsing for dbt
    "tree-sitter==0.21.3",    # AST parsing
    "tree-sitter-languages>=1.10.2",  # Language grammars
    "httpx>=0.27.0",          # HTTP client
    "xxhash>=3.4.1",          # Fast hashing
]
```

### Dependency Selection Criteria

Each dependency was chosen based on:

| Dependency | Justification | Alternatives Considered |
|------------|---------------|------------------------|
| `click` | Industry standard CLI, extensive testing | `argparse` (stdlib but verbose), `typer` (newer) |
| `networkx` | Mature graph library, rich algorithms | `igraph` (C-based, harder install), `graph-tool` |
| `pydantic` | Type validation, serialization | `dataclasses` (less validation), `attrs` |
| `pyyaml` | YAML parsing standard | `ruamel.yaml` (heavier), stdlib `json` |
| `rich` | Beautiful CLI output | `colorama` (less features), plain text |
| `tree-sitter` | Fast, accurate AST parsing | `ast` (Python only), regex (error-prone) |

### Minimal Attack Surface

The core install has only **6 direct dependencies**. Compare to similar tools:

| Tool | Direct Dependencies | Transitive Dependencies |
|------|--------------------|-----------------------|
| jnkn (core) | 6 | ~20 |
| jnkn (full) | 11 | ~45 |
| Checkov | 25+ | 150+ |
| Snyk CLI | N/A (Node.js) | 300+ |

### No Native Code in Core

The core installation avoids native/compiled dependencies:
- No C extensions in required dependencies
- Works on any Python 3.12+ platform
- No compilation step during install

The `[full]` extras add Tree-sitter (which includes C bindings) for advanced parsing, but this is optional.

### Pinned Versions in Lockfile

For reproducible builds, we recommend using a lockfile:

```bash
# Generate locked dependencies
pip-compile pyproject.toml -o requirements.lock

# Install from lockfile
pip install -r requirements.lock
```

### Vulnerability Scanning

jnkn's CI pipeline includes dependency scanning:

```yaml
# .github/workflows/security.yml
- name: Check for vulnerabilities
  run: |
    pip install safety pip-audit
    safety check
    pip-audit
```

### SBOM Generation

Generate a Software Bill of Materials for compliance:

```bash
# Install SBOM generator
pip install cyclonedx-bom

# Generate SBOM
cyclonedx-py environment -o sbom.json
```

## What jnkn Analyzes (Your Codebase)

jnkn's dependency graph focuses on **cross-domain implicit dependencies**, not package dependencies. However, the analysis does touch security-relevant areas.

### Environment Variables

jnkn extracts environment variable references:

```python
# Detected: env:DATABASE_URL
db_url = os.getenv("DATABASE_URL")

# Detected: env:API_SECRET
secret = os.environ["API_SECRET"]
```

**Security note**: jnkn records the *name* of environment variables, never their values. The graph stores `env:DATABASE_URL`, not `postgres://user:password@host/db`.

### Infrastructure References

jnkn parses Terraform outputs and resources:

```hcl
# Detected: infra:db_connection_string
output "db_connection_string" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}
```

**Security note**: jnkn parses HCL structure, not state files. Sensitive values in `terraform.tfstate` are never accessed.

### Kubernetes Secrets References

jnkn detects references to secrets, not their contents:

```yaml
# Detected: config:db-credentials (reference only)
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-credentials
        key: password
```

### What jnkn Does NOT Access

- **Secret values**: Only names/references, never actual secrets
- **State files**: `terraform.tfstate`, `.terraform/` ignored
- **Credentials**: `.env`, `*.pem`, `*_key` files ignored by default
- **Git history**: Only current working tree, not commit history
- **Network resources**: No HTTP calls to resolve references

### Default Ignore Patterns

jnkn's default `.jnknignore` excludes sensitive paths:

```gitignore
# Secrets and credentials
.env
.env.*
*.pem
*.key
**/secrets/
**/credentials/

# State files
terraform.tfstate
terraform.tfstate.*
.terraform/

# Dependencies (not our focus)
node_modules/
venv/
.venv/
__pycache__/

# Build artifacts
dist/
build/
*.egg-info/
```

## Secure Usage Recommendations

### CI/CD Integration

When running in CI/CD, ensure jnkn doesn't have access to secrets:

```yaml
# GitHub Actions - run before secrets are injected
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # Run jnkn BEFORE setting up cloud credentials
      - name: Analyze dependencies
        run: |
          pip install jnkn
          jnkn scan .
      
      # Later: deploy with secrets (jnkn not involved)
      - name: Deploy
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
        run: ...
```

### Air-Gapped Environments

jnkn works fully offline:

```bash
# Pre-download dependencies
pip download jnkn -d ./packages

# Install offline
pip install --no-index --find-links=./packages jnkn

# Run with telemetry disabled (default)
jnkn scan .
```

### Least Privilege

jnkn only needs read access to source code:

```bash
# Run as read-only user
sudo -u readonly-user jnkn scan /path/to/code

# Or in container with read-only mount
docker run -v /code:/code:ro jnkn scan /code
```

## Future Ideas

### Short-term: Dependency Hash Verification

Verify dependencies match known-good hashes:

```toml
# pyproject.toml
[tool.jnkn.security]
verify_hashes = true
```

```bash
# requirements.lock with hashes
click==8.1.7 \
    --hash=sha256:ae74fb96c20a0277a1d615f1e4d73c8414f5a98db8b799a7931d1582f3390c28
```

### Short-term: Signed Releases

Sign releases with Sigstore/cosign:

```bash
# Verify release signature
cosign verify-blob --signature jnkn-0.1.0.tar.gz.sig jnkn-0.1.0.tar.gz
```

### Medium-term: SBOM Integration

Generate SBOM for analyzed codebases:

```bash
jnkn sbom --format cyclonedx -o project-sbom.json
```

Include jnkn-discovered dependencies:

```json
{
  "bomFormat": "CycloneDX",
  "components": [
    {
      "type": "application",
      "name": "payment-service",
      "dependencies": [
        {"ref": "infra:payment_db"},
        {"ref": "env:STRIPE_API_KEY"},
        {"ref": "config:kafka-credentials"}
      ]
    }
  ]
}
```

### Medium-term: Vulnerability Context

Show which vulnerabilities affect your dependency graph:

```bash
jnkn security --check-vulns
```

Output:
```
Vulnerability Impact Analysis:

CVE-2024-1234 in log4j affects:
  → file://services/java-api/pom.xml
  → Downstream impact: 12 services
  
  Blast radius:
    HIGH: payment-service, auth-service
    MEDIUM: notification-service
    LOW: analytics-worker (test only)
```

### Long-term: Supply Chain Graph

Extend the dependency graph to include package dependencies:

```
┌─────────────────────────────────────────────────────────┐
│                    jnkn Extended Graph                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Package Layer:     requests → urllib3 → ssl            │
│                          ↓                               │
│  Code Layer:        api_client.py                       │
│                          ↓                               │
│  Infra Layer:       env:API_ENDPOINT → infra:api_gateway│
│                                                          │
└─────────────────────────────────────────────────────────┘
```

```python
# Future: combine package deps with cross-domain deps
jnkn scan --include-packages .
```

### Long-term: Policy Enforcement

Define and enforce supply chain policies:

```yaml
# .jnkn/policies/supply-chain.yaml
policies:
  - name: no-unmaintained-deps
    rule: |
      package.last_update > now() - 365d
    
  - name: max-transitive-depth
    rule: |
      dependency.depth <= 5
    
  - name: approved-sources-only
    rule: |
      package.source in ["pypi.org", "npm.org", "internal.repo"]
```

```bash
jnkn check --policy supply-chain.yaml
```

### Long-term: Reproducible Analysis

Ensure analysis results are reproducible:

```bash
# Generate analysis with provenance
jnkn scan --provenance .

# Output includes:
# - jnkn version
# - Dependency hashes
# - Git commit SHA
# - Timestamp
# - Analysis checksum
```

```json
{
  "provenance": {
    "jnkn_version": "0.1.0",
    "jnkn_hash": "sha256:abc123...",
    "analyzed_commit": "def456...",
    "timestamp": "2025-01-15T10:30:00Z",
    "result_hash": "sha256:789xyz..."
  },
  "graph": { ... }
}
```