# Atomic Design Architecture

## Overview

The Aider MCP Server has been completely refactored using **Atomic Design** principles, creating a maintainable, scalable, and well-organized codebase. This document explains the architecture, its benefits, and how to navigate the new structure.

## Atomic Design Principles

Atomic Design is a methodology for creating design systems by breaking down interfaces into their smallest parts and building up from there. In software architecture, we apply these same principles to organize code into hierarchical layers of increasing complexity.

### The Four Layers

#### 1. **Atoms** (`src/aider_mcp_server/atoms/`)

**Purpose**: Fundamental building blocks - the smallest, most reusable components.

**What belongs here**:
- Basic data types and protocols
- Utility functions
- Core constants
- Logging mechanisms
- Error definitions
- Simple validation logic

**Examples**:
```
atoms/
├── errors/
│   ├── application_errors.py    # Core error classes
│   └── __init__.py
├── logging/
│   ├── logger.py                # Basic logging functionality
│   └── __init__.py
├── security/
│   ├── context.py               # Security context definitions
│   ├── errors.py                # Security-specific errors
│   └── permissions.py           # Permission protocols
├── types/
│   ├── auth_protocols.py        # Authentication interfaces
│   ├── data_types.py           # Core data structures
│   ├── event_types.py          # Event type definitions
│   ├── handler_protocols.py    # Request handler interfaces
│   ├── mcp_types.py            # MCP-specific types
│   ├── streaming_types.py      # Streaming-related types
│   └── transport_protocols.py  # Transport layer interfaces
└── utils/
    ├── aider_validation.py      # Aider parameter validation
    ├── config_constants.py      # Configuration constants
    ├── diff_cache.py           # File difference caching
    └── fallback_config.py      # Configuration fallbacks
```

#### 2. **Molecules** (`src/aider_mcp_server/molecules/`)

**Purpose**: Combinations of atoms that form more complex, but still focused, functionality.

**What belongs here**:
- Service implementations
- Business logic modules
- Data processing components
- Tool implementations
- Configuration management

**Examples**:
```
molecules/
├── configuration/
│   ├── configuration_manager.py # Configuration handling
│   ├── dependency_resolver.py   # Dependency injection
│   ├── legacy_bridge.py         # Legacy compatibility
│   └── service_locator.py       # Service discovery
├── events/
│   ├── event_mediator.py        # Event distribution
│   ├── event_participant.py     # Event participation
│   └── event_system.py          # Core event handling
├── execution/
│   ├── progress_tracker.py      # Task progress monitoring
│   ├── resource_manager.py      # Resource allocation
│   └── retry_handler.py         # Retry logic
├── monitoring/
│   ├── health_monitor.py        # Health checking
│   ├── health_tracker.py        # Health tracking
│   ├── metrics_collector.py     # Metrics collection
│   └── request_monitor.py       # Request monitoring
├── security/
│   ├── auth_provider.py         # Authentication services
│   └── security_service.py      # Security validation
├── session/
│   ├── session_context.py       # Session management
│   └── session_manager.py       # Session lifecycle
├── tools/
│   ├── aider/                   # Aider tool decomposition
│   │   ├── api_validation.py    # API key validation
│   │   ├── cache_management.py  # Cache integration
│   │   ├── core_execution.py    # Core Aider execution
│   │   ├── rate_limiting.py     # Rate limit handling
│   │   ├── response_formatting.py # Response processing
│   │   └── session_coordination.py # Session management
│   ├── aider_ai_ask.py          # Aider ask tool
│   ├── aider_ai_code.py         # Main Aider tool (refactored)
│   └── aider_list_models.py     # Model listing tool
└── transport/
    └── base_adapter.py          # Base transport functionality
```

#### 3. **Organisms** (`src/aider_mcp_server/organisms/`)

**Purpose**: Complex components that combine molecules and atoms to implement major features.

**What belongs here**:
- Coordinators and orchestrators
- Transport adapters
- Request processors
- Registry services
- Multi-component features

**Examples**:
```
organisms/
├── coordinators/
│   ├── event_coordinator.py     # Event orchestration
│   ├── health_coordinator.py    # Health management
│   ├── resource_coordinator.py  # Resource coordination
│   └── transport_coordinator.py # Transport lifecycle
├── processors/
│   ├── error_handling.py        # Error processing
│   ├── handlers.py              # Request handlers
│   ├── progress_reporter.py     # Progress reporting
│   └── request_processor.py     # Request processing
├── registries/
│   ├── handler_registry.py      # Handler registration
│   └── transport_registry.py    # Transport registration
└── transports/
    ├── http/
    │   └── http_streamable_transport_adapter.py
    ├── sse/
    │   └── sse_transport_adapter.py
    └── stdio/
        └── stdio_transport_adapter.py
```

#### 4. **Pages** (`src/aider_mcp_server/pages/`)

**Purpose**: Complete application flows and entry points that coordinate all lower layers.

**What belongs here**:
- Application coordinators
- Server implementations
- CLI interfaces
- Main application flows

**Examples**:
```
pages/
└── application/
    ├── app.py          # Application setup and coordination
    └── coordinator.py  # Main application coordinator
```

## Key Refactoring Accomplishments

### 1. Interface Directory Elimination

**Before**: All interfaces were centralized in a single `interfaces/` directory.

**After**: Interfaces are distributed to appropriate atomic layers based on their complexity and dependencies.

