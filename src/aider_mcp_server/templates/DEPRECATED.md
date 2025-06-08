# Templates Directory - DEPRECATED

⚠️ **WARNING: This directory is deprecated and will be removed in a future version.**

## Migration Notice

The `templates/` directory contains legacy implementations that have been superseded by the new **Atomic Design Compliance** architecture. All functionality has been migrated to appropriate atomic layers.

### Migration Path

| Legacy Component | New Location | Status |
|------------------|--------------|--------|
| `configuration/configuration_system.py` | `molecules/configuration/configuration_manager.py` + `legacy_bridge.py` | ✅ Migrated with compatibility layer |
| `configuration/dependency_container.py` | `molecules/configuration/service_locator.py` + `dependency_resolver.py` | ✅ Enhanced and migrated |
| `initialization/session_manager.py` | `molecules/session/session_manager.py` | ✅ Migrated and enhanced |
| `initialization/initialization_sequence.py` | `organisms/initialization/startup_sequence.py` | ✅ Migrated and enhanced |
| `initialization/cli.py` | `organisms/cli/` (planned) | 🚧 Planned migration |
| `servers/server.py` | Organism transport adapters + extracted logic | 🚧 Partial migration |
| `servers/sse_server.py` | `organisms/transports/sse/` | ✅ Mostly covered |
| `servers/http_server.py` | `organisms/transports/http/` | ✅ Mostly covered |

### How to Update Your Code

#### Configuration System
```python
# OLD (deprecated)
from aider_mcp_server.templates.configuration.configuration_system import get_config
config = get_config()

# NEW (recommended)
from aider_mcp_server.molecules.configuration.configuration_manager import ConfigurationManager
config_manager = ConfigurationManager()

# TEMPORARY (for backward compatibility)
from aider_mcp_server.molecules.configuration.legacy_bridge import get_config
config = get_config()  # Will show deprecation warning
```

#### Dependency Injection
```python
# OLD (deprecated)
from aider_mcp_server.templates.configuration.dependency_container import DependencyContainer

# NEW (recommended) 
from aider_mcp_server.molecules.configuration.service_locator import ServiceLocator
from aider_mcp_server.molecules.configuration.dependency_resolver import DependencyResolver
```

#### Session Management
```python
# OLD (deprecated)
from aider_mcp_server.templates.initialization.session_manager import SessionManager

# NEW (recommended)
from aider_mcp_server.molecules.session.session_manager import SessionManager
```

#### Application Initialization
```python
# OLD (deprecated)
from aider_mcp_server.templates.initialization.initialization_sequence import initialize_application

# NEW (recommended)
from aider_mcp_server.organisms.initialization.startup_sequence import StartupSequence
startup = StartupSequence()
coordinator = await startup.initialize_application()
```

### Timeline

- **Phase 1** (Current): Legacy bridge and compatibility layers active
- **Phase 2** (Next release): Deprecation warnings added to all template imports
- **Phase 3** (Future release): Templates directory removed

### Getting Help

If you encounter issues during migration:

1. Check the new atomic design documentation
2. Review the migration examples above
3. Look at the compatibility bridge implementations
4. Create an issue if you find missing functionality

### Benefits of Migration

The new atomic design structure provides:

- ✅ **Better separation of concerns**
- ✅ **Improved testability**
- ✅ **Enhanced modularity**
- ✅ **Clearer dependency management**
- ✅ **Better performance**
- ✅ **More comprehensive features**

---

*This migration was completed as part of Task 19 - Redistribute Template Directory Content during the Atomic Design Compliance Refactoring project.*