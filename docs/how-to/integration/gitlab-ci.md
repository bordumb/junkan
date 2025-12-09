# GitLab CI

Set up Jnkn in GitLab CI/CD pipelines.

## Minimal Setup

```yaml
# .gitlab-ci.yml
jnkn:
  image: python:3.11-slim
  script:
    - pip install jnkn[full]
    - jnkn scan
    - jnkn stats
  only:
    changes:
      - "**/*.py"
      - "**/*.tf"
```

## With Caching

```yaml
jnkn:
  image: python:3.11-slim
  cache:
    key: jnkn-$CI_COMMIT_REF_SLUG
    paths:
      - .jnkn/
  script:
    - pip install jnkn[full]
    - jnkn scan
    - jnkn stats
```

## Block Pipeline on High Impact

```yaml
jnkn:
  image: python:3.11-slim
  script:
    - pip install jnkn[full] jq
    - jnkn scan
    - |
      MAX_IMPACT=10
      FAILED=0
      
      for f in $(git diff --name-only origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD | grep -E '\.(py|tf)$'); do
        IMPACT=$(jnkn blast "file://$f" --format json 2>/dev/null | jq '.total_impacted_count // 0')
        if [ "$IMPACT" -gt "$MAX_IMPACT" ]; then
          echo "High impact ($IMPACT) for $f"
          FAILED=1
        fi
      done
      
      if [ "$FAILED" -eq 1 ]; then
        exit 1
      fi
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

## Docker Image

Use a pre-built image for faster pipelines:

```yaml
jnkn:
  image: ghcr.io/jnkn-io/jnkn:latest
  script:
    - jnkn scan
    - jnkn stats
```

## Parallel Jobs

```yaml
.jnkn-template:
  image: python:3.11-slim
  before_script:
    - pip install jnkn[full]

jnkn-backend:
  extends: .jnkn-template
  script:
    - jnkn scan --dir backend/

jnkn-infra:
  extends: .jnkn-template
  script:
    - jnkn scan --dir terraform/
```

## Artifacts

Save results for later stages:

```yaml
jnkn:
  script:
    - jnkn scan
    - jnkn stats --format json > stats.json
    - jnkn export --format json > graph.json
  artifacts:
    paths:
      - stats.json
      - graph.json
    expire_in: 1 week
```