| Original Interface | New Location | Atomic Layer |
|-------------------|--------------|--------------|
| `transport_adapter.py` | `atoms/types/transport_protocols.py` | Atom |
| `authentication_provider.py` | `atoms/types/auth_protocols.py` | Atom |
| `request_handler.py` | `atoms/types/handler_protocols.py` | Atom |
| `security_service.py` | `molecules/security/interface.py` | Molecule |
| `application_coordinator.py` | `organisms/coordinators/coordinator_interface.py` | Organism |

### 2. Aider AI Code Decomposition

**Before**: Single monolithic file (`aider_ai_code.py`) with 1,847 lines.

**After**: Split into 6 focused modules in `molecules/tools/aider/`:

| Module | Responsibility | Lines |
|--------|---------------|-------|
| `core_execution.py` | Core Aider execution logic | ~400 |
| `rate_limiting.py` | Rate limit detection and handling | ~300 |
| `response_formatting.py` | Response processing and formatting | ~300 |
| `cache_management.py` | Diff cache integration | ~200 |
| `api_validation.py` | API key validation and setup | ~200 |
| `session_coordination.py` | Session lifecycle and events | ~300 |
| `__init__.py` | Public API facade | ~50 |

### 3. Application Coordinator Refactoring

**Before**: Single monolithic `ApplicationCoordinator` handling all coordination.

**After**: Split into focused coordinators in `organisms/coordinators/`:

| Coordinator | Responsibility |
|------------|---------------|
| `transport_coordinator.py` | Transport lifecycle management |
| `event_coordinator.py` | Event distribution and handling |
| `health_coordinator.py` | Health monitoring and reporting |
| `resource_coordinator.py` | Resource allocation and cleanup |

### 4. Templates Directory Deprecation

**Before**: Legacy `templates/` directory with outdated patterns.

**After**: Marked as `DEPRECATED.md` with clear migration paths to atomic structure.

## Benefits of the New Architecture

### 1. **Clear Separation of Concerns**
Each layer has a well-defined responsibility, making it easier to understand and modify code.

### 2. **High Reusability**
Atoms and molecules can be easily reused across different parts of the application.

### 3. **Easier Testing**
Smaller, focused modules are easier to test in isolation.

### 4. **Better Maintainability**
Changes to one layer don't ripple through the entire codebase unnecessarily.

### 5. **Scalable Architecture**
New features can be added by composing existing atoms and molecules.

### 6. **Clear Dependencies**
The hierarchy ensures that dependencies flow in one direction (atoms → molecules → organisms → pages).

## Navigation Guide

### Finding Functionality

**To find basic types or utilities**: Look in `atoms/`
- Data types: `atoms/types/`
- Utilities: `atoms/utils/`
- Core errors: `atoms/errors/`

**To find business logic**: Look in `molecules/`
- Service implementations: `molecules/*/`
- Tool logic: `molecules/tools/`
- Configuration: `molecules/configuration/`

**To find complex features**: Look in `organisms/`
- Coordinators: `organisms/coordinators/`
- Transport adapters: `organisms/transports/`
- Request processing: `organisms/processors/`

**To find application entry points**: Look in `pages/`
- Main application: `pages/application/`

### Import Patterns

```python
# Importing atoms (basic building blocks)
from aider_mcp_server.atoms.types.event_types import EventType
from aider_mcp_server.atoms.utils.diff_cache import DiffCache

# Importing molecules (focused functionality)
from aider_mcp_server.molecules.configuration.configuration_manager import ConfigurationManager
from aider_mcp_server.molecules.tools.aider.core_execution import execute_aider_request

# Importing organisms (complex features)
from aider_mcp_server.organisms.coordinators.transport_coordinator import TransportCoordinator
from aider_mcp_server.organisms.transports.sse.sse_transport_adapter import SSETransportAdapter

# Importing pages (application flows)
from aider_mcp_server.pages.application.coordinator import ApplicationCoordinator
```

## Backward Compatibility

The refactoring maintains **100% backward compatibility** through import aliases. Existing code continues to work without changes:

```python
# These old imports still work thanks to aliases
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
from aider_mcp_server.tools.aider_ai_code import process_aider_ai_code_request

# But the new imports are recommended for new code
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.molecules.tools.aider.core_execution import execute_aider_request
```

## Best Practices for Development

### 1. **Follow the Hierarchy**
- Atoms should never import from molecules, organisms, or pages
- Molecules can import from atoms but not organisms or pages
- Organisms can import from atoms and molecules but not pages
- Pages can import from any layer

### 2. **Keep Atoms Simple**
- Atoms should be stateless when possible
- Focus on single responsibilities
- Avoid complex business logic

### 3. **Make Molecules Focused**
- Each molecule should have a clear, single purpose
- Combine atoms to create useful functionality
- Keep interfaces clean and minimal

### 4. **Design Organisms for Composition**
- Organisms should coordinate multiple molecules
- Focus on orchestration rather than implementation
- Provide clear APIs for pages to use

### 5. **Keep Pages Minimal**
- Pages should primarily coordinate organisms
- Minimize business logic in pages
- Focus on application flow and user interface

## Migration from Legacy Structure

See the [Migration Guide](./migration-guide.md) for detailed instructions on adapting existing code to the new atomic structure.

## Conclusion

The Atomic Design refactoring has transformed the Aider MCP Server from a monolithic structure into a well-organized, maintainable, and scalable architecture. The clear separation of concerns, hierarchical organization, and backward compatibility ensure that the codebase is ready for future growth while remaining accessible to current users.
