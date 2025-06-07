"""Tests for the resource manager module."""

import asyncio
import pytest
import time
from unittest.mock import Mock

from aider_mcp_server.molecules.execution.resource_manager import (
    PooledResourceAllocator,
    Resource,
    ResourceConstraints,
    ResourceManager,
    ResourceState,
    ResourceType,
    SimpleResourceAllocator,
    cleanup_all_managers,
    get_resource_manager,
    managed_resource,
    register_resource_manager,
)


class TestResource:
    """Test cases for Resource class."""
    
    def test_resource_creation(self):
        """Test Resource creation and initialization."""
        cleanup_func = Mock()
        resource_obj = {"data": "test"}
        metadata = {"key": "value"}
        
        resource = Resource(
            resource_id="test_resource",
            resource_type=ResourceType.MEMORY,
            resource_object=resource_obj,
            cleanup_func=cleanup_func,
            metadata=metadata
        )
        
        assert resource.resource_id == "test_resource"
        assert resource.resource_type == ResourceType.MEMORY
        assert resource.resource_object == resource_obj
        assert resource.cleanup_func == cleanup_func
        assert resource.metadata == metadata
        assert resource.state == ResourceState.ALLOCATED
        assert resource.access_count == 0
    
    def test_resource_access_tracking(self):
        """Test resource access tracking."""
        resource = Resource("test", ResourceType.MEMORY, {"data": "test"})
        
        initial_time = resource.last_accessed
        
        # Access the resource
        obj = resource.access()
        assert obj == {"data": "test"}
        assert resource.access_count == 1
        assert resource.last_accessed >= initial_time
        assert resource.state == ResourceState.IN_USE
        
        # Access again
        resource.access()
        assert resource.access_count == 2
    
    def test_resource_idle_marking(self):
        """Test marking resource as idle."""
        resource = Resource("test", ResourceType.MEMORY, {"data": "test"})
        resource.access()  # Mark as in use
        
        assert resource.state == ResourceState.IN_USE
        
        resource.mark_idle()
        assert resource.state == ResourceState.IDLE
    
    def test_resource_age_and_idle_time(self):
        """Test age and idle time calculations."""
        resource = Resource("test", ResourceType.MEMORY, {"data": "test"})
        
        time.sleep(0.01)
        age = resource.get_age()
        assert age > 0
        
        idle_time = resource.get_idle_time()
        assert idle_time > 0
        
        # Access should reset idle time
        time.sleep(0.01)
        resource.access()
        new_idle_time = resource.get_idle_time()
        assert new_idle_time < idle_time
    
    def test_resource_to_dict(self):
        """Test resource dictionary conversion."""
        resource = Resource(
            "test",
            ResourceType.FILE,
            {"data": "test"},
            metadata={"category": "temp"}
        )
        resource.access()
        
        resource_dict = resource.to_dict()
        assert resource_dict["resource_id"] == "test"
        assert resource_dict["resource_type"] == "file"
        assert resource_dict["state"] == "in_use"
        assert resource_dict["access_count"] == 1
        assert "age" in resource_dict
        assert "idle_time" in resource_dict
        assert resource_dict["metadata"]["category"] == "temp"


class TestResourceConstraints:
    """Test cases for ResourceConstraints."""
    
    def test_constraints_creation(self):
        """Test ResourceConstraints creation."""
        constraints = ResourceConstraints(
            max_resources=10,
            max_memory_mb=100.0,
            max_idle_time=300.0,
            max_age=3600.0,
            max_access_count=1000
        )
        
        assert constraints.max_resources == 10
        assert constraints.max_memory_mb == 100.0
        assert constraints.max_idle_time == 300.0
        assert constraints.max_age == 3600.0
        assert constraints.max_access_count == 1000


