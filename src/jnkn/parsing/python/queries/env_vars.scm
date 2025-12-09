; click_typer_envvar.scm
; @click.option(..., envvar="VAR")
(decorated_definition
  (decorator
    (call
      function: (attribute
        object: (identifier) @_mod
        attribute: (identifier) @_func)
      arguments: (argument_list
        (keyword_argument
          name: (identifier) @_kwarg
          value: [(string) @click_envvar
                  (list (string) @click_envvar_list)]))))
  (#eq? @_mod "click")
  (#eq? @_func "option")
  (#eq? @_kwarg "envvar"))

; dotenv_subscript.scm
; config["VAR"] where config = dotenv_values()
(subscript
  value: (identifier) @_config_var
  subscript: (string) @dotenv_key)

; django_environ.scm
; env.str("VAR"), env.bool("VAR"), env("VAR")
(call
  function: [(attribute
               object: (identifier) @_env_var
               attribute: (identifier) @_method)
             (identifier) @_env_call]
  arguments: (argument_list (string) @django_env_var)
  (#match? @_env_var "^env$")
  (#match? @_method "^(str|int|bool|float|list|dict|url|db|cache|search_url|email_url)$"))

; airflow_variable.scm
(call
  function: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @airflow_var)
  (#eq? @_obj "Variable")
  (#eq? @_method "get"))

; f_string_env.scm
(interpolation
  (call
    function: (attribute
      object: (identifier) @_obj
      attribute: (identifier) @_method)
    arguments: (argument_list (string) @fstring_env))
  (#eq? @_obj "os")
  (#eq? @_method "getenv"))