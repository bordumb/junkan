# Jnkn LSP (Language Server Protocol)

**Real-time architectural feedback for your IDE.**

`jnkn-lsp` bridges the gap between your editor and the Jnkn dependency graph. It provides "squiggly line" diagnostics for broken cross-domain dependencies (e.g., orphaned environment variables) and rich hover information for connected infrastructure.

---

## Features

### 🔍 Diagnostics (The "Squigglies")
Get immediate feedback when you reference a dependency that doesn't exist in your infrastructure.

* **Orphan Detection:** Highlights `os.getenv("VAR")` calls if "VAR" is not provided by any Terraform output or configuration source in the graph.

### 🖱️ Hover Support
Hover over an environment variable or configuration key to see exactly where it comes from.

* **Infrastructure Context:** Shows the Terraform resource type and address that provisions the variable.
* **Deep Links:** Click "View in Graph" to open the visualization for that specific node.

---

## Installation

This package is typically installed as part of the `jnkn` developer toolchain, but can be installed independently for editor integration.

```bash
pip install jnkn-lsp
````

## Editor Configuration

### VS Code

Use a generic LSP client extension or the [Generic LSP Client](https://www.google.com/search?q=https://marketplace.visualstudio.com/items%3FitemName%3Dsnooz82.vscode-generic-lsp-client) and configure it to run `jnkn-lsp`.

**settings.json:**

```json
{
    "generic-lsp.server-definitions": {
        "jnkn-lsp": {
            "command": ["jnkn-lsp"],
            "languageIds": ["python"],
            "rootPath": "${workspaceFolder}"
        }
    }
}
```

### Neovim (using lspconfig)

Add the following to your `init.lua`:

```lua
local configs = require 'lspconfig.configs'

if not configs.jnkn_lsp then
  configs.jnkn_lsp = {
    default_config = {
      cmd = { 'jnkn-lsp' },
      filetypes = { 'python' },
      root_dir = require('lspconfig.util').root_pattern('.jnkn', '.git'),
      settings = {},
    },
  }
end

require('lspconfig').jnkn_lsp.setup{}
```

## Architecture

The LSP server is stateless and read-only. It relies on the local SQLite database (`.jnkn/jnkn.db`) maintained by the `jnkn watch` daemon or manual `jnkn scan` commands.

  * **Server:** Built with `pygls`.
  * **State:** Reads from `jnkn.core.storage.SQLiteStorage`.
  * **Protocol:** Implements `textDocument/didSave`, `textDocument/didOpen`, and `textDocument/hover`.

## Developing

To install from source while developing:
```bash
uv pip install -e packages/jnkn-lsp
```

And you will want to point your settings to your virtual environment running the latest code on your machine, e.g.: 
```json
{
    "generic-lsp.server-definitions": {
        "jnkn-lsp": {
            "command": ["/Users/bordumb/workspace/repositories/junkan/.venv/bin/jnkn-lsp"],
            "languageIds": ["python"],
            "rootPath": "${workspaceFolder}"
        }
    }
}
```

> Note: you will want to use `/Users/{YOUR_USER_NAME}/path/to/jnkn/.venv/bin/jnkn-lsp`. You can confirm the correct path on your device using `pwd -P | xargs -I {} echo {}/.venv/bin/jnkn-lsp`
