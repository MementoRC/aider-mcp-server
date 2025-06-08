# Migration Guide: Atomic Design Refactoring

## Overview

This guide helps developers migrate existing code to work with the new Atomic Design architecture of Aider MCP Server. The refactoring maintains 100% backward compatibility through import aliases, but new development should use the new structure.

## Migration Strategy

### Immediate Actions Required: **NONE**

✅ **All existing code continues to work without changes** due to import aliases.

### Recommended Actions for New Development

1. **Use new import paths** for better organization
2. **Follow atomic design principles** for new features
3. **Gradually migrate existing code** when making significant changes

## Import Path Changes

### 1. Interface Imports

**OLD (still works via aliases)**:
```python
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
from aider_mcp_server.interfaces.authentication_provider import IAuthenticationProvider
from aider_mcp_server.interfaces.request_handler import IRequestHandler
from aider_mcp_server.interfaces.security_service import ISecurityService
from aider_mcp_server.interfaces.application_coordinator import IApplicationCoordinator
```

**NEW (recommended)**:
```python
# Basic protocols (atoms)
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.atoms.types.auth_protocols import IAuthenticationProvider
from aider_mcp_server.atoms.types.handler_protocols import IRequestHandler

# Service interfaces (molecules)
from aider_mcp_server.molecules.security.interface import ISecurityService

# Coordination interfaces (organisms)
from aider_mcp_server.organisms.coordinators.coordinator_interface import IApplicationCoordinator
```

### 2. Aider Tool Imports

**OLD (still works via aliases)**:
```python
from aider_mcp_server.tools.aider_ai_code import (
    process_aider_ai_code_request,
    setup_aider_coder,
    configure_model,
    code_with_aider
)
```

**NEW (recommended)**:
```python
# Import from specific modules for better organization
from aider_mcp_server.molecules.tools.aider.core_execution import execute_aider_request
from aider_mcp_server.molecules.tools.aider.api_validation import validate_api_configuration
from aider_mcp_server.molecules.tools.aider.rate_limiting import handle_rate_limits
from aider_mcp_server.molecules.tools.aider.response_formatting import format_aider_response
from aider_mcp_server.molecules.tools.aider.cache_management import manage_diff_cache
from aider_mcp_server.molecules.tools.aider.session_coordination import coordinate_session

# Or use the public API facade
from aider_mcp_server.molecules.tools.aider import (
    execute_aider_request,
    validate_api_configuration,
    handle_rate_limits
)
```

### 3. Utility and Type Imports

**OLD (still works via aliases)**:
```python
from aider_mcp_server.atoms.diff_cache import DiffCache
from aider_mcp_server.atoms.event_types import EventType
from aider_mcp_server.atoms.data_types import SessionContext
```

**NEW (recommended)**:
```python
from aider_mcp_server.atoms.utils.diff_cache import DiffCache
from aider_mcp_server.atoms.types.event_types import EventType
from aider_mcp_server.atoms.types.data_types import SessionContext
```

### 4. Configuration and Service Imports

**OLD (still works via aliases)**:
```python
from aider_mcp_server.configuration_manager import ConfigurationManager
from aider_mcp_server.security_service import SecurityService
```

**NEW (recommended)**:
```python
from aider_mcp_server.molecules.configuration.configuration_manager import ConfigurationManager
from aider_mcp_server.molecules.security.security_service import SecurityService
```

## Step-by-Step Migration

### For Existing Projects

#### Step 1: Update Your Dependencies
Ensure you're using the latest version of aider-mcp-server that includes the atomic design refactoring.

```bash
pip install --upgrade aider-mcp-server
```

#### Step 2: Test Existing Functionality
Run your existing tests to verify everything still works:

```bash
python -m pytest your_tests/
```

#### Step 3: Gradually Update Imports (Optional)
When modifying existing files, consider updating imports to use the new paths:

```python
# Before
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter

# After
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
```

#### Step 4: Use New Structure for New Features
When adding new functionality, follow the atomic design principles:

```python
# New feature using atomic design
from aider_mcp_server.atoms.types.event_types import EventType
from aider_mcp_server.molecules.events.event_mediator import EventMediator
from aider_mcp_server.organisms.coordinators.event_coordinator import EventCoordinator
```

### For New Projects

#### Step 1: Use New Import Paths from the Start
```python
# Recommended imports for new projects
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.molecules.tools.aider import execute_aider_request
from aider_mcp_server.organisms.coordinators.transport_coordinator import TransportCoordinator
from aider_mcp_server.pages.application.coordinator import ApplicationCoordinator
```

#### Step 2: Follow Atomic Design Principles
Organize your own code using similar principles:

```
your_project/
├── atoms/          # Basic utilities and types
├── molecules/      # Business logic components
├── organisms/      # Complex features
└── pages/          # Application flows
```

## Common Migration Scenarios

### Scenario 1: Custom Transport Adapter

**OLD**:
```python
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
from aider_mcp_server.atoms.event_types import EventType

class MyCustomAdapter(ITransportAdapter):
    def send_event(self, event: EventType) -> None:
        # Implementation
        pass
```

