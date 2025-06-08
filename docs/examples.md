# Examples

This page provides practical examples of using Aider MCP Server in various scenarios.

## Basic Examples

### Simple Code Generation

Generate a new function with comprehensive documentation and tests.

=== "stdio"

    ```bash
    # Start server
    mcp-aider-stdio --current-working-dir /path/to/project
    ```

    ```json
    {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "aider_ai_code",
        "arguments": {
          "ai_coding_prompt": "Create a utility function to calculate the factorial of a number. Include docstrings, type hints, and handle edge cases.",
          "relative_editable_files": ["utils/math.py"]
        }
      }
    }
    ```

=== "SSE/HTTP"

    ```bash
    # Start server
    mcp-aider-sse --current-working-dir /path/to/project --port 5005
    ```

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
            "ai_coding_prompt": "Create a utility function to calculate the factorial of a number. Include docstrings, type hints, and handle edge cases.",
            "relative_editable_files": ["utils/math.py"]
          }
        }
      }'
    ```

### Code Refactoring

Refactor existing code to improve performance and maintainability.

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Refactor this database connection code to use connection pooling and add proper error handling",
      "relative_editable_files": [
        "src/database/connection.py",
        "src/database/pool.py"
      ],
      "relative_readonly_files": [
        "src/database/models.py",
        "config/database.yaml"
      ]
    }
  }
}
```

### Adding Tests

Generate comprehensive test coverage for existing code.

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Create comprehensive unit tests for the user authentication module. Include tests for success cases, error handling, and edge cases.",
      "relative_editable_files": [
        "tests/test_auth.py"
      ],
      "relative_readonly_files": [
        "src/auth/login.py",
        "src/auth/session.py",
        "src/auth/models.py"
      ]
    }
  }
}
```

## Advanced Examples

### Architect Mode

Use two-phase generation for complex features.

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Implement a caching system with Redis backend, including cache invalidation, TTL support, and monitoring metrics",
      "relative_editable_files": [
        "src/cache/redis_cache.py",
        "src/cache/cache_manager.py",
        "src/cache/metrics.py"
      ],
      "relative_readonly_files": [
        "src/config/settings.py",
        "requirements.txt"
      ],
      "architect_mode": true,
      "editor_model": "gpt-4o-mini"
    }
  }
}
```

### Multi-File Feature Implementation

Implement a complete feature across multiple files.

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Implement a complete user notification system with email and SMS support, including templates, queuing, and delivery tracking",
      "relative_editable_files": [
        "src/notifications/email.py",
        "src/notifications/sms.py",
        "src/notifications/queue.py",
        "src/notifications/templates.py",
        "src/notifications/tracking.py",
        "src/api/notifications.py"
      ],
      "relative_readonly_files": [
        "src/models/user.py",
        "src/config/settings.py",
        "templates/email/",
        "requirements.txt"
      ]
    }
  }
}
```

## Integration Examples

### Web Application Integration

#### FastAPI Integration

```python
from fastapi import FastAPI, BackgroundTasks
import httpx
import json

app = FastAPI()

