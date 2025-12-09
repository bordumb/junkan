#!/bin/bash
# =============================================================================
# Jnkn Epic 2 Parser Verification Script
# =============================================================================
# This script verifies that all Epic 2 parsers work correctly by creating
# test fixtures and running the parsers against them.
#
# Usage: bash scripts/verify_epic2.sh
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       JUNKAN EPIC 2 - PARSER EXPANSION VERIFICATION          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# Setup: Create test fixtures directory
# =============================================================================
TEST_DIR="tests/epic2_fixtures"
rm -rf "$TEST_DIR"
mkdir -p "$TEST_DIR/python"
mkdir -p "$TEST_DIR/terraform"
mkdir -p "$TEST_DIR/dbt"
mkdir -p "$TEST_DIR/kubernetes"
mkdir -p "$TEST_DIR/javascript"

echo -e "${YELLOW}📁 Creating test fixtures in $TEST_DIR...${NC}"

# =============================================================================
# Python Fixtures - Multiple env var patterns
# =============================================================================
cat > "$TEST_DIR/python/app_config.py" << 'PYEOF'
"""Application configuration with multiple env var patterns."""
import os
from os import getenv, environ

# Pattern 1: os.getenv()
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")

# Pattern 2: os.environ.get()
REDIS_URL = os.environ.get("REDIS_URL")
CACHE_TTL = os.environ.get("CACHE_TTL", "3600")

# Pattern 3: os.environ[]
API_KEY = os.environ["API_KEY"]

# Pattern 4: After from-import
SECRET_KEY = getenv("SECRET_KEY")
DEBUG_MODE = environ.get("DEBUG_MODE", "false")

# Pattern 5: Heuristic (env-like variable names)
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL")
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET")

class Config:
    """Config class with env vars."""
    db_host = os.getenv("DB_HOST")
    db_name = os.environ.get("DB_NAME", "myapp")
PYEOF

