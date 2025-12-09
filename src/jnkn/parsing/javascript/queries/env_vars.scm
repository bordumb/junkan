; Environment Variable Detection for JavaScript/TypeScript
; Covers all common patterns for environment variable access

; =============================================================================
; Node.js process.env Patterns
; =============================================================================

; Pattern 1: process.env.VAR_NAME
(member_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  property: (property_identifier) @env_var
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 2: process.env["VAR_NAME"]
(subscript_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  index: (string) @env_var_bracket
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 3: process.env['VAR_NAME'] with template literal
(subscript_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  index: (template_string) @env_var_template
  (#eq? @_process "process")
  (#eq? @_env "env"))

; =============================================================================
; Destructuring Patterns
; =============================================================================

; Pattern 4: const { VAR } = process.env
(variable_declarator
  name: (object_pattern
    (shorthand_property_identifier_pattern) @destructured_var)
  value: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 5: const { VAR: myVar } = process.env (rename)
(variable_declarator
  name: (object_pattern
    (pair_pattern
      key: (property_identifier) @renamed_var
      value: (identifier)))
  value: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 6: const { VAR = "default" } = process.env (with default)
(variable_declarator
  name: (object_pattern
    (object_assignment_pattern
      left: (shorthand_property_identifier_pattern) @destructured_default))
  value: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  (#eq? @_process "process")
  (#eq? @_env "env"))

; =============================================================================
; Vite / import.meta.env Patterns
; =============================================================================

; Pattern 7: import.meta.env.VITE_VAR
(member_expression
  object: (member_expression
    object: (member_expression
      object: (identifier) @_import
      property: (property_identifier) @_meta)
    property: (property_identifier) @_env_meta)
  property: (property_identifier) @vite_env_var
  (#eq? @_import "import")
  (#eq? @_meta "meta")
  (#eq? @_env_meta "env"))

; Pattern 8: import.meta.env["VITE_VAR"]
(subscript_expression
  object: (member_expression
    object: (member_expression
      object: (identifier) @_import
      property: (property_identifier) @_meta)
    property: (property_identifier) @_env_meta)
  index: (string) @vite_env_bracket
  (#eq? @_import "import")
  (#eq? @_meta "meta")
  (#eq? @_env_meta "env"))

; =============================================================================
; dotenv Patterns
; =============================================================================

; Pattern 9: require("dotenv").config()
(call_expression
  function: (member_expression
    object: (call_expression
      function: (identifier) @_require
      arguments: (arguments (string) @dotenv_require))
    property: (property_identifier) @_config)
  (#eq? @_require "require")
  (#match? @dotenv_require "dotenv")
  (#eq? @_config "config"))

; Pattern 10: import "dotenv/config"
(import_statement
  source: (string) @dotenv_import
  (#match? @dotenv_import "dotenv"))

; =============================================================================
; Default Value Patterns
; =============================================================================

; Pattern 11: process.env.VAR || "default"
(binary_expression
  left: (member_expression
    object: (member_expression
      object: (identifier) @_process
      property: (property_identifier) @_env)
    property: (property_identifier) @env_with_or)
  operator: "||"
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 12: process.env.VAR ?? "default"
(binary_expression
  left: (member_expression
    object: (member_expression
      object: (identifier) @_process
      property: (property_identifier) @_env)
    property: (property_identifier) @env_with_nullish)
  operator: "??"
  (#eq? @_process "process")
  (#eq? @_env "env"))

; =============================================================================
; config/env library patterns
; =============================================================================

; Pattern 13: config.get("VAR")
(call_expression
  function: (member_expression
    object: (identifier) @_config_obj
    property: (property_identifier) @_get)
  arguments: (arguments (string) @config_get_var)
  (#eq? @_config_obj "config")
  (#eq? @_get "get"))

; Pattern 14: env.get("VAR") or env("VAR")
(call_expression
  function: (identifier) @_env_func
  arguments: (arguments (string) @env_func_var)
  (#match? @_env_func "^env$"))