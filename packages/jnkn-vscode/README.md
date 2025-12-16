# jnkn-vscode

VS Code extension for **jnkn** - the Pre-Flight Impact Analysis Engine that catches breaking changes between Infrastructure (Terraform), Code (Python/JS), and Data (dbt) before they hit production.

## Features

- **Real-time Diagnostics**: Red squiggly lines under environment variables that have no infrastructure provider
- **Hover Information**: See which Terraform output or K8s secret provides each variable
- **Automatic Scanning**: Watches for file changes and re-analyzes dependencies
- **Zero Configuration**: Works out of the box with any project containing Terraform, Python, or K8s files

![Demo](./docs/demo.gif)

## How It Works

This extension is a thin client that communicates with the **jnkn LSP server** (Language Server Protocol). The architecture:

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   VS Code       │  LSP    │   jnkn-lsp      │  SQL    │   .jnkn/        │
│   Extension     │ ◄─────► │   (Python)      │ ◄─────► │   jnkn.db       │
│   (extension.js)│  JSON   │                 │         │   (SQLite)      │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                    │
                                    │ subprocess
                                    ▼
                            ┌─────────────────┐
                            │   jnkn-core     │
                            │   (CLI + Parser)│
                            └─────────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| `extension.js` | VS Code extension entry point. Starts the LSP client and handles activation. |
| `jnkn-lsp` | Python Language Server that provides diagnostics, hover, and other LSP features. |
| `jnkn-core` | Core library with parsers for Python, Terraform, K8s, and the dependency stitching engine. |
| `.jnkn/jnkn.db` | SQLite database storing the dependency graph for the workspace. |

## Installation

### From VS Code Marketplace (Coming Soon)

Search for "jnkn" in the Extensions sidebar.

### From VSIX (Local Development)

```bash
cd packages/jnkn-vscode
npm install
npm run package
code --install-extension jnkn-*.vsix
```

## Requirements

- **Python 3.10+** with `jnkn` and `jnkn-lsp` packages installed
- A virtual environment in your project (`.venv/`) with the packages installed

```bash
# In your project directory
python -m venv .venv
.venv/bin/pip install jnkn jnkn-lsp
```

## Extension Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `jnkn.pythonPath` | Path to Python interpreter with jnkn installed | `${workspaceFolder}/.venv/bin/python` |
| `jnkn.serverPath` | Path to LSP server script (for development) | `null` (uses installed package) |
| `jnkn.logLevel` | Logging verbosity: `error`, `warn`, `info`, `debug` | `info` |

### Example `.vscode/settings.json`

```json
{
  "jnkn.pythonPath": "${workspaceFolder}/.venv/bin/python",
  "jnkn.logLevel": "debug"
}
```

---

## Architecture Deep Dive

### `extension.js`

The extension entry point handles:

1. **Activation**: Triggered when VS Code opens a workspace with Python, Terraform, or YAML files
2. **LSP Client Setup**: Spawns the Python LSP server as a subprocess
3. **Configuration**: Reads settings and passes them to the server
4. **Lifecycle Management**: Handles server crashes, restarts, and cleanup

#### Key Functions

```javascript
// Called when extension activates
async function activate(context) {
    // 1. Find Python interpreter
    const pythonPath = getPythonPath();
    
    // 2. Create LSP client
    const serverOptions = {
        command: pythonPath,
        args: ['-m', 'jnkn_lsp'],  // or path to server.py
    };
    
    // 3. Configure client capabilities
    const clientOptions = {
        documentSelector: [
            { scheme: 'file', language: 'python' },
            { scheme: 'file', language: 'terraform' },
            { scheme: 'file', language: 'yaml' },
        ],
    };
    
    // 4. Start the client
    client = new LanguageClient('jnkn', 'Jnkn', serverOptions, clientOptions);
    client.start();
}
```

### LSP Communication

