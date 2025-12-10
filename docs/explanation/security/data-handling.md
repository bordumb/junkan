# Data Handling

Privacy, data retention, and opt-in telemetry via PostHog using anonymous IDs.

## Current Design

jnkn is designed with privacy as a core principle. The tool processes your code locally, stores data locally, and only sends anonymous usage telemetry if you explicitly opt in.

### Local-First Architecture

All analysis happens on your machine:

```
Your Codebase → jnkn CLI → Local SQLite DB → Local Output
                   ↓
            (opt-in only)
                   ↓
         Anonymous Telemetry → PostHog
```

**What stays local**:
- Your source code (never transmitted)
- The dependency graph (stored in `.jnkn/jnkn.db`)
- Configuration files (`.jnkn/config.yaml`)
- Suppression rules (`.jnkn/suppressions.yaml`)
- All analysis results

**What is transmitted (if opted in)**:
- Anonymous usage events (command invocations, timing)
- Aggregate statistics (node counts, scan duration)
- Error categories (not stack traces or code)

### Telemetry System

Telemetry is **disabled by default** and requires explicit opt-in:

```python
class TelemetryClient:
    @property
    def is_enabled(self) -> bool:
        """Check if telemetry is enabled in config."""
        if not self.config_path.exists():
            return False
        
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f) or {}
            # Default to False if not explicitly set
            return data.get("telemetry", {}).get("enabled", False)
```

### Opting In

Enable telemetry during initialization or in config:

```bash
# During init
jnkn init
# Prompts: "Enable anonymous telemetry? [y/N]"

# Or manually in config
```

```yaml
# .jnkn/config.yaml
telemetry:
  enabled: true
  distinct_id: "a1b2c3d4-..."  # Auto-generated anonymous UUID
```

### Anonymous Identification

Each installation gets a random UUID that cannot be traced back to you:

```python
@property
def distinct_id(self) -> str:
    """Get or generate persistent anonymous ID."""
    if self._distinct_id:
        return self._distinct_id
    
    # Try to load from config
    if self.config_path.exists():
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f) or {}
            self._distinct_id = data.get("telemetry", {}).get("distinct_id")
    
    # Generate new if not found
    if not self._distinct_id:
        self._distinct_id = str(uuid.uuid4())
    
    return self._distinct_id
```

The ID is:
- A random UUID (e.g., `f47ac10b-58cc-4372-a567-0e02b2c3d479`)
- Not linked to your name, email, or any PII
- Stored locally in your config file
- Consistent across sessions (for usage patterns)
- Deletable by removing the config entry

### What We Collect

When telemetry is enabled, we track:

```python
def track(self, event_name: str, properties: Dict[str, Any] = None):
    payload = {
        "api_key": POSTHOG_API_KEY,
        "event": event_name,
        "properties": {
            "distinct_id": self.distinct_id,     # Anonymous UUID
            "$lib": "jnkn-cli",                  # Client identifier
            "$os": platform.system(),            # OS name (Linux/Darwin/Windows)
            "$python_version": platform.python_version(),  # Python version
            "timestamp": datetime.utcnow().isoformat(),
            **(properties or {})
        }
    }
```

**Events tracked**:

| Event | Properties | Purpose |
|-------|------------|---------|
| `scan_complete` | `node_count`, `edge_count`, `duration_ms`, `languages` | Understand usage patterns |
| `blast_radius_query` | `depth`, `result_count` | Optimize algorithms |
| `stitch_complete` | `edge_count`, `rule_names` | Rule effectiveness |
| `error` | `error_type` (not message) | Bug prioritization |
| `cli_command` | `command_name` | Feature usage |

**What we never collect**:
- Source code or file contents
- File paths or names
- Environment variable names/values
- Node or edge identifiers
- Error messages or stack traces
- Git repository names or URLs
- IP addresses (PostHog anonymizes)

### Transmission Mechanism

Telemetry uses fire-and-forget HTTP requests that don't block the CLI:

```python
def track(self, event_name: str, properties: Dict[str, Any] = None):
    if not self.is_enabled:
        return
    
    # Non-blocking: runs in background thread
    thread = threading.Thread(target=self._send_request, args=(payload,))
    thread.daemon = False  # Let it finish if possible
    thread.start()

def _send_request(self, payload: Dict[str, Any]):
    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{POSTHOG_HOST}/capture/",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with request.urlopen(req, timeout=5.0) as _:
            pass
    except Exception:
        # Silent fail - telemetry should never break functionality
        pass
```

Key properties:
- **Non-blocking**: Runs in background thread
- **Fail-safe**: Silent failure, no impact on CLI
- **Timeout**: 5 second limit prevents hangs
- **Graceful shutdown**: Waits for pending requests on exit

