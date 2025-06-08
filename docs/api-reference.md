# API Reference

This reference covers all available tools, endpoints, and transport mechanisms provided by Aider MCP Server.

## MCP Tools

### aider_ai_code

The primary tool for AI-assisted code generation and modification.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ai_coding_prompt` | string | ✅ | Description of the coding task to perform |
| `relative_editable_files` | array[string] | ✅ | Files that can be modified |
| `relative_readonly_files` | array[string] | ❌ | Files for context (read-only) |
| `architect_mode` | boolean | ❌ | Enable two-phase generation (architect + editor) |
| `editor_model` | string | ❌ | Secondary model for architect mode |
| `model` | string | ❌ | Override default AI model |

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Add comprehensive error handling to the user authentication system",
      "relative_editable_files": [
        "src/auth/login.py",
        "src/auth/session.py"
      ],
      "relative_readonly_files": [
        "src/auth/models.py",
        "tests/test_auth.py"
      ],
      "architect_mode": true,
      "editor_model": "gpt-4o-mini"
    }
  }
}
```

#### Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text", 
        "text": "## Summary\n\nAdded comprehensive error handling to the authentication system:\n\n### Changes Made\n\n- **login.py**: Added try-catch blocks for database exceptions\n- **session.py**: Implemented session validation with proper error codes\n\n### Files Modified\n\n- `src/auth/login.py`: 45 lines added\n- `src/auth/session.py`: 23 lines added\n\n### Testing\n\nAll existing tests pass. Consider adding tests for the new error scenarios."
      }
    ],
    "isError": false
  }
}
```

### aider_ai_ask

Query tool for code explanation and questions without making changes.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ai_coding_prompt` | string | ✅ | Question about the codebase |
| `relative_readonly_files` | array[string] | ❌ | Files to analyze |
| `model` | string | ❌ | Override default AI model |

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_ask",
    "arguments": {
      "ai_coding_prompt": "Explain how the authentication flow works in this application",
      "relative_readonly_files": [
        "src/auth/login.py",
        "src/auth/session.py",
        "src/auth/models.py"
      ]
    }
  }
}
```

### aider_list_models

List available AI models matching a given substring.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `substring` | string | ❌ | Filter models by substring |

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "aider_list_models",
    "arguments": {
      "substring": "gpt-4"
    }
  }
}
```

#### Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Available models matching 'gpt-4':\n\n- gpt-4o\n- gpt-4o-mini\n- gpt-4-turbo\n- gpt-4"
      }
    ],
    "isError": false
  }
}
```

## Transport Mechanisms

### stdio Transport

Standard input/output communication for MCP clients.

#### Usage
```bash
mcp-aider-stdio --current-working-dir /path/to/project
```

#### Characteristics
- **Protocol:** MCP over stdio
- **Bidirectional:** Yes
- **Real-time events:** No
- **Use case:** Command-line tools, IDE plugins

### SSE Transport

Server-Sent Events over HTTP for web applications.

#### Base URL
```
http://localhost:5005
```

#### Endpoints

##### POST /mcp
Execute MCP tool calls.

**Request:**
```bash
curl -X POST http://localhost:5005/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}'
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [...],
    "isError": false
  }
}
```

##### GET /sse
Real-time event stream.

**Usage:**
```bash
curl -N http://localhost:5005/sse
```

**Event Types:**
- `STATUS` - General status updates
- `PROGRESS` - Operation progress (0-100%)  
- `TOOL_RESULT` - Final tool results
- `HEARTBEAT` - Connection keepalive

**Event Format:**
```
data: {"event_type": "PROGRESS", "data": {"progress": 45, "message": "Processing files..."}}