The extension communicates with `jnkn-lsp` using the [Language Server Protocol](https://microsoft.github.io/language-server-protocol/):

| LSP Method | Purpose |
|------------|---------|
| `initialize` | Exchange capabilities, set workspace root |
| `textDocument/didOpen` | Trigger diagnostics for opened file |
| `textDocument/didSave` | Re-analyze after save |
| `textDocument/hover` | Show provider info on hover |
| `textDocument/publishDiagnostics` | Server → Client: Send error/warning markers |

### Workspace Initialization Flow

```
1. User opens folder in VS Code
2. Extension activates (extension.js)
3. LSP client spawns jnkn-lsp server
4. Server runs `jnkn init` if .jnkn/ doesn't exist
5. Server runs `jnkn scan` to build dependency graph
6. Server starts file watcher for incremental updates
7. User opens app.py
8. Server queries SQLite for orphaned env vars
9. Server publishes diagnostics (red squiggles)
```

---

## Development

### Prerequisites

- Node.js 18+
- Python 3.10+
- VS Code 1.80+

### Setup

```bash
# Clone the monorepo
git clone https://github.com/your-org/junkan.git
cd junkan

# Install jnkn-core and jnkn-lsp in development mode
cd packages/jnkn-core
pip install -e .

cd ../jnkn-lsp
pip install -e .

# Install VS Code extension dependencies
cd ../jnkn-vscode
npm install
```

### Running in Development Mode

1. **Open the extension folder in VS Code**:
   ```bash
   cd packages/jnkn-vscode
   code .
   ```

2. **Navigate to `extension.js`** in the Explorer sidebar

3. **Press `F5`** to launch the Extension Development Host
   - This opens a new VS Code window with your extension loaded
   - The original window shows debug output in the Debug Console

4. **Open the demo project** in the new window:
   ```bash
   # First, create the demo if you haven't
   jnkn demo ~/jnkn-test-run
   
   # Then in the Extension Development Host:
   # File → Open Folder → ~/jnkn-test-run/jnkn-demo
   ```

5. **Watch the magic happen**:
   - Open `src/app.py`
   - See red squiggles on orphaned environment variables
   - Hover to see diagnostic details

### Debugging Tips

#### View LSP Logs

In the Extension Development Host window:
- Open Output panel (`View → Output`)
- Select "Jnkn" from the dropdown

#### View Server-Side Logs

The LSP server logs to stderr. In the original VS Code window:
- Check the Debug Console for Python server output
- Or add `"jnkn.logLevel": "debug"` to settings

#### Common Issues

| Issue | Solution |
|-------|----------|
| "Cannot find Python" | Ensure `.venv/` exists with jnkn installed |
| No diagnostics appearing | Check Output panel for errors; verify `.jnkn/jnkn.db` exists |
| Stale diagnostics | Save the file to trigger re-analysis |
| Server crash on startup | Check Python version (needs 3.10+) |

### Testing

```bash
# Run extension tests
npm test

# Run with coverage
npm run test:coverage
```

### Packaging

```bash
# Create .vsix package
npm run package

# This creates: jnkn-<version>.vsix
```

### Publishing (Maintainers)

```bash
# Login to VS Code Marketplace
vsce login <publisher>

# Publish
vsce publish
```

---

## Project Structure

```
packages/jnkn-vscode/
├── extension.js          # Main extension entry point
├── package.json          # Extension manifest (activation events, commands, settings)
├── package-lock.json
├── README.md             # This file
├── CHANGELOG.md          # Version history
├── LICENSE
├── .vscodeignore         # Files to exclude from package
├── docs/
│   └── demo.gif          # Demo animation
├── test/
│   └── extension.test.js # Extension tests
└── node_modules/
```

### `package.json` Key Sections

```json
{
  "activationEvents": [
    "onLanguage:python",
    "onLanguage:terraform", 
    "onLanguage:yaml",
    "workspaceContains:**/*.tf",
    "workspaceContains:**/*.py"
  ],
  "contributes": {
    "configuration": {
      "title": "Jnkn",
      "properties": {
        "jnkn.pythonPath": { ... },
        "jnkn.serverPath": { ... },
        "jnkn.logLevel": { ... }
      }
    }
  }
}
```

---

## Troubleshooting

### Extension Not Activating

1. Check that the workspace contains `.py`, `.tf`, or `.yaml` files
2. Look for errors in `Help → Toggle Developer Tools → Console`

### "Python not found" Error

1. Ensure a virtual environment exists:
   ```bash
   python -m venv .venv
   .venv/bin/pip install jnkn jnkn-lsp
   ```
2. Or set a custom path in settings:
   ```json
   { "jnkn.pythonPath": "/path/to/python" }
   ```

### No Diagnostics Appearing

1. **Check if jnkn scanned the project**:
   ```bash
   ls -la .jnkn/  # Should contain jnkn.db
   ```

2. **Run scan manually**:
   ```bash
   .venv/bin/jnkn scan
   ```

3. **Check for provides edges**:
   ```bash
   sqlite3 .jnkn/jnkn.db "SELECT * FROM edges WHERE type='provides';"
   ```

### Diagnostics Are Wrong

1. **Re-scan after Terraform changes**:
   ```bash
   rm -rf .jnkn/
   .venv/bin/jnkn scan
   ```

2. **Reload VS Code window**: `Cmd+Shift+P` → "Developer: Reload Window"

---

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) in the monorepo root.

## License

MIT - See [LICENSE](./LICENSE)