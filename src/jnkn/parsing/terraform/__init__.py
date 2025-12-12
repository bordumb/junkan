"""
Terraform parsing module for jnkn.

Provides parsing for Terraform HCL files and plan JSON output:
- TerraformParser: Static analysis of .tf files
- TerraformPlanParser: Rich analysis of terraform plan JSON output

Features:
- Resource extraction
- Variable and output detection
- Module dependencies
- Plan change analysis (create/update/delete/replace)
"""

from .parser import (
    TerraformParser,
    TerraformPlanParser,
    create_terraform_parser,
    create_terraform_plan_parser,
)

__all__ = [
    "TerraformParser",
    "TerraformPlanParser",
    "create_terraform_parser",
    "create_terraform_plan_parser",
]
