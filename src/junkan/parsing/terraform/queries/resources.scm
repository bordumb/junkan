; Terraform HCL Resource Detection
; For use with tree-sitter-hcl grammar

; =============================================================================
; Resource Blocks
; =============================================================================

; resource "type" "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @resource_type
  (string_lit) @resource_name
  (#eq? @block_type "resource"))

; =============================================================================
; Data Blocks
; =============================================================================

; data "type" "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @data_type
  (string_lit) @data_name
  (#eq? @block_type "data"))

; =============================================================================
; Variable Blocks
; =============================================================================

; variable "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @variable_name
  (#eq? @block_type "variable"))

; =============================================================================
; Output Blocks
; =============================================================================

; output "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @output_name
  (#eq? @block_type "output"))

; =============================================================================
; Module Blocks
; =============================================================================

; module "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @module_name
  (#eq? @block_type "module"))

; =============================================================================
; Provider Blocks
; =============================================================================

; provider "name" { ... }
(block
  (identifier) @block_type
  (string_lit) @provider_name
  (#eq? @block_type "provider"))

; =============================================================================
; Locals Block
; =============================================================================

; locals { ... }
(block
  (identifier) @locals_block
  (#eq? @locals_block "locals"))

; =============================================================================
; Terraform Block
; =============================================================================

; terraform { ... }
(block
  (identifier) @terraform_block
  (#eq? @terraform_block "terraform"))

; =============================================================================
; References (within expressions)
; =============================================================================

; Attribute access on resources (e.g., aws_instance.main.id)
(get_attr
  (get_attr
    (variable_expr) @ref_base
    (identifier) @ref_name)
  (identifier) @ref_attr)

; Simple variable reference (e.g., var.name)
(get_attr
  (variable_expr) @var_base
  (identifier) @var_ref
  (#eq? @var_base "var"))

; Local reference (e.g., local.name)
(get_attr
  (variable_expr) @local_base
  (identifier) @local_ref
  (#eq? @local_base "local"))

; Module output reference (e.g., module.name.output)
(get_attr
  (get_attr
    (variable_expr) @module_base
    (identifier) @module_ref)
  (identifier) @module_output
  (#eq? @module_base "module"))

; Data source reference (e.g., data.type.name.attr)
(get_attr
  (get_attr
    (get_attr
      (variable_expr) @data_base
      (identifier) @data_type_ref)
    (identifier) @data_name_ref)
  (identifier) @data_attr
  (#eq? @data_base "data"))