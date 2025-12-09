# Terraform Resource Patterns

All Terraform patterns Jnkn detects.

## Resources

```hcl
# ✅ Detected as infra:aws_db_instance.main
resource "aws_db_instance" "main" {
  identifier = "my-database"
  engine     = "postgres"
}

# ✅ Detected as infra:aws_s3_bucket.data
resource "aws_s3_bucket" "data" {
  bucket = "my-data-bucket"
}
```

### Node ID Format

```
infra:{resource_type}.{resource_name}
```

Examples:
- `infra:aws_db_instance.main`
- `infra:aws_s3_bucket.logs`
- `infra:google_compute_instance.web`

## Variables

```hcl
# ✅ Detected as infra:var.database_url
variable "database_url" {
  type        = string
  description = "Database connection URL"
}

# ✅ Detected as infra:var.api_key
variable "api_key" {
  type      = string
  sensitive = true
}
```

### Node ID Format

```
infra:var.{variable_name}
```

## Outputs

```hcl
# ✅ Detected as infra:output.database_endpoint
output "database_endpoint" {
  value = aws_db_instance.main.endpoint
}

# ✅ Detected as infra:output.bucket_arn
output "bucket_arn" {
  value = aws_s3_bucket.data.arn
}
```

### Node ID Format

```
infra:output.{output_name}
```

## Data Sources

```hcl
# ✅ Detected as infra:data.aws_ami.ubuntu
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]
}
```

### Node ID Format

```
infra:data.{data_type}.{data_name}
```

## Locals

```hcl
# ✅ Detected as infra:local.database_host
locals {
  database_host = var.database_url
  api_endpoint  = "https://${var.domain}/api"
}
```

### Node ID Format

```
infra:local.{local_name}
```

## Modules

```hcl
# ✅ Detected as infra:module.vpc
module "vpc" {
  source = "./modules/vpc"
  
  cidr_block = var.vpc_cidr
}
```

### Node ID Format

```
infra:module.{module_name}
```

## Dependencies Detected

Jnkn creates edges for:

### Variable References

```hcl
resource "aws_instance" "web" {
  ami = var.ami_id  # Edge: infra:aws_instance.web → infra:var.ami_id
}
```

### Resource References

```hcl
resource "aws_security_group_rule" "allow" {
  security_group_id = aws_security_group.main.id
  # Edge: infra:aws_security_group_rule.allow → infra:aws_security_group.main
}
```

### Output References

```hcl
output "instance_ip" {
  value = aws_instance.web.public_ip
  # Edge: infra:output.instance_ip → infra:aws_instance.web
}
```

## Cross-Domain Matching

Terraform resources are matched to env vars via token matching:

| Terraform | Env Var | Match Confidence |
|-----------|---------|------------------|
| `aws_db_instance.main_db` | `env:MAIN_DB_HOST` | HIGH (0.85) |
| `output.database_url` | `env:DATABASE_URL` | HIGH (0.92) |
| `var.api_key` | `env:API_KEY` | HIGH (0.90) |

## Not Detected

```hcl
# ❌ Dynamic blocks (partial support)
dynamic "setting" {
  for_each = var.settings
  content {
    name  = setting.value.name
    value = setting.value.value
  }
}

# ❌ Complex expressions
locals {
  name = var.enabled ? "prod" : "dev"
}
```
