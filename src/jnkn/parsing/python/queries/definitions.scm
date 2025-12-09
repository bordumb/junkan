; Definition Detection for Python
; Captures function and class definitions

; =============================================================================
; Function Definitions
; =============================================================================

; Regular function definition
(function_definition
  name: (identifier) @function_def)

; Async function definition
(function_definition
  name: (identifier) @async_function_def
  (#match? @async_function_def ".*"))

; Decorated function definition
(decorated_definition
  definition: (function_definition
    name: (identifier) @decorated_function_def))

; =============================================================================
; Class Definitions
; =============================================================================

; Regular class definition
(class_definition
  name: (identifier) @class_def)

; Decorated class definition
(decorated_definition
  definition: (class_definition
    name: (identifier) @decorated_class_def))

; =============================================================================
; Method Definitions (inside classes)
; =============================================================================

; Method definition (function inside class)
(class_definition
  body: (block
    (function_definition
      name: (identifier) @method_def)))

; Decorated method definition
(class_definition
  body: (block
    (decorated_definition
      definition: (function_definition
        name: (identifier) @decorated_method_def))))

; =============================================================================
; Variable Definitions (module-level constants)
; =============================================================================

; Simple assignment at module level
(module
  (expression_statement
    (assignment
      left: (identifier) @variable_def)))

; Type-annotated assignment at module level
(module
  (expression_statement
    (assignment
      left: (identifier) @typed_variable_def
      type: (type) @variable_type)))

; =============================================================================
; Decorators (for context)
; =============================================================================

; Capture decorators for additional context
(decorator
  (identifier) @decorator_name)

(decorator
  (call
    function: (identifier) @decorator_call))

(decorator
  (call
    function: (attribute
      object: (identifier) @decorator_module
      attribute: (identifier) @decorator_attr)))