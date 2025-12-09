# Kubernetes Reference Patterns

All Kubernetes patterns Jnkn detects.

## Environment Variables

### Direct Values

```yaml
# ✅ Detected as env:DATABASE_URL
env:
  - name: DATABASE_URL
    value: "postgresql://localhost/db"
```

### ConfigMap References

```yaml
# ✅ Detected as env:DATABASE_HOST
# ✅ Creates edge to k8s:default/configmap/app-config
env:
  - name: DATABASE_HOST
    valueFrom:
      configMapKeyRef:
        name: app-config
        key: db-host
```

### Secret References

```yaml
# ✅ Detected as env:DATABASE_PASSWORD
# ✅ Creates edge to k8s:default/secret/app-secrets
env:
  - name: DATABASE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: db-password
```

### Field References

```yaml
# ✅ Detected as env:POD_NAME
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

## envFrom

### All Keys from ConfigMap

```yaml
# ✅ Creates edge to k8s:default/configmap/app-config
envFrom:
  - configMapRef:
      name: app-config
```

### All Keys from Secret

```yaml
# ✅ Creates edge to k8s:default/secret/app-secrets
envFrom:
  - secretRef:
      name: app-secrets
```

## Workload Types

Jnkn parses these Kubernetes resources:

| Kind | Detected |
|------|----------|
| Deployment | ✅ |
| StatefulSet | ✅ |
| DaemonSet | ✅ |
| Job | ✅ |
| CronJob | ✅ |
| Pod | ✅ |
| ReplicaSet | ✅ |

## Node ID Format

```
k8s:{namespace}/{kind}/{name}
```

Examples:
- `k8s:default/deployment/api-server`
- `k8s:production/statefulset/database`
- `k8s:default/configmap/app-config`
- `k8s:default/secret/app-secrets`

## Dependencies Detected

### Workload → ConfigMap

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  namespace: default
spec:
  template:
    spec:
      containers:
        - name: api
          envFrom:
            - configMapRef:
                name: api-config
# Edge: k8s:default/deployment/api-server → k8s:default/configmap/api-config
```

### Workload → Secret

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  template:
    spec:
      containers:
        - name: api
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-creds
                  key: password
# Edge: k8s:default/deployment/api-server → k8s:default/secret/db-creds
```

### Workload → ServiceAccount

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
spec:
  template:
    spec:
      serviceAccountName: api-sa
# Edge: k8s:default/deployment/api-server → k8s:default/serviceaccount/api-sa
```

## Cross-Domain Matching

K8s env vars are matched to other domains:

| K8s Env Var | Python | Confidence |
|-------------|--------|------------|
| `DATABASE_URL` | `os.getenv("DATABASE_URL")` | HIGH (0.95) |
| `API_KEY` | `env:API_KEY` | HIGH (0.90) |

| K8s ConfigMap | Terraform | Confidence |
|---------------|-----------|------------|
| `api-config` | `infra:aws_ssm_parameter.api_config` | MEDIUM (0.75) |

## Multi-Document YAML

Jnkn handles multi-document YAML files:

```yaml
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  DATABASE_HOST: "localhost"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  template:
    spec:
      containers:
        - name: app
          envFrom:
            - configMapRef:
                name: app-config
```

Both resources are detected and linked.

## Not Detected

```yaml
# ❌ Helm templates (pre-rendered)
env:
  - name: {{ .Values.envName }}
    value: {{ .Values.envValue }}

# ❌ Kustomize patches (pre-rendered)
# Process with helm template or kustomize build first
```
