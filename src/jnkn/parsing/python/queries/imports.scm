; Import Statement Detection for Python
; Captures all forms of Python imports

; =============================================================================
; Standard Import Patterns
; =============================================================================

; import module
(import_statement 
  name: (dotted_name) @import)

; import module as alias
(import_statement
  name: (aliased_import
    name: (dotted_name) @import
    alias: (identifier) @import_alias))

; =============================================================================
; From-Import Patterns
; =============================================================================

; from module import name
(import_from_statement 
  module_name: (dotted_name) @from_import)

; from . import name (relative import, current package)
(import_from_statement
  module_name: (relative_import
    (import_prefix) @relative_prefix) @relative_import)

; from .module import name (relative import with module)
(import_from_statement
  module_name: (relative_import
    (import_prefix) @relative_prefix
    (dotted_name) @relative_module) @relative_import)

; =============================================================================
; Import Names (what's being imported)
; =============================================================================

; The actual names being imported in from-import
(import_from_statement
  name: (dotted_name) @imported_name)

; Aliased imports in from-import
(import_from_statement
  name: (aliased_import
    name: (dotted_name) @imported_name
    alias: (identifier) @imported_alias))