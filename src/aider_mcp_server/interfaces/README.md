# DEPRECATED: Interface Directory

⚠️ **This directory is deprecated as of the Atomic Design Compliance Refactoring.**

## Migration Status

This directory previously contained interface definitions that have been **successfully redistributed** to follow Atomic Design principles. All interfaces have been moved to their appropriate atomic design layers.

## Interface Migration Map

| Original Interface | New Location | Status |
|-------------------|--------------|--------|
| `ITransportAdapter` | `atoms/types/transport_protocols.py` | ✅ **MIGRATED** |
| `IAuthenticationProvider` | `atoms/types/auth_protocols.py` | ✅ **MIGRATED** |
| `IRequestHandler` | `atoms/types/handler_protocols.py` | ✅ **MIGRATED** |
| `IErrorHandler` | `atoms/types/handler_protocols.py` | ✅ **MIGRATED** |
| `IEventHandler` | `atoms/types/handler_protocols.py` | ✅ **MIGRATED** |
| `IApplicationCoordinator` | `organisms/coordinators/coordinator_interface.py` | ✅ **MIGRATED** |
| `IEventCoordinator` | `organisms/coordinators/event_interface.py` | ✅ **MIGRATED** |
| `IDependencyContainer` | `organisms/coordinators/container_interface.py` | ✅ **MIGRATED** |
| `ISecurityService` | `molecules/security/interface.py` | ✅ **MIGRATED** |
| `TransportAdapterRegistry` | `organisms/registries/registry_interface.py` | ✅ **MIGRATED** |

## Backward Compatibility

✅ **All imports from `aider_mcp_server.interfaces.*` continue to work** through alias files that redirect to the new locations.

## Migration Guide

### For New Code
Use the new atomic design locations:

```python
# ✅ NEW - Use atomic design locations
from aider_mcp_server.atoms.types.transport_protocols import ITransportAdapter
from aider_mcp_server.organisms.coordinators.coordinator_interface import IApplicationCoordinator
```

### For Existing Code
Existing imports will continue working but are deprecated:

```python
# ⚠️ DEPRECATED - Still works but discouraged
from aider_mcp_server.interfaces.transport_adapter import ITransportAdapter
from aider_mcp_server.interfaces.application_coordinator import IApplicationCoordinator
```

## Verification Report

**Verification Date:** December 4, 2025  
**Test Suite Status:** ✅ 660 tests passing, 5 skipped  
**Functionality Check:** ✅ All interface functionality preserved  
**Import Compatibility:** ✅ Both old and new import paths working  
**Static Analysis:** ✅ No broken imports detected  

## Atomic Design Benefits

The redistribution provides:

1. **🏗️ Better Organization**: Interfaces are co-located with their implementations
2. **📦 Atomic Design Compliance**: Clear separation of concerns by complexity
3. **🔄 Improved Maintainability**: Easier to find and update related interfaces
4. **⚡ Better Discoverability**: Related types and protocols grouped together
5. **🧪 Enhanced Testing**: Atomic components can be tested in isolation

## Timeline

- **Phase 1** (Tasks 3-5): Interface redistribution ✅ **COMPLETE**
- **Phase 2** (Task 6): Verification and deprecation ✅ **COMPLETE**  
- **Phase 3** (Future): Remove deprecated aliases after transition period

## Related Documentation

- [Atomic Design Principles](../../docs/atomic-design.md)
- [Migration Scripts](../../../scripts/README.md)
- [Interface Redistribution Guide](../../../docs/interface-migration.md)

---

**This directory will be maintained for backward compatibility during the transition period. New development should use the atomic design interface locations.**