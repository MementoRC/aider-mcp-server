# Getting Started

Welcome to Aider MCP Server! This guide will help you get up and running quickly with this AI-powered coding server that integrates Aider with the Model Context Protocol (MCP).

## What is Aider MCP Server?

Aider MCP Server is a modular, AI-powered coding server built with **Atomic Design** principles. It provides:

- 🤖 **AI-Assisted Coding** via Aider integration
- 🔄 **Multiple Transport Protocols** (stdio, SSE, HTTP)
- 🏗️ **Atomic Design Architecture** for maintainability
- ⚡ **Real-time Progress Updates** and event streaming
- 🔒 **Security Controls** and validation
- 📈 **Comprehensive Monitoring** and health checks

## Installation

### Prerequisites

- **Python 3.12** or higher
- **Git** (for repository operations)
- **AI API Keys** (OpenAI, Anthropic, Google, etc.)

### Quick Install

=== "pip"

    ```bash
    pip install aider-mcp-server
    ```

=== "uv"

    ```bash
    uv add aider-mcp-server
    ```

=== "Development Install"

    ```bash
    git clone https://github.com/MementoRC/aider-mcp-server.git
    cd aider-mcp-server
    pip install -e ".[dev]"
    pre-commit install
    ```

### Verify Installation

```bash
# Check installation
python -m aider_mcp_server --help

# Test with stdio mode
mcp-aider-stdio --current-working-dir /path/to/your/project
```

## Configuration

### Environment Variables

Create a `.env` file or set these environment variables:

```bash
# API Keys (choose your preferred provider)
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_API_KEY=your_google_key_here

# Optional: Model Configuration
AIDER_MODEL=gpt-4o
AIDER_EDITOR_MODEL=gpt-4o-mini

# Optional: Server Configuration
AIDER_WORKING_DIR=/path/to/your/project
AIDER_HOST=localhost
AIDER_PORT=5005
```

### API Key Priority

The server attempts to use API keys in this order:

1. **OpenAI** (`OPENAI_API_KEY`)
2. **Anthropic** (`ANTHROPIC_API_KEY`) 
3. **Google/Gemini** (`GOOGLE_API_KEY`)
4. **Other providers** as configured

## Quick Start Examples

### 1. stdio Mode (Command Line)

Perfect for command-line tools and MCP clients:

```bash
mcp-aider-stdio --current-working-dir /path/to/your/project
```

**Use cases:**
- Claude Desktop integration
- Command-line MCP clients
- Shell scripting automation

### 2. SSE Mode (Web Applications)

Ideal for web-based interfaces with real-time updates:

```bash
mcp-aider-sse \
  --current-working-dir /path/to/your/project \
  --host localhost \
  --port 5005
```

**Use cases:**
- Web applications
- Real-time dashboards
- Browser-based development tools

### 3. Multi-Transport Mode

Runs both stdio and SSE simultaneously:

```bash
mcp-aider-multi \
  --current-working-dir /path/to/your/project \
  --host localhost \
  --port 5005
```

**Use cases:**
- Development environments
- Multi-client scenarios
- Testing and debugging

## Your First AI Coding Request

### Using stdio Mode

1. **Start the server:**
   ```bash
   mcp-aider-stdio --current-working-dir /path/to/your/project
   ```

2. **Send an MCP request:**
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tools/call",
     "params": {
       "name": "aider_ai_code",
       "arguments": {
         "ai_coding_prompt": "Create a simple Python function that calculates fibonacci numbers",
         "relative_editable_files": ["fibonacci.py"]
       }
     }
   }
   ```

### Using SSE Mode with curl

1. **Start the server:**
   ```bash
   mcp-aider-sse --current-working-dir /path/to/your/project
   ```

2. **Send a request:**
   ```bash
   curl -X POST http://localhost:5005/mcp \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools/call",
       "params": {
         "name": "aider_ai_code",
         "arguments": {
           "ai_coding_prompt": "Add error handling to the fibonacci function",
           "relative_editable_files": ["fibonacci.py"]
         }
       }
     }'
   ```

3. **Monitor progress (optional):**
   ```bash
   curl -N http://localhost:5005/sse
   ```

## Transport Mechanisms

### stdio Transport

- **Protocol:** Standard input/output streams
- **Use case:** Command-line integration, MCP clients
- **Pros:** Simple, widely supported, low overhead
- **Cons:** No real-time progress updates

### SSE Transport  

- **Protocol:** Server-Sent Events over HTTP
- **Use case:** Web applications, real-time dashboards
- **Pros:** Real-time updates, web-compatible, bi-directional
- **Cons:** HTTP overhead, requires port management

### HTTP Transport

- **Protocol:** RESTful HTTP API
- **Use case:** Traditional web APIs, batch processing
- **Pros:** Standard HTTP, caching support, simple integration
- **Cons:** Request-response only, no streaming

## Common Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--current-working-dir` | Git repository path | Current directory |
| `--host` | SSE/Multi server host | `localhost` |
| `--port` | SSE/Multi server port | `5005` |
| `--log-level` | Logging verbosity | `INFO` |
| `--model` | AI model to use | From environment |

## Troubleshooting

### Common Issues

!!! warning "Repository Required"
    The server requires a valid Git repository as the working directory. Initialize one with:
    ```bash
    git init /path/to/your/project
    ```

!!! error "API Key Not Found"
    Set at least one AI provider API key:
    ```bash
    export OPENAI_API_KEY=your_key_here
    # or
    export ANTHROPIC_API_KEY=your_key_here
    ```

!!! info "Port Already in Use"
    If port 5005 is busy, use a different port:
    ```bash
    mcp-aider-sse --port 5006
    ```

### Log Files

Logs are stored in `~/.aider-mcp-server/logs/` by default:

```bash
# View recent logs
tail -f ~/.aider-mcp-server/logs/aider-mcp-server.log

# Check error logs
grep ERROR ~/.aider-mcp-server/logs/aider-mcp-server.log
```

### Health Checks

#### SSE Mode
```bash
curl http://localhost:5005/health
```

#### Multi Mode
```bash
curl http://localhost:5005/health
curl http://localhost:5005/sse-health
```

## Next Steps

Now that you have Aider MCP Server running:

1. **[Explore the API Reference](api-reference.md)** - Learn about available tools and endpoints
2. **[Check out Examples](examples.md)** - See practical usage scenarios  
3. **[Understand the Architecture](atomic-design-architecture.md)** - Dive into the atomic design structure
4. **[Contributing](contributing.md)** - Help improve the project

## Need Help?

- **Documentation:** [Full documentation site](index.md)
- **Issues:** [GitHub Issues](https://github.com/MementoRC/aider-mcp-server/issues)
- **Discussions:** [GitHub Discussions](https://github.com/MementoRC/aider-mcp-server/discussions)