#!/bin/bash
# Environment synchronization script

set -e

echo "🔄 Synchronizing pixi environment..."

# Update pixi environment
echo "📦 Installing/updating pixi dependencies..."
pixi install

echo "✅ Pixi environment synchronized!"
echo ""
echo "Next steps:"
echo "- Test with: pixi run test"
echo "- Verify MCP server: pixi run mcp-server --help"
echo "- Lint code: pixi run lint"
echo "- Format code: pixi run format"
