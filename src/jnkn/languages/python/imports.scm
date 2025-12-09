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