class TestResourceAllocators:
    """Test cases for resource allocators."""
    
    def test_simple_resource_allocator(self):
        """Test SimpleResourceAllocator."""
        def factory_func(data):
            return {"created": data}
        
        allocator = SimpleResourceAllocator(factory_func)
        
        # Test allocation
        result = allocator.allocate("test_id", "test_data")
        assert result == {"created": "test_data"}
        
        # Test constraints checking
        constraints = ResourceConstraints(max_resources=2)
        resources = {"res1": Mock(), "res2": Mock()}
        
        assert not allocator.can_allocate(resources, constraints)
        
        resources = {"res1": Mock()}
        assert allocator.can_allocate(resources, constraints)
    
    def test_pooled_resource_allocator(self):
        """Test PooledResourceAllocator."""
        creation_count = 0
        
        def factory_func(data):
            nonlocal creation_count
            creation_count += 1
            return {"id": creation_count, "data": data}
        
        def reset_func(obj):
            obj["reset"] = True
        
        allocator = PooledResourceAllocator(factory_func, reset_func, pool_size=2)
        
        # First allocation should create new resource
        resource1 = allocator.allocate("test_id", "data1")
        assert resource1["id"] == 1
        assert creation_count == 1
        
        # Return to pool
        allocator.return_to_pool(resource1)
        
        # Next allocation should reuse from pool
        resource2 = allocator.allocate("test_id", "data2")
        assert resource2["id"] == 1  # Same object
        assert resource2["reset"] is True  # Reset function was called
        assert creation_count == 1  # No new creation
        
        # Pool overflow test
        allocator.return_to_pool({"id": 2})
        allocator.return_to_pool({"id": 3})
        allocator.return_to_pool({"id": 4})  # Should be dropped (pool_size=2)
        
        assert len(allocator._pool) == 2