**NEW**:
```python
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.atoms.types.event_types import EventType

class MyCustomAdapter(ITransportAdapter):
    def send_event(self, event: EventType) -> None:
        # Implementation (unchanged)
        pass
```

### Scenario 2: Custom Request Handler

**OLD**:
```python
from aider_mcp_server.interfaces.request_handler import IRequestHandler
from aider_mcp_server.tools.aider_ai_code import process_aider_ai_code_request

class MyHandler(IRequestHandler):
    def handle_request(self, request):
        return process_aider_ai_code_request(request)
```

**NEW**:
```python
from aider_mcp_server.atoms.types.handler_protocols import IRequestHandler
from aider_mcp_server.molecules.tools.aider.core_execution import execute_aider_request

class MyHandler(IRequestHandler):
    def handle_request(self, request):
        return execute_aider_request(request)
```

### Scenario 3: Configuration Setup

**OLD**:
```python
from aider_mcp_server.configuration_manager import ConfigurationManager
from aider_mcp_server.security_service import SecurityService

config = ConfigurationManager()
security = SecurityService(config)
```

**NEW**:
```python
from aider_mcp_server.molecules.configuration.configuration_manager import ConfigurationManager
from aider_mcp_server.molecules.security.security_service import SecurityService

config = ConfigurationManager()
security = SecurityService(config)
```

## Troubleshooting

### Issue: Import Errors

**Problem**: Getting `ImportError` or `ModuleNotFoundError`

**Solution**:
1. Verify you're using the latest version of aider-mcp-server
2. Check if you're using the correct import path
3. Use the old import path temporarily while debugging

```python
# If this fails:
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter

# Try the legacy path:
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
```

### Issue: Deprecated Warnings

**Problem**: Seeing deprecation warnings about old import paths

**Solution**: These warnings are informational. Update imports when convenient:

```python
# Warning: "Import from 'interfaces' is deprecated, use 'atoms.types.transport_protocols'"
# Solution: Update the import
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
```

### Issue: Type Checking Errors

**Problem**: Type checkers (mypy, pyright) showing errors with new imports

**Solution**:
1. Update your type checker configuration
2. Add the new paths to your PYTHONPATH
3. Verify all dependencies are updated

### Issue: Missing Functionality

**Problem**: Can't find a function or class in the new location

**Solution**:
1. Check the [architecture documentation](./atomic-design-architecture.md) for the new location
2. Use the old import path temporarily
3. Report the issue if functionality is truly missing

## Migration Checklist

### For Library Maintainers

- [ ] Test existing functionality with latest version
- [ ] Update documentation to use new import paths
- [ ] Add deprecation timeline for old import paths
- [ ] Update examples and tutorials
- [ ] Consider gradual import path migration

### For Application Developers

- [ ] Verify existing code still works
- [ ] Update imports in new code to use atomic structure
- [ ] Follow atomic design principles for new features
- [ ] Update documentation and comments
- [ ] Plan gradual migration of existing code

### For Contributors

- [ ] Use new import paths for all new code
- [ ] Follow atomic design principles for new features
- [ ] Update tests to use new structure
- [ ] Ensure backward compatibility is maintained
- [ ] Document any breaking changes

## Best Practices During Migration

### 1. **Gradual Migration**
Don't try to migrate everything at once. Update imports when you're already modifying code.

### 2. **Test Thoroughly**
Always test after making import changes to ensure functionality is preserved.

### 3. **Use Atomic Principles**
When creating new functionality, think about which atomic layer it belongs in.

### 4. **Document Changes**
Update your project documentation to reflect the new structure.

### 5. **Leverage Backward Compatibility**
Take advantage of the import aliases to migrate at your own pace.

## Timeline and Deprecation

### Current Phase: **Transition Period**
- ✅ New atomic structure is available
- ✅ Old import paths work via aliases
- ✅ No breaking changes

### Future Phases:

**Phase 1** (Next 6 months):
- Deprecation warnings for old import paths
- Continued full backward compatibility
- Documentation updated to show new paths

**Phase 2** (6-12 months):
- More prominent deprecation warnings
- New features only available via new paths
- Migration tools provided

**Phase 3** (12+ months):
- Consider removing old import aliases
- Breaking change with major version bump
- Migration tools and guides provided

## Getting Help

### Resources

1. **Documentation**: [Atomic Design Architecture](./atomic-design-architecture.md)
2. **Examples**: Check the test files for usage examples
3. **Issues**: Report problems on the GitHub issue tracker
4. **Discussions**: Use GitHub Discussions for questions

### Common Questions

**Q: Do I need to migrate immediately?**
A: No, all existing code continues to work. Migrate when convenient.

**Q: Will the old import paths be removed?**
A: Eventually, but not for at least 12 months, and only with a major version bump.

**Q: How do I know which atomic layer to use?**
A: See the [architecture guide](./atomic-design-architecture.md) for guidance on each layer's purpose.

**Q: Can I mix old and new import styles?**
A: Yes, but consistency within a project is recommended.

## Conclusion

The Atomic Design refactoring improves code organization and maintainability while preserving full backward compatibility. Migration is optional and can be done gradually, making it safe to adopt the new structure at your own pace.