### Data Retention

**Local data** (`.jnkn/` directory):
- Retained indefinitely until you delete it
- Delete with `rm -rf .jnkn/` or `jnkn clean`
- Not synced to any cloud service

**Telemetry data** (PostHog):
- Retained for 2 years (PostHog default)
- Aggregated for analysis, not stored per-event long-term
- No way to link anonymous ID to individual users
- GDPR-compliant (PostHog EU hosting option)

### Opting Out

Disable telemetry at any time:

```yaml
# .jnkn/config.yaml
telemetry:
  enabled: false
```

Or delete the distinct_id to reset:

```yaml
# .jnkn/config.yaml
telemetry:
  enabled: false
  # Remove distinct_id line entirely
```

### Network Behavior

When telemetry is enabled, jnkn makes HTTPS requests to:
- `app.posthog.com` (telemetry events)

When telemetry is disabled:
- **Zero network requests**
- jnkn works entirely offline
- No phone-home or license checks

### CI/CD Environments

In CI/CD, telemetry is typically disabled:

```yaml
# GitHub Actions
- name: Run jnkn
  run: |
    jnkn scan .
  env:
    JNKN_TELEMETRY: "false"  # Environment variable override
```

Or via config committed to repo:

```yaml
# .jnkn/config.yaml (committed)
telemetry:
  enabled: false
```

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR MACHINE                                 │
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐ │
│  │              │     │              │     │                      │ │
│  │  Your Code   │────▶│   jnkn CLI   │────▶│  .jnkn/jnkn.db      │ │
│  │  (private)   │     │  (analysis)  │     │  (local storage)     │ │
│  │              │     │              │     │                      │ │
│  └──────────────┘     └──────┬───────┘     └──────────────────────┘ │
│                              │                                       │
│                              │ (if telemetry enabled)               │
│                              ▼                                       │
│                    ┌──────────────────┐                             │
│                    │ Anonymous Events │                             │
│                    │ - command used   │                             │
│                    │ - node count     │                             │
│                    │ - timing         │                             │
│                    └────────┬─────────┘                             │
│                              │                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │ HTTPS (encrypted)
                               ▼
                    ┌──────────────────┐
                    │                  │
                    │  PostHog Cloud   │
                    │  (telemetry)     │
                    │                  │
                    └──────────────────┘
```

## Future Ideas

### Short-term: Telemetry Transparency

Show exactly what would be sent before enabling:

```bash
jnkn telemetry preview
```

Output:
```
If telemetry were enabled, the following would be sent:

Event: scan_complete
Properties:
  distinct_id: f47ac10b-58cc-4372-a567-0e02b2c3d479
  $os: Darwin
  $python_version: 3.12.0
  node_count: 1234
  edge_count: 567
  duration_ms: 2340
  languages: ["python", "terraform"]

No source code, file paths, or identifiers are included.
```

### Short-term: Telemetry Log

Log what's being sent for audit:

```yaml
telemetry:
  enabled: true
  log_events: true  # Write to .jnkn/telemetry.log
```

### Medium-term: Self-Hosted Telemetry

For enterprises that want usage data without external transmission:

```yaml
telemetry:
  enabled: true
  endpoint: "https://posthog.internal.company.com"
  api_key: "phc_..."
```

### Medium-term: Aggregate-Only Mode

Send only daily aggregates, not per-event data:

```yaml
telemetry:
  enabled: true
  mode: "aggregate"  # vs "events"
```

Sends once daily:
```json
{
  "date": "2025-01-15",
  "total_scans": 47,
  "total_nodes_analyzed": 125000,
  "avg_scan_duration_ms": 3400,
  "languages_used": ["python", "terraform", "kubernetes"]
}
```

### Long-term: Privacy-Preserving Analytics

Use differential privacy for stronger guarantees:

```python
def add_noise(value: int, epsilon: float = 1.0) -> int:
    """Add Laplacian noise for differential privacy."""
    import numpy as np
    noise = np.random.laplace(0, 1/epsilon)
    return int(value + noise)

# Instead of exact count
# node_count: 1234
# Send noisy count
# node_count: 1241 (within ±10 of true value)
```

### Long-term: Local-Only Analytics

Aggregate usage locally and display insights without any transmission:

```bash
jnkn stats
```

Output:
```
Your jnkn Usage (local data only):

Total scans: 147
Files analyzed: 45,230
Dependencies discovered: 2,341
False positives suppressed: 23

Most common languages:
  1. Python (67%)
  2. Terraform (23%)
  3. Kubernetes (10%)

Average scan time: 2.3s
```