class TestResourceManager:
    """Test cases for ResourceManager."""
    
    def test_manager_initialization(self):
        """Test ResourceManager initialization."""
        constraints = ResourceConstraints(max_resources=5)
        manager = ResourceManager("test_manager", constraints, cleanup_interval=30.0)
        
        assert manager.name == "test_manager"
        assert manager.constraints == constraints
        assert manager.cleanup_interval == 30.0
        assert len(manager._resources) == 0
    
    def test_resource_allocation_and_retrieval(self):
        """Test resource allocation and retrieval."""
        manager = ResourceManager("test")
        
        def create_resource(data):
            return {"data": data, "created": True}
        
        def cleanup_resource(obj):
            obj["cleaned"] = True
        
        # Allocate resource
        resource_obj = manager.allocate_resource(
            resource_id="test_resource",
            resource_type=ResourceType.MEMORY,
            factory_func=create_resource,
            cleanup_func=cleanup_resource,
            metadata={"category": "test"},
            data="test_data"
        )
        
        assert resource_obj is not None
        assert resource_obj["data"] == "test_data"
        assert resource_obj["created"] is True
        
        # Retrieve existing resource
        retrieved = manager.get_resource("test_resource")
        assert retrieved == resource_obj
        
        # Non-existent resource
        assert manager.get_resource("nonexistent") is None
    
    def test_resource_allocation_with_allocator(self):
        """Test resource allocation using registered allocator."""
        manager = ResourceManager("test")
        
        def factory_func(data):
            return {"allocator_data": data}
        
        allocator = SimpleResourceAllocator(factory_func)
        manager.register_allocator(ResourceType.MEMORY, allocator)
        
        resource_obj = manager.allocate_resource(
            resource_id="allocated_resource",
            resource_type=ResourceType.MEMORY,
            data="allocator_test"
        )
        
        assert resource_obj is not None
        assert resource_obj["allocator_data"] == "allocator_test"
    
    def test_resource_release(self):
        """Test resource release and cleanup."""
        manager = ResourceManager("test")
        cleanup_called = []
        
        def cleanup_func(obj):
            cleanup_called.append(obj)
        
        # Allocate resource
        resource_obj = manager.allocate_resource(
            resource_id="release_test",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "test"},
            cleanup_func=cleanup_func
        )
        
        assert "release_test" in manager._resources
        
        # Release resource
        success = manager.release_resource("release_test")
        assert success
        assert "release_test" not in manager._resources
        assert len(cleanup_called) == 1
        assert cleanup_called[0] == resource_obj
    
    def test_resource_constraints_enforcement(self):
        """Test resource allocation constraint enforcement."""
        constraints = ResourceConstraints(max_resources=2)
        manager = ResourceManager("constrained", constraints)
        
        # Allocate up to limit
        resource1 = manager.allocate_resource(
            resource_id="res1",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"id": 1}
        )
        resource2 = manager.allocate_resource(
            resource_id="res2", 
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"id": 2}
        )
        
        assert resource1 is not None
        assert resource2 is not None
        
        # Third allocation should fail
        resource3 = manager.allocate_resource(
            resource_id="res3",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"id": 3}
        )
        assert resource3 is None
        
        # Metrics should reflect failed allocation
        stats = manager.get_resource_stats()
        assert stats["failed_allocations"] == 1
    
    def test_mark_resource_idle(self):
        """Test marking resources as idle."""
        manager = ResourceManager("test")
        
        manager.allocate_resource(
            resource_id="idle_test",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "test"}
        )
        
        # Access resource to mark as in use
        manager.get_resource("idle_test")
        resource = manager._resources["idle_test"]
        assert resource.state == ResourceState.IN_USE
        
        # Mark as idle
        manager.mark_resource_idle("idle_test")
        assert resource.state == ResourceState.IDLE
    
    @pytest.mark.asyncio
    async def test_async_cleanup(self):
        """Test async resource cleanup."""
        manager = ResourceManager("async_test")
        async_cleanup_called = []
        
        async def async_cleanup_func(obj):
            await asyncio.sleep(0.01)  # Simulate async work
            async_cleanup_called.append(obj)
        
        # Allocate resource with async cleanup
        resource_obj = manager.allocate_resource(
            resource_id="async_cleanup_test",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "async_test"},
            async_cleanup_func=async_cleanup_func
        )
        
        # Release resource (should trigger async cleanup)
        success = manager.release_resource("async_cleanup_test")
        assert success
        
        # Wait for async cleanup to complete
        await asyncio.sleep(0.05)
        
        # Cleanup should have been called
        assert len(async_cleanup_called) == 1
        assert async_cleanup_called[0] == resource_obj
    
    def test_cleanup_callbacks(self):
        """Test cleanup callbacks."""
        manager = ResourceManager("callback_test")
        callback_calls = []
        
        def cleanup_callback(resource):
            callback_calls.append(resource.resource_id)
        
        manager.add_cleanup_callback(cleanup_callback)
        
        # Allocate and release resource
        manager.allocate_resource(
            resource_id="callback_resource",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "test"}
        )
        
        manager.release_resource("callback_resource")
        
        assert len(callback_calls) == 1
        assert callback_calls[0] == "callback_resource"
    
    @pytest.mark.asyncio
    async def test_cleanup_all_resources(self):
        """Test cleanup of all resources."""
        manager = ResourceManager("cleanup_all_test")
        cleanup_calls = []
        
        def cleanup_func(obj):
            cleanup_calls.append(obj["id"])
        
        # Allocate multiple resources
        for i in range(3):
            manager.allocate_resource(
                resource_id=f"resource_{i}",
                resource_type=ResourceType.MEMORY,
                factory_func=lambda i=i: {"id": i},
                cleanup_func=cleanup_func
            )
        
        assert len(manager._resources) == 3
        
        # Cleanup all
        cleaned = await manager.cleanup_all_resources()
        assert cleaned == 3
        assert len(manager._resources) == 0
        assert len(cleanup_calls) == 3
    
    def test_resource_statistics(self):
        """Test resource statistics collection."""
        manager = ResourceManager("stats_test")
        
        # Allocate resources of different types
        manager.allocate_resource(
            resource_id="mem1",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"type": "memory"}
        )
        manager.allocate_resource(
            resource_id="file1",
            resource_type=ResourceType.FILE,
            factory_func=lambda: {"type": "file"}
        )
        manager.allocate_resource(
            resource_id="mem2",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"type": "memory"}
        )
        
        # Access one resource to change state
        manager.get_resource("mem1")
        
        stats = manager.get_resource_stats()
        
        assert stats["manager_name"] == "stats_test"
        assert stats["total_resources"] == 3
        assert stats["resources_by_type"]["memory"] == 2
        assert stats["resources_by_type"]["file"] == 1
        assert stats["resources_by_state"]["in_use"] == 1
        assert stats["resources_by_state"]["allocated"] == 2
        assert stats["allocation_count"] == 3
    
    def test_resource_details(self):
        """Test detailed resource information retrieval."""
        manager = ResourceManager("details_test")
        
        manager.allocate_resource(
            resource_id="detail_resource",
            resource_type=ResourceType.NETWORK,
            factory_func=lambda: {"connection": "active"},
            metadata={"host": "localhost", "port": 8080}
        )
        
        details = manager.get_resource_details()
        assert len(details) == 1
        
        resource_detail = details[0]
        assert resource_detail["resource_id"] == "detail_resource"
        assert resource_detail["resource_type"] == "network"
        assert resource_detail["metadata"]["host"] == "localhost"
        assert resource_detail["metadata"]["port"] == 8080
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test ResourceManager as async context manager."""
        async with ResourceManager("context_test") as manager:
            resource_obj = manager.allocate_resource(
                resource_id="context_resource",
                resource_type=ResourceType.MEMORY,
                factory_func=lambda: {"data": "context_test"}
            )
            assert resource_obj is not None
            assert len(manager._resources) == 1
        
        # Resources should be cleaned up after context exit
        assert len(manager._resources) == 0


class TestGlobalResourceManagement:
    """Test cases for global resource management functions."""
    
    def test_get_resource_manager(self):
        """Test global resource manager retrieval."""
        manager1 = get_resource_manager("test_global")
        manager2 = get_resource_manager("test_global")
        
        # Should return the same instance
        assert manager1 is manager2
        assert manager1.name == "test_global"
    
    def test_register_resource_manager(self):
        """Test resource manager registration."""
        custom_manager = ResourceManager("custom")
        register_resource_manager("custom_global", custom_manager)
        
        retrieved = get_resource_manager("custom_global")
        assert retrieved is custom_manager
    
    @pytest.mark.asyncio
    async def test_cleanup_all_managers(self):
        """Test cleanup of all registered managers."""
        # Create some managers with resources
        manager1 = get_resource_manager("cleanup_test1")
        manager2 = get_resource_manager("cleanup_test2")
        
        manager1.allocate_resource(
            resource_id="res1",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "test1"}
        )
        manager2.allocate_resource(
            resource_id="res2",
            resource_type=ResourceType.MEMORY,
            factory_func=lambda: {"data": "test2"}
        )
        
        assert len(manager1._resources) == 1
        assert len(manager2._resources) == 1
        
        # Cleanup all managers
        await cleanup_all_managers()
        
        # All resources should be cleaned up
        assert len(manager1._resources) == 0
        assert len(manager2._resources) == 0


class TestManagedResourceDecorator:
    """Test cases for the managed_resource decorator."""
    
    def test_managed_resource_decorator(self):
        """Test managed_resource decorator functionality."""
        cleanup_calls = []
        
        def cleanup_func(obj):
            cleanup_calls.append(obj)
        
        @managed_resource(ResourceType.MEMORY, cleanup_func, "decorator_test")
        def create_test_resource(data):
            return {"decorated_data": data}
        
        # Create resource using decorated function
        result = create_test_resource("test_input")
        assert result is not None
        assert result["decorated_data"] == "test_input"
        
        # Check that resource was registered in manager
        manager = get_resource_manager("decorator_test")
        assert len(manager._resources) == 1