data: {"event_type": "TOOL_RESULT", "data": {"result": {...}, "request_id": "req_123"}}
```

##### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

##### GET /
Basic server information.

**Response:**
```json
{
  "name": "aider-mcp-server",
  "version": "1.0.0",
  "transport": "sse",
  "capabilities": ["tools/call", "events"]
}
```

### Multi-Transport Mode

Runs both stdio and SSE simultaneously.

```bash
mcp-aider-multi --current-working-dir /path/to/project --port 5005
```

## Event System

### Event Types

#### STATUS
General status information.

```json
{
  "event_type": "STATUS",
  "data": {
    "message": "Processing request req_123",
    "level": "info",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

#### PROGRESS  
Task progress updates (0-100%).

```json
{
  "event_type": "PROGRESS", 
  "data": {
    "progress": 75,
    "message": "Analyzing code structure...",
    "request_id": "req_123"
  }
}
```

#### TOOL_RESULT
Final results from tool execution.

```json
{
  "event_type": "TOOL_RESULT",
  "data": {
    "result": {
      "content": [...],
      "isError": false
    },
    "request_id": "req_123",
    "execution_time": 2.5
  }
}
```

#### HEARTBEAT
Connection keepalive (sent every 30 seconds).

```json
{
  "event_type": "HEARTBEAT",
  "data": {
    "timestamp": "2024-01-15T10:30:00Z",
    "uptime": 3600
  }
}
```

## Error Handling

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "details": "The method 'invalid_tool' is not supported",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  }
}
```

### Common Error Codes

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Invalid JSON-RPC |
| -32601 | Method not found | Unknown method |
| -32602 | Invalid params | Invalid parameters |
| -32603 | Internal error | Server error |
| -32000 | Tool error | Tool execution failed |

### Rate Limiting

When rate limits are encountered:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Rate limit encountered. Attempting fallback to gpt-4o-mini..."
      }
    ],
    "isError": false,
    "fallback_used": true,
    "original_model": "gpt-4o",
    "fallback_model": "gpt-4o-mini"
  }
}
```

## Authentication & Security

### Working Directory Validation

The server validates that the working directory:
- Exists and is accessible
- Contains a valid Git repository
- Has appropriate permissions

### Request Validation

All requests are validated for:
- Valid JSON-RPC format
- Required parameters
- File path security (no directory traversal)
- Model availability

### API Key Management

API keys are checked in order:
1. OpenAI (`OPENAI_API_KEY`)
2. Anthropic (`ANTHROPIC_API_KEY`) 
3. Google (`GOOGLE_API_KEY`)
4. Other configured providers

## Rate Limits & Fallbacks

### Automatic Fallback

When primary models hit rate limits:

1. **Detection:** Rate limit error detected
2. **Fallback:** Switch to backup model automatically
3. **Notification:** User informed via response
4. **Retry:** Original request executed with fallback model

### Fallback Chain

```
gpt-4o → gpt-4o-mini → gpt-3.5-turbo
claude-3-opus → claude-3-sonnet → claude-3-haiku
gemini-pro → gemini-pro-vision
```

## Client Libraries

### Python

```python
import json
import subprocess

# stdio mode
process = subprocess.Popen([
    'mcp-aider-stdio',
    '--current-working-dir', '/path/to/project'
], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "aider_ai_code",
        "arguments": {
            "ai_coding_prompt": "Add logging to this function",
            "relative_editable_files": ["app.py"]
        }
    }
}

process.stdin.write(json.dumps(request) + '\n')
process.stdin.flush()

response = process.stdout.readline()
result = json.loads(response)
```

### JavaScript

```javascript
// SSE mode
const response = await fetch('http://localhost:5005/mcp', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: 'aider_ai_code',
      arguments: {
        ai_coding_prompt: 'Add error handling to this API endpoint',
        relative_editable_files: ['api/routes.js']
      }
    }
  })
});

const result = await response.json();

// Listen for real-time events
const eventSource = new EventSource('http://localhost:5005/sse');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.event_type === 'PROGRESS') {
    console.log(`Progress: ${data.data.progress}%`);
  }
};
```

## Performance & Monitoring

### Metrics Available

- Request count and success rate
- Average response time
- Active connection count
- Model usage statistics
- Error rate by type

### Health Monitoring

Regular health checks verify:
- API connectivity
- Model availability  
- File system access
- Memory usage
- Active connections

### Logging

Structured logs include:
- Request/response details
- Performance metrics
- Error traces
- Security events

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`