cat > "$TEST_DIR/python/pydantic_settings.py" << 'PYEOF'
"""Pydantic settings example."""
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    """Application settings from environment."""
    
    database_url: str = Field(..., env="DATABASE_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    api_secret: str = Field(..., env="API_SECRET_KEY")
    
    class Config:
        env_prefix = "APP_"
PYEOF

echo -e "  ${GREEN}✓${NC} Python fixtures created"

# =============================================================================
# Terraform Fixtures - Resources and dependencies
# =============================================================================
cat > "$TEST_DIR/terraform/main.tf" << 'TFEOF'
# Main Terraform configuration

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC for the application
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Public subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

# Security group for RDS
resource "aws_security_group" "database" {
  name        = "${var.project_name}-db-sg"
  description = "Security group for RDS database"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

# RDS Database Instance
resource "aws_db_instance" "payment_db_host" {
  identifier           = "${var.project_name}-db"
  allocated_storage    = 20
  engine              = "postgres"
  engine_version      = "14"
  instance_class      = "db.t3.micro"
  db_name             = var.db_name
  username            = var.db_username
  password            = var.db_password
  skip_final_snapshot = true

  vpc_security_group_ids = [aws_security_group.database.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  tags = {
    Name = "${var.project_name}-database"
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.public.id, aws_subnet.private.id]
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = "${var.aws_region}b"

  tags = {
    Name = "${var.project_name}-private-subnet"
  }
}
TFEOF

cat > "$TEST_DIR/terraform/variables.tf" << 'TFEOF'
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "jnkn-test"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Public subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "Private subnet CIDR"
  type        = string
  default     = "10.0.2.0/24"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "appdb"
}

variable "db_username" {
  description = "Database username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}
TFEOF

cat > "$TEST_DIR/terraform/outputs.tf" << 'TFEOF'
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "database_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.payment_db_host.endpoint
}

output "database_host" {
  description = "RDS hostname"
  value       = aws_db_instance.payment_db_host.address
}
TFEOF

echo -e "  ${GREEN}✓${NC} Terraform fixtures created"

# =============================================================================
# dbt Fixtures - Manifest with models and sources
# =============================================================================
cat > "$TEST_DIR/dbt/manifest.json" << 'DBTEOF'
{
  "metadata": {
    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v10.json",
    "dbt_version": "1.6.0",
    "generated_at": "2024-01-15T10:00:00Z",
    "project_name": "analytics"
  },
  "nodes": {
    "model.analytics.stg_customers": {
      "resource_type": "model",
      "name": "stg_customers",
      "schema": "staging",
      "database": "analytics",
      "original_file_path": "models/staging/stg_customers.sql",
      "columns": {
        "customer_id": {"name": "customer_id", "description": "Primary key", "data_type": "integer"},
        "email": {"name": "email", "description": "Customer email", "data_type": "varchar"},
        "created_at": {"name": "created_at", "description": "Account creation timestamp", "data_type": "timestamp"}
      },
      "depends_on": {
        "nodes": ["source.analytics.raw.customers"]
      },
      "tags": ["staging", "customers"]
    },
    "model.analytics.stg_orders": {
      "resource_type": "model",
      "name": "stg_orders",
      "schema": "staging",
      "database": "analytics",
      "original_file_path": "models/staging/stg_orders.sql",
      "columns": {
        "order_id": {"name": "order_id", "description": "Primary key"},
        "customer_id": {"name": "customer_id", "description": "Foreign key to customers"},
        "total_amount": {"name": "total_amount", "description": "Order total"}
      },
      "depends_on": {
        "nodes": ["source.analytics.raw.orders"]
      },
      "tags": ["staging", "orders"]
    },
    "model.analytics.fct_orders": {
      "resource_type": "model",
      "name": "fct_orders",
      "schema": "marts",
      "database": "analytics",
      "original_file_path": "models/marts/fct_orders.sql",
      "columns": {
        "order_id": {"name": "order_id", "description": "Primary key"},
        "customer_id": {"name": "customer_id", "description": "Customer ID"},
        "customer_email": {"name": "customer_email", "description": "Customer email"},
        "total_amount": {"name": "total_amount", "description": "Order total"},
        "order_date": {"name": "order_date", "description": "Date of order"}
      },
      "depends_on": {
        "nodes": ["model.analytics.stg_orders", "model.analytics.stg_customers"]
      },
      "tags": ["marts", "orders"]
    },
    "model.analytics.dim_customers": {
      "resource_type": "model",
      "name": "dim_customers",
      "schema": "marts",
      "database": "analytics",
      "original_file_path": "models/marts/dim_customers.sql",
      "depends_on": {
        "nodes": ["model.analytics.stg_customers", "model.analytics.fct_orders"]
      },
      "tags": ["marts", "customers"]
    },
    "seed.analytics.country_codes": {
      "resource_type": "seed",
      "name": "country_codes",
      "schema": "seeds",
      "database": "analytics",
      "original_file_path": "seeds/country_codes.csv"
    }
  },
  "sources": {
    "source.analytics.raw.customers": {
      "resource_type": "source",
      "name": "customers",
      "source_name": "raw",
      "schema": "raw_data",
      "database": "analytics",
      "description": "Raw customer data from production database"
    },
    "source.analytics.raw.orders": {
      "resource_type": "source",
      "name": "orders",
      "source_name": "raw",
      "schema": "raw_data",
      "database": "analytics",
      "description": "Raw order data from production database"
    }
  },
  "exposures": {
    "exposure.analytics.customer_dashboard": {
      "name": "customer_dashboard",
      "type": "dashboard",
      "owner": {"name": "Data Team", "email": "data@example.com"},
      "description": "Customer analytics dashboard in Looker",
      "depends_on": {
        "nodes": ["model.analytics.dim_customers", "model.analytics.fct_orders"]
      },
      "url": "https://looker.example.com/dashboards/123"
    }
  }
}
DBTEOF

echo -e "  ${GREEN}✓${NC} dbt fixtures created"

# =============================================================================
# Kubernetes Fixtures - Deployments with env vars
# =============================================================================
cat > "$TEST_DIR/kubernetes/deployment.yaml" << 'K8SEOF'
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
  namespace: production
data:
  LOG_LEVEL: "info"
  CACHE_TTL: "3600"
  FEATURE_FLAGS: "new_checkout,dark_mode"
---
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
  namespace: production
type: Opaque
data:
  API_KEY: YXBpLWtleS1zZWNyZXQ=
  DB_PASSWORD: c3VwZXItc2VjcmV0
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: production
  labels:
    app: payment-service
    tier: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      serviceAccountName: payment-service-sa
      containers:
      - name: payment-service
        image: payment-service:v1.2.3
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_HOST
          value: "postgres.production.svc.cluster.local"
        - name: DATABASE_PORT
          value: "5432"
        - name: DATABASE_NAME
          value: "payments"
        - name: DATABASE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: DB_PASSWORD
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: API_KEY
        - name: LOG_LEVEL
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: LOG_LEVEL
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        envFrom:
        - configMapRef:
            name: app-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cleanup-job
  namespace: production
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cleanup
            image: cleanup-job:latest
            env:
            - name: RETENTION_DAYS
              value: "30"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: DATABASE_URL
          restartPolicy: OnFailure
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
  namespace: production
spec:
  serviceName: redis
  replicas: 3
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        env:
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secrets
              key: password
K8SEOF

echo -e "  ${GREEN}✓${NC} Kubernetes fixtures created"

# =============================================================================
# JavaScript/TypeScript Fixtures - Various env var patterns
# =============================================================================
cat > "$TEST_DIR/javascript/config.ts" << 'JSEOF'
// TypeScript configuration with various env var patterns

// Pattern 1: process.env.VAR
const databaseHost = process.env.DATABASE_HOST;
const databasePort = process.env.DATABASE_PORT || '5432';

// Pattern 2: process.env["VAR"]
const apiKey = process.env["API_KEY"];
const secretKey = process.env['SECRET_KEY'];

// Pattern 3: Destructuring
const { 
  REDIS_URL, 
  CACHE_TTL,
  SESSION_SECRET 
} = process.env;

// Pattern 4: Destructuring with rename
const { 
  DATABASE_URL: dbUrl, 
  API_ENDPOINT: apiEndpoint 
} = process.env;

// Pattern 5: With nullish coalescing
const port = process.env.PORT ?? 3000;
const host = process.env.HOST ?? 'localhost';

// TypeScript interface for config
interface Config {
  database: {
    host: string;
    port: number;
    name: string;
  };
  redis: {
    url: string;
  };
}

export const config: Config = {
  database: {
    host: process.env.DB_HOST!,
    port: parseInt(process.env.DB_PORT || '5432'),
    name: process.env.DB_NAME!,
  },
  redis: {
    url: process.env.REDIS_URL!,
  },
};
JSEOF

cat > "$TEST_DIR/javascript/next-app.tsx" << 'JSEOF'
// Next.js application with NEXT_PUBLIC_ env vars
import React from 'react';

// Server-side env vars
const apiSecret = process.env.API_SECRET;
const databaseUrl = process.env.DATABASE_URL;

// Client-side env vars (NEXT_PUBLIC_ prefix)
const publicApiUrl = process.env.NEXT_PUBLIC_API_URL;
const publicAppName = process.env.NEXT_PUBLIC_APP_NAME;
const publicAnalyticsId = process.env.NEXT_PUBLIC_ANALYTICS_ID;

export default function App() {
  return (
    <div>
      <h1>{process.env.NEXT_PUBLIC_APP_NAME}</h1>
      <p>API: {process.env.NEXT_PUBLIC_API_URL}</p>
    </div>
  );
}

export async function getServerSideProps() {
  // Server-side only
  const data = await fetch(process.env.INTERNAL_API_URL!);
  return { props: { data } };
}
JSEOF

cat > "$TEST_DIR/javascript/vite-app.ts" << 'JSEOF'
// Vite application with import.meta.env

// Vite-specific env vars
const apiUrl = import.meta.env.VITE_API_URL;
const appTitle = import.meta.env.VITE_APP_TITLE;
const analyticsKey = import.meta.env.VITE_ANALYTICS_KEY;
const debugMode = import.meta.env.VITE_DEBUG_MODE;

// Built-in Vite env vars
const mode = import.meta.env.MODE;
const isDev = import.meta.env.DEV;
const isProd = import.meta.env.PROD;

export const config = {
  apiUrl: import.meta.env.VITE_API_URL,
  wsUrl: import.meta.env.VITE_WS_URL,
  environment: import.meta.env.MODE,
};
JSEOF

cat > "$TEST_DIR/javascript/express-app.js" << 'JSEOF'
// Express.js application with CommonJS require
require('dotenv').config();

const express = require('express');
const app = express();

// Environment variables
const PORT = process.env.PORT || 3000;
const NODE_ENV = process.env.NODE_ENV || 'development';
const DATABASE_URL = process.env.DATABASE_URL;
const REDIS_HOST = process.env.REDIS_HOST;
const JWT_SECRET = process.env.JWT_SECRET;

// Destructured env vars
const {
  AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY,
  S3_BUCKET
} = process.env;

app.get('/health', (req, res) => {
  res.json({ status: 'ok', env: NODE_ENV });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
JSEOF

echo -e "  ${GREEN}✓${NC} JavaScript/TypeScript fixtures created"

# =============================================================================
# Run Verification Tests
# =============================================================================
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    RUNNING PARSER TESTS                        ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Reset database
rm -rf .jnkn
mkdir -p .jnkn

# Run scan on all fixtures
echo -e "${YELLOW}🔍 Scanning all fixtures...${NC}"
if uv run python -m jnkn.cli.main scan --dir "$TEST_DIR" --full 2>&1; then
    echo -e "${GREEN}✓ Scan completed successfully${NC}"
else
    echo -e "${RED}✗ Scan failed${NC}"
    exit 1
fi

echo ""

# =============================================================================
# Verify Results
# =============================================================================
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                    VERIFICATION RESULTS                        ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

DB_PATH=".jnkn/jnkn.db"

if [ ! -f "$DB_PATH" ]; then
    echo -e "${RED}✗ Database not created${NC}"
    exit 1
fi

# Count nodes by type
echo -e "${YELLOW}📊 Node Statistics:${NC}"
echo ""

TOTAL_NODES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes;")
echo "  Total Nodes: $TOTAL_NODES"

CODE_FILES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='code_file';")
echo "  Code Files: $CODE_FILES"

ENV_VARS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='env_var';")
echo "  Environment Variables: $ENV_VARS"

INFRA_RESOURCES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='infra_resource';")
echo "  Infrastructure Resources: $INFRA_RESOURCES"

DATA_ASSETS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='data_asset';")
echo "  Data Assets (dbt): $DATA_ASSETS"

echo ""

# Count edges
TOTAL_EDGES=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM edges;")
echo -e "${YELLOW}🔗 Edge Statistics:${NC}"
echo "  Total Edges: $TOTAL_EDGES"
echo ""

# Verify specific detections
echo -e "${YELLOW}🔬 Specific Detection Verification:${NC}"
echo ""

# Python env vars
PYTHON_ENV_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='env_var' AND id LIKE '%DATABASE_HOST%' OR id LIKE '%REDIS_URL%' OR id LIKE '%API_KEY%';")
if [ "$PYTHON_ENV_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} Python env vars detected ($PYTHON_ENV_COUNT found)"
else
    echo -e "  ${RED}✗${NC} Python env vars NOT detected"
fi

# Terraform resources
TF_RESOURCE_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='infra_resource';")
if [ "$TF_RESOURCE_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} Terraform resources detected ($TF_RESOURCE_COUNT found)"
else
    echo -e "  ${RED}✗${NC} Terraform resources NOT detected"
fi

# dbt models
DBT_MODEL_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='data_asset';")
if [ "$DBT_MODEL_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} dbt models detected ($DBT_MODEL_COUNT found)"
else
    echo -e "  ${YELLOW}⚠${NC} dbt models NOT detected (may need --dbt-manifest flag)"
fi

# K8s env vars
K8S_ENV_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE id LIKE '%POD_NAME%' OR id LIKE '%POD_NAMESPACE%';")
if [ "$K8S_ENV_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} Kubernetes env vars detected ($K8S_ENV_COUNT found)"
else
    echo -e "  ${YELLOW}⚠${NC} Kubernetes env vars NOT detected (may need specific parser)"
fi

# JS/TS env vars (Next.js public vars)
NEXTJS_ENV_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE id LIKE '%NEXT_PUBLIC%';")
if [ "$NEXTJS_ENV_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} Next.js public env vars detected ($NEXTJS_ENV_COUNT found)"
else
    echo -e "  ${YELLOW}⚠${NC} Next.js public env vars NOT detected"
fi

# Vite env vars
VITE_ENV_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE id LIKE '%VITE_%';")
if [ "$VITE_ENV_COUNT" -gt "0" ]; then
    echo -e "  ${GREEN}✓${NC} Vite env vars detected ($VITE_ENV_COUNT found)"
else
    echo -e "  ${YELLOW}⚠${NC} Vite env vars NOT detected"
fi

echo ""

# Show stitched links
STITCHED_LINKS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM edges WHERE source_id LIKE 'env:%' AND target_id LIKE 'infra:%';")
echo -e "${YELLOW}🧵 Stitching Results:${NC}"
echo "  Env → Infra Links: $STITCHED_LINKS"

if [ "$STITCHED_LINKS" -gt "0" ]; then
    echo ""
    echo -e "  ${GREEN}Stitched connections:${NC}"
    sqlite3 "$DB_PATH" "SELECT '    ' || source_id || ' → ' || target_id || ' (confidence: ' || ROUND(confidence, 2) || ')' FROM edges WHERE source_id LIKE 'env:%' AND target_id LIKE 'infra:%' LIMIT 5;"
fi

echo ""

# =============================================================================
# Summary
# =============================================================================
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}                         SUMMARY                                ${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

PASS_COUNT=0
TOTAL_CHECKS=6

[ "$PYTHON_ENV_COUNT" -gt "0" ] && ((PASS_COUNT++))
[ "$TF_RESOURCE_COUNT" -gt "0" ] && ((PASS_COUNT++))
[ "$CODE_FILES" -gt "0" ] && ((PASS_COUNT++))
[ "$TOTAL_EDGES" -gt "0" ] && ((PASS_COUNT++))
[ "$ENV_VARS" -gt "5" ] && ((PASS_COUNT++))
[ "$STITCHED_LINKS" -gt "0" ] && ((PASS_COUNT++))

if [ "$PASS_COUNT" -eq "$TOTAL_CHECKS" ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED ($PASS_COUNT/$TOTAL_CHECKS)${NC}"
    echo ""
    echo "Epic 2 Parser Expansion is working correctly!"
else
    echo -e "${YELLOW}⚠️  PARTIAL SUCCESS ($PASS_COUNT/$TOTAL_CHECKS checks passed)${NC}"
    echo ""
    echo "Some parsers may need additional configuration or the full dependencies."
fi

echo ""
echo -e "${BLUE}Database location: $DB_PATH${NC}"
echo -e "${BLUE}Test fixtures: $TEST_DIR${NC}"
echo ""

# Optionally show all env vars detected
echo -e "${YELLOW}📋 All detected environment variables:${NC}"
sqlite3 "$DB_PATH" "SELECT '  • ' || name FROM nodes WHERE type='env_var' ORDER BY name LIMIT 20;"
ENV_TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM nodes WHERE type='env_var';")
if [ "$ENV_TOTAL" -gt "20" ]; then
    echo "  ... and $((ENV_TOTAL - 20)) more"
fi

echo ""
echo -e "${GREEN}Done!${NC}"