async def call_aider_mcp(prompt: str, files: list[str]):
    """Call Aider MCP Server via HTTP"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:5005/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "aider_ai_code",
                    "arguments": {
                        "ai_coding_prompt": prompt,
                        "relative_editable_files": files
                    }
                }
            }
        )
        return response.json()

@app.post("/generate-code")
async def generate_code(
    prompt: str,
    files: list[str],
    background_tasks: BackgroundTasks
):
    """Generate code using Aider MCP Server"""
    result = await call_aider_mcp(prompt, files)
    return {"status": "success", "result": result}

@app.get("/sse-events")
async def sse_events():
    """Proxy SSE events from Aider MCP Server"""
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", "http://localhost:5005/sse") as response:
            async for chunk in response.aiter_text():
                yield f"data: {chunk}\n\n"
```

#### React Frontend

```javascript
import React, { useState, useEffect } from 'react';

function AiderCodeGenerator() {
  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState(['']);
  const [result, setResult] = useState(null);
  const [progress, setProgress] = useState(0);

  // Listen for real-time progress
  useEffect(() => {
    const eventSource = new EventSource('http://localhost:5005/sse');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.event_type === 'PROGRESS') {
        setProgress(data.data.progress);
      } else if (data.event_type === 'TOOL_RESULT') {
        setResult(data.data.result);
        setProgress(100);
      }
    };

    return () => eventSource.close();
  }, []);

  const generateCode = async () => {
    setProgress(0);
    setResult(null);

    const response = await fetch('http://localhost:5005/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: Date.now(),
        method: 'tools/call',
        params: {
          name: 'aider_ai_code',
          arguments: {
            ai_coding_prompt: prompt,
            relative_editable_files: files.filter(f => f.trim())
          }
        }
      })
    });

    const result = await response.json();
    if (result.result) {
      setResult(result.result);
    }
  };

  return (
    <div>
      <h2>AI Code Generator</h2>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe what code you want to generate..."
        rows={4}
        cols={80}
      />

      {files.map((file, index) => (
        <input
          key={index}
          type="text"
          value={file}
          onChange={(e) => {
            const newFiles = [...files];
            newFiles[index] = e.target.value;
            setFiles(newFiles);
          }}
          placeholder="File path (e.g., src/utils.py)"
        />
      ))}

      <button onClick={generateCode}>Generate Code</button>

      {progress > 0 && progress < 100 && (
        <div>
          <progress value={progress} max={100} />
          <span>{progress}%</span>
        </div>
      )}

      {result && (
        <div>
          <h3>Result:</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

export default AiderCodeGenerator;
```

### CLI Tool Integration

```python
#!/usr/bin/env python3
"""CLI tool that integrates with Aider MCP Server"""

import subprocess
import json
import sys
import argparse

class AiderCLI:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self.process = None

    def start_server(self):
        """Start Aider MCP Server in stdio mode"""
        self.process = subprocess.Popen([
            'mcp-aider-stdio',
            '--current-working-dir', self.working_dir
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def send_request(self, prompt: str, files: list[str], readonly_files: list[str] = None):
        """Send a coding request to Aider"""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "aider_ai_code",
                "arguments": {
                    "ai_coding_prompt": prompt,
                    "relative_editable_files": files,
                    "relative_readonly_files": readonly_files or []
                }
            }
        }

        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()

        response = self.process.stdout.readline()
        return json.loads(response)

    def ask_question(self, question: str, files: list[str] = None):
        """Ask a question about the codebase"""
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "aider_ai_ask",
                "arguments": {
                    "ai_coding_prompt": question,
                    "relative_readonly_files": files or []
                }
            }
        }

        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()

        response = self.process.stdout.readline()
        return json.loads(response)

def main():
    parser = argparse.ArgumentParser(description='Aider CLI Tool')
    parser.add_argument('--dir', required=True, help='Working directory')
    parser.add_argument('--prompt', required=True, help='Coding prompt')
    parser.add_argument('--files', nargs='+', required=True, help='Files to edit')
    parser.add_argument('--readonly', nargs='*', help='Read-only context files')

    args = parser.parse_args()

    cli = AiderCLI(args.dir)
    cli.start_server()

    try:
        result = cli.send_request(args.prompt, args.files, args.readonly)

        if result.get('result', {}).get('isError'):
            print("Error:", result['result']['content'][0]['text'])
            sys.exit(1)
        else:
            print("Success!")
            print(result['result']['content'][0]['text'])

    finally:
        if cli.process:
            cli.process.terminate()

if __name__ == '__main__':
    main()
```

Usage:
```bash
python aider_cli.py \
  --dir /path/to/project \
  --prompt "Add logging to all API endpoints" \
  --files api/routes.py api/middleware.py \
  --readonly config/logging.yaml
```

## Real-World Scenarios

### Bug Fix Workflow

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Fix the memory leak in the image processing pipeline. The issue appears to be that image objects are not being properly released after processing.",
      "relative_editable_files": [
        "src/processing/image_processor.py",
        "src/processing/pipeline.py"
      ],
      "relative_readonly_files": [
        "tests/test_image_processing.py",
        "src/models/image.py",
        "docs/memory_usage_report.md"
      ]
    }
  }
}
```

### Feature Addition

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Add dark mode support to the web application. Include CSS variables for theming, toggle functionality, and persistence of user preference.",
      "relative_editable_files": [
        "static/css/themes.css",
        "static/js/theme-toggle.js",
        "templates/base.html",
        "src/preferences/theme.py"
      ],
      "relative_readonly_files": [
        "static/css/main.css",
        "src/models/user.py"
      ]
    }
  }
}
```

### Code Review Assistant

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_ask",
    "arguments": {
      "ai_coding_prompt": "Review this authentication code for security vulnerabilities. Pay special attention to session management, password handling, and potential injection attacks.",
      "relative_readonly_files": [
        "src/auth/login.py",
        "src/auth/session.py",
        "src/auth/password.py",
        "src/middleware/security.py"
      ]
    }
  }
}
```

### Documentation Generation

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Generate comprehensive API documentation for all endpoints. Include request/response examples, error codes, and authentication requirements.",
      "relative_editable_files": [
        "docs/api.md",
        "docs/authentication.md",
        "docs/examples.md"
      ],
      "relative_readonly_files": [
        "src/api/routes.py",
        "src/api/auth.py",
        "src/models/",
        "tests/test_api.py"
      ]
    }
  }
}
```

## Performance Optimization

### Using Architect Mode for Large Tasks

For complex multi-file changes, architect mode provides better results:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "aider_ai_code",
    "arguments": {
      "ai_coding_prompt": "Optimize the database layer for better performance. Implement connection pooling, query optimization, and caching strategies.",
      "relative_editable_files": [
        "src/database/connection.py",
        "src/database/query_builder.py",
        "src/database/cache.py",
        "src/database/pool.py"
      ],
      "architect_mode": true,
      "editor_model": "gpt-4o-mini"
    }
  }
}
```

### Model Selection for Different Tasks

Choose appropriate models based on task complexity:

```javascript
// Simple tasks - use faster, cheaper models
const simpleTask = {
  name: "aider_ai_code",
  arguments: {
    ai_coding_prompt: "Add a docstring to this function",
    relative_editable_files: ["utils.py"],
    model: "gpt-4o-mini"
  }
};

// Complex tasks - use more capable models
const complexTask = {
  name: "aider_ai_code",
  arguments: {
    ai_coding_prompt: "Refactor this legacy codebase to use modern patterns",
    relative_editable_files: ["legacy/", "modern/"],
    model: "gpt-4o",
    architect_mode: true
  }
};
```

## Error Handling Examples

### Robust Client Implementation

```python
import json
import httpx
import asyncio
from typing import Optional

class AiderClient:
    def __init__(self, base_url: str = "http://localhost:5005"):
        self.base_url = base_url

    async def code_request(self, prompt: str, files: list[str],
                          readonly_files: Optional[list[str]] = None,
                          max_retries: int = 3) -> dict:
        """Make a code generation request with error handling and retries"""

        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "aider_ai_code",
                "arguments": {
                    "ai_coding_prompt": prompt,
                    "relative_editable_files": files,
                    "relative_readonly_files": readonly_files or []
                }
            }
        }

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{self.base_url}/mcp",
                        json=request_data
                    )
                    response.raise_for_status()

                    result = response.json()

                    # Check for application-level errors
                    if 'error' in result:
                        raise Exception(f"MCP Error: {result['error']['message']}")

                    if result.get('result', {}).get('isError'):
                        raise Exception(f"Tool Error: {result['result']['content'][0]['text']}")

                    return result

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise Exception("Request timed out after retries")

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise Exception(f"HTTP Error: {e.response.status_code}")

            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise e

        raise Exception("Max retries exceeded")

# Usage
async def main():
    client = AiderClient()

    try:
        result = await client.code_request(
            prompt="Add error handling to this function",
            files=["src/utils.py"],
            readonly_files=["tests/test_utils.py"]
        )
        print("Success:", result['result']['content'][0]['text'])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing Examples

### Unit Testing MCP Integration

```python
import pytest
import json
from unittest.mock import Mock, patch
from aider_client import AiderClient

class TestAiderIntegration:

    @pytest.fixture
    def mock_response(self):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Successfully generated code"
                    }
                ],
                "isError": False
            }
        }

    @pytest.mark.asyncio
    async def test_successful_code_generation(self, mock_response):
        client = AiderClient()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.return_value.json.return_value = mock_response
            mock_client.return_value.__aenter__.return_value.post.return_value.raise_for_status.return_value = None

            result = await client.code_request(
                prompt="Test prompt",
                files=["test.py"]
            )

            assert result == mock_response
            assert not result['result']['isError']

    @pytest.mark.asyncio
    async def test_error_handling(self):
        client = AiderClient()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("Connection failed")

            with pytest.raises(Exception, match="Connection failed"):
                await client.code_request(
                    prompt="Test prompt",
                    files=["test.py"]
                )
```

These examples demonstrate the flexibility and power of Aider MCP Server across different use cases, from simple code generation to complex enterprise integrations. The key is choosing the right transport mechanism and configuring the appropriate models for your specific needs.
