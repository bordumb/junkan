import * as path from 'path';
import { workspace, ExtensionContext, window, commands } from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;
let outputChannel = window.createOutputChannel("Jnkn LSP");

export async function activate(context: ExtensionContext) {
  outputChannel.appendLine("========================================");
  outputChannel.appendLine("🚀 Jnkn Extension Activating...");
  outputChannel.appendLine(`Timestamp: ${new Date().toISOString()}`);
  outputChannel.appendLine("========================================");
  
  // Show the output channel immediately for debugging
  outputChannel.show(true);
  
  // Also show an info message
  window.showInformationMessage("👋 Jnkn Extension is starting!");

  // Register commands
  context.subscriptions.push(
    commands.registerCommand('jnkn-vscode.restart', restartServer),
    commands.registerCommand('jnkn-vscode.showOutput', () => outputChannel.show(true))
  );

  // Start the language server
  await startServer(context);
}

async function startServer(context: ExtensionContext) {
  // Get configuration
  const config = workspace.getConfiguration('jnkn');
  const pythonPath = config.get<string>('pythonPath') || 'python3';
  const serverPath = config.get<string>('serverPath') || '';
  
  outputChannel.appendLine(`\n📋 Configuration:`);
  outputChannel.appendLine(`   Python Path: ${pythonPath}`);
  outputChannel.appendLine(`   Server Path: ${serverPath || '(using installed package)'}`);
  outputChannel.appendLine(`   Workspace: ${workspace.workspaceFolders?.[0]?.uri.fsPath || 'No workspace'}`);

  // Determine server module/script
  let serverModule: string;
  let serverArgs: string[];

  if (serverPath) {
    // Use explicit path to server.py
    serverModule = pythonPath;
    serverArgs = [serverPath];
    outputChannel.appendLine(`\n🔧 Using explicit server path: ${serverPath}`);
  } else {
    // Use installed package (python -m jnkn_lsp)
    serverModule = pythonPath;
    serverArgs = ['-m', 'jnkn_lsp.server'];
    outputChannel.appendLine(`\n🔧 Using installed package: python -m jnkn_lsp`);
  }

  // Verify Python is accessible
  try {
    const { exec } = require('child_process');
    const version = await new Promise<string>((resolve, reject) => {
      exec(`${pythonPath} --version`, (err: Error | null, stdout: string, stderr: string) => {
        if (err) {reject(err);}
        resolve(stdout || stderr);
      });
    });
    outputChannel.appendLine(`✅ Python version: ${version.trim()}`);
  } catch (err) {
    outputChannel.appendLine(`❌ Failed to find Python at: ${pythonPath}`);
    outputChannel.appendLine(`   Error: ${err}`);
    window.showErrorMessage(`Jnkn: Cannot find Python at "${pythonPath}". Please check jnkn.pythonPath setting.`);
    return;
  }

  // Server options
  const serverOptions: ServerOptions = {
    command: serverModule,
    args: serverArgs,
    options: {
      cwd: workspace.workspaceFolders?.[0]?.uri.fsPath,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',  // Ensure Python output isn't buffered
      }
    }
  };

  // Client options
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: 'file', language: 'python' },
      { scheme: 'file', language: 'typescript' },
      { scheme: 'file', language: 'javascript' },
      { scheme: 'file', language: 'terraform' },
      { scheme: 'file', language: 'yaml' },
    ],
    outputChannel: outputChannel,
    traceOutputChannel: outputChannel,
    revealOutputChannelOn: 1,  // RevealOutputChannelOn.Error
  };

  outputChannel.appendLine(`\n🔌 Starting Language Server...`);
  outputChannel.appendLine(`   Command: ${serverModule} ${serverArgs.join(' ')}`);

  // Create the language client
  client = new LanguageClient(
    'jnkn-lsp',
    'Jnkn Language Server',
    serverOptions,
    clientOptions
  );

  // Handle client state changes
  client.onDidChangeState((event) => {
    outputChannel.appendLine(`📡 Client state: ${stateToString(event.oldState)} → ${stateToString(event.newState)}`);
  });

  // Start the client
  try {
    await client.start();
    outputChannel.appendLine(`✅ Language Server started successfully!`);
    window.showInformationMessage("Jnkn LSP Server started!");
  } catch (err) {
    outputChannel.appendLine(`❌ Failed to start Language Server:`);
    outputChannel.appendLine(`   ${err}`);
    window.showErrorMessage(`Jnkn: Failed to start LSP server. Check Output panel for details.`);
  }
}

async function restartServer() {
  outputChannel.appendLine(`\n🔄 Restarting Language Server...`);
  
  if (client) {
    await client.stop();
    client = undefined;
  }
  
  // Re-read context from the activation
  // For simplicity, we'll just call startServer with a mock context
  // In production, you'd store the context reference
  window.showInformationMessage("Jnkn: Restarting LSP server...");
}

function stateToString(state: number): string {
  switch (state) {
    case 1: return 'Stopped';
    case 2: return 'Starting';
    case 3: return 'Running';
    default: return `Unknown(${state})`;
  }
}

export function deactivate(): Thenable<void> | undefined {
  outputChannel.appendLine(`\n👋 Jnkn Extension Deactivating...`);
  if (!client) {
    return undefined;
  }
  return client.stop();
}