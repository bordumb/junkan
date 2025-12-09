#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🧪 INITIATING E2E SURVIVAL TEST...${NC}"

# ==============================================================================
# 1. SETUP: Ensure the Codebase is Exact
# ==============================================================================
mkdir -p src/jnkn/languages/python
mkdir -p src/jnkn/languages/terraform

# Write the Python Query (How we find Env Vars)
cat << 'EOF' > src/jnkn/languages/python/imports.scm
(import_statement name: (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @import)

; Pattern 1: os.getenv("VAR_NAME")
(call
  function: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @env_var)
  (#eq? @_obj "os")
  (#eq? @_method "getenv"))

; Pattern 2: os.environ.get("VAR_NAME")
(call
  function: (attribute
    object: (attribute
      object: (identifier) @_obj
      attribute: (identifier) @_attr)
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @env_var)
  (#eq? @_obj "os")
  (#eq? @_attr "environ")
  (#eq? @_method "get"))

; Pattern 3: os.environ["VAR_NAME"]
(subscript
  value: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_attr)
  subscript: (string) @environ_key
  (#eq? @_obj "os")
  (#eq? @_attr "environ"))

; Pattern 4: getenv("VAR_NAME")
(call
  function: (identifier) @_func
  arguments: (argument_list (string) @env_var)
  (#eq? @_func "getenv"))
EOF

# Write empty definitions.scm
cat << 'EOF' > src/jnkn/languages/python/definitions.scm
; Capture Function Definitions
(function_definition
  name: (identifier) @definition)

; Capture Class Definitions
(class_definition
  name: (identifier) @definition)
EOF

# Write the Terraform Query (How we find Resources)
cat << 'EOF' > src/jnkn/languages/terraform/resources.scm
(block
  (identifier) @block_type
  (string_lit) @res_type
  (string_lit) @res_name
  (#eq? @block_type "resource")) @resource_block
EOF

# ==============================================================================
# 2. FIXTURES: Create the "Glue" Scenario
# ==============================================================================
echo "🛠️  Creating Test Fixtures (The 'Payment DB' Scenario)..."
rm -rf tests/e2e_live
mkdir -p tests/e2e_live/infra

# Fixture 1: The Python Service
cat << 'EOF' > tests/e2e_live/payment_service.py
import os
import boto3

def connect():
    # CRITICAL DEPENDENCY: If this env var changes, the app crashes.
    host = os.getenv("PAYMENT_DB_HOST")
    print(f"Connecting to {host}...")
EOF

# Fixture 2: The Terraform Infrastructure
cat << 'EOF' > tests/e2e_live/infra/rds.tf
resource "aws_db_instance" "payment_db_host" {
  allocated_storage    = 10
  db_name              = "mydb"
  engine               = "mysql"
  instance_class       = "db.t3.micro"
}
EOF

# ==============================================================================
# 3. EXECUTION: Run the Engine
# ==============================================================================
echo "🚀 Running Jnkn High-Road Engine..."

# Reset DB
rm -rf .jnkn
mkdir -p .jnkn

# Run Scan with full flag to ensure clean state
uv run python -m jnkn.cli.main scan --dir tests/e2e_live --full

# ==============================================================================
# 4. VERIFICATION: Prove the Link Exists
# ==============================================================================
echo -e "\n${GREEN}🔍 VERIFYING STITCHING LOGIC...${NC}"

DB_PATH=".jnkn/jnkn.db"

# Check if nodes exist
ENV_NODE_COUNT=$(sqlite3 $DB_PATH "SELECT count(*) FROM nodes WHERE id LIKE 'env:%PAYMENT%';")
INFRA_NODE_COUNT=$(sqlite3 $DB_PATH "SELECT count(*) FROM nodes WHERE type = 'infra_resource';")

if [ "$ENV_NODE_COUNT" -eq "0" ]; then
    echo -e "${RED}❌ FAILED: Python Env Var node not found.${NC}"
    echo "Debug: Checking all nodes..."
    sqlite3 $DB_PATH "SELECT id, type FROM nodes;"
    exit 1
fi

if [ "$INFRA_NODE_COUNT" -eq "0" ]; then
    echo -e "${RED}❌ FAILED: Terraform Resource node not found.${NC}"
    echo "Debug: Checking all nodes..."
    sqlite3 $DB_PATH "SELECT id, type FROM nodes;"
    exit 1
fi

# Check the "Magic" Link (The Stitch)
LINK_COUNT=$(sqlite3 $DB_PATH "SELECT count(*) FROM edges WHERE source_id LIKE 'env:%PAYMENT%' AND target_id LIKE 'infra:%';")

echo "---------------------------------------------------"
echo "Stats:"
echo "Env Nodes Found:   $ENV_NODE_COUNT"
echo "Infra Nodes Found: $INFRA_NODE_COUNT"
echo "Stitched Links:    $LINK_COUNT"
echo "---------------------------------------------------"

# Debug: Show all edges
echo -e "\n${YELLOW}Debug: All edges in database:${NC}"
sqlite3 $DB_PATH "SELECT source_id, target_id, type, confidence FROM edges;"

# Debug: Show all nodes
echo -e "\n${YELLOW}Debug: All nodes in database:${NC}"
sqlite3 $DB_PATH "SELECT id, name, type FROM nodes;"

if [ "$LINK_COUNT" -gt "0" ]; then
    echo -e "\n${GREEN}✅ SUCCESS: The system successfully bridged Code and Infrastructure!${NC}"
    echo "Proof: The Python file 'payment_service.py' is now aware of 'rds.tf'."
    
    # Show the actual link
    echo -e "\n${GREEN}Stitched Edge:${NC}"
    sqlite3 $DB_PATH "SELECT source_id, target_id, confidence, match_strategy FROM edges WHERE source_id LIKE 'env:%' AND target_id LIKE 'infra:%';"
else
    echo -e "${RED}❌ FAILURE: The Stitcher did not connect the Env Var to the Terraform Resource.${NC}"
    echo "Debug Advice: Check 'src/jnkn/core/stitching.py' fuzzy matching logic."
    exit 1
fi