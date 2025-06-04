#!/usr/bin/env python3
"""
Interface Migration Verification Script

This script verifies that the interface redistribution was completed successfully
and that both old and new import paths work correctly.

Usage:
    python scripts/verify_interface_migration.py
"""

import sys
from typing import List, Tuple


def test_interface_imports() -> Tuple[List[str], List[str]]:
    """Test that all interface imports work correctly.

    Returns:
        Tuple of (successful_imports, failed_imports)
    """
    successful = []
    failed = []

    # Test new atomic design imports
    new_imports = [
        ("aider_mcp_server.atoms.types.transport_protocols", "ITransportAdapter"),
        ("aider_mcp_server.atoms.types.auth_protocols", "IAuthenticationProvider"),
        ("aider_mcp_server.atoms.types.handler_protocols", "IRequestHandler"),
        ("aider_mcp_server.atoms.types.handler_protocols", "IErrorHandler"),
        ("aider_mcp_server.atoms.types.handler_protocols", "IEventHandler"),
        ("aider_mcp_server.organisms.coordinators.coordinator_interface", "IApplicationCoordinator"),
        ("aider_mcp_server.organisms.coordinators.event_interface", "IEventCoordinator"),
        ("aider_mcp_server.organisms.coordinators.container_interface", "IDependencyContainer"),
        ("aider_mcp_server.molecules.security.interface", "ISecurityService"),
        ("aider_mcp_server.organisms.registries.registry_interface", "TransportAdapterRegistry"),
    ]

    # Test legacy interface imports (should work through aliases)
    legacy_imports = [
        ("aider_mcp_server.interfaces.transport_adapter", "ITransportAdapter"),
        ("aider_mcp_server.interfaces.authentication_provider", "IAuthenticationProvider"),
        ("aider_mcp_server.interfaces.request_handler", "IRequestHandler"),
        ("aider_mcp_server.interfaces.error_handler", "IErrorHandler"),
        ("aider_mcp_server.interfaces.event_handler", "IEventHandler"),
        ("aider_mcp_server.interfaces.application_coordinator", "IApplicationCoordinator"),
        ("aider_mcp_server.interfaces.event_coordinator", "IEventCoordinator"),
        ("aider_mcp_server.interfaces.dependency_container", "IDependencyContainer"),
        ("aider_mcp_server.interfaces.security_service", "ISecurityService"),
        ("aider_mcp_server.interfaces.transport_registry", "TransportAdapterRegistry"),
    ]

    all_imports = [("NEW", new_imports), ("LEGACY", legacy_imports)]

    for import_type, imports in all_imports:
        print(f"\\n=== Testing {import_type} Imports ===")

        for module_name, class_name in imports:
            try:
                module = __import__(module_name, fromlist=[class_name])
                interface_class = getattr(module, class_name)

                # Verify it's actually a class/protocol
                if hasattr(interface_class, "__name__"):
                    success_msg = f"{import_type}: {module_name}.{class_name} ✅"
                    print(success_msg)
                    successful.append(success_msg)
                else:
                    error_msg = f"{import_type}: {module_name}.{class_name} ❌ (not a valid class)"
                    print(error_msg)
                    failed.append(error_msg)

            except ImportError as e:
                error_msg = f"{import_type}: {module_name}.{class_name} ❌ (ImportError: {e})"
                print(error_msg)
                failed.append(error_msg)
            except AttributeError as e:
                error_msg = f"{import_type}: {module_name}.{class_name} ❌ (AttributeError: {e})"
                print(error_msg)
                failed.append(error_msg)
            except Exception as e:
                error_msg = f"{import_type}: {module_name}.{class_name} ❌ (Error: {e})"
                print(error_msg)
                failed.append(error_msg)

    return successful, failed


def test_interface_equivalence() -> List[str]:
    """Test that old and new interfaces are equivalent."""
    equivalence_failures = []

    print("\\n=== Testing Interface Equivalence ===")

    # Test pairs that should be the same interface
    test_pairs = [
        (
            ("aider_mcp_server.atoms.types.transport_protocols", "ITransportAdapter"),
            ("aider_mcp_server.interfaces.transport_adapter", "ITransportAdapter"),
        ),
        (
            ("aider_mcp_server.organisms.coordinators.coordinator_interface", "IApplicationCoordinator"),
            ("aider_mcp_server.interfaces.application_coordinator", "IApplicationCoordinator"),
        ),
    ]

    for (new_module, new_class), (old_module, old_class) in test_pairs:
        try:
            new_interface = getattr(__import__(new_module, fromlist=[new_class]), new_class)
            old_interface = getattr(__import__(old_module, fromlist=[old_class]), old_class)

            # Check if they're the same object (perfect alias) or have same name
            if new_interface is old_interface:
                print(f"✅ {new_class}: Perfect alias (same object)")
            elif hasattr(new_interface, "__name__") and hasattr(old_interface, "__name__"):
                if new_interface.__name__ == old_interface.__name__:
                    print(f"✅ {new_class}: Name equivalence maintained")
                else:
                    error_msg = f"❌ {new_class}: Name mismatch ({new_interface.__name__} vs {old_interface.__name__})"
                    print(error_msg)
                    equivalence_failures.append(error_msg)
            else:
                print(f"⚠️  {new_class}: Cannot verify equivalence (missing __name__)")

        except Exception as e:
            error_msg = f"❌ {new_class}: Equivalence test failed ({e})"
            print(error_msg)
            equivalence_failures.append(error_msg)

    return equivalence_failures


def main():
    """Run the verification script."""
    print("🔍 Interface Migration Verification Script")
    print("=" * 50)

    # Test imports
    successful, failed = test_interface_imports()

    # Test equivalence
    equivalence_failures = test_interface_equivalence()

    # Summary
    print("\\n" + "=" * 50)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 50)

    print(f"✅ Successful imports: {len(successful)}")
    print(f"❌ Failed imports: {len(failed)}")
    print(f"⚠️  Equivalence failures: {len(equivalence_failures)}")

    if failed:
        print("\\n❌ FAILED IMPORTS:")
        for failure in failed:
            print(f"   {failure}")

    if equivalence_failures:
        print("\\n⚠️  EQUIVALENCE FAILURES:")
        for failure in equivalence_failures:
            print(f"   {failure}")

    # Overall result
    total_failures = len(failed) + len(equivalence_failures)
    if total_failures == 0:
        print("\\n🎉 ALL VERIFICATION TESTS PASSED!")
        print("   ✅ Interface redistribution completed successfully")
        print("   ✅ Backward compatibility maintained")
        print("   ✅ Both old and new import paths working")
        return 0
    else:
        print(f"\\n❌ VERIFICATION FAILED ({total_failures} issues found)")
        print("   Please check the interface migration and alias setup")
        return 1


if __name__ == "__main__":
    sys.exit(main())
