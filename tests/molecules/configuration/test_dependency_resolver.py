"""
Tests for the dependency resolver module.
"""

import pytest
from typing import Type, Any

from aider_mcp_server.molecules.configuration.dependency_resolver import (
    DependencyResolver,
    DependencyGraph,
    DependencyType,
)


class MockLogger:
    """Mock logger for testing."""
    
    def __init__(self):
        self.messages = []
    
    def verbose(self, message: str):
        self.messages.append(f"VERBOSE: {message}")
    
    def warning(self, message: str):
        self.messages.append(f"WARNING: {message}")


class SimpleService:
    """Simple service for testing."""
    
    def __init__(self):
        pass


class ServiceWithDependency:
    """Service with a single dependency."""
    
    def __init__(self, simple: SimpleService):
        self.simple = simple


class ServiceWithOptionalDependency:
    """Service with optional dependency."""
    
    def __init__(self, simple: SimpleService = None):
        self.simple = simple


class CircularA:
    """Service with circular dependency to CircularB."""
    
    def __init__(self, b: 'CircularB'):
        self.b = b


class CircularB:
    """Service with circular dependency to CircularA."""
    
    def __init__(self, a: CircularA):
        self.a = a


class ComplexService:
    """Service with multiple dependencies."""
    
    def __init__(self, simple: SimpleService, with_dep: ServiceWithDependency, optional: ServiceWithOptionalDependency = None):
        self.simple = simple
        self.with_dep = with_dep
        self.optional = optional


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return MockLogger()


@pytest.fixture
def resolver(mock_logger):
    """Create a dependency resolver with mock logger."""
    return DependencyResolver(logger=mock_logger)


class TestDependencyResolver:
    """Test the DependencyResolver class."""
    
    def test_analyze_simple_service(self, resolver):
        """Test analyzing a service with no dependencies."""
        dependencies = resolver.analyze_dependencies(SimpleService)
        assert len(dependencies) == 0
    
    def test_analyze_service_with_dependency(self, resolver):
        """Test analyzing a service with one dependency."""
        dependencies = resolver.analyze_dependencies(ServiceWithDependency)
        assert len(dependencies) == 1
        
        dep = dependencies[0]
        assert dep.parameter_name == 'simple'
        assert dep.parameter_type == SimpleService
        assert not dep.is_optional
        assert dep.dependency_type == DependencyType.CONSTRUCTOR
    
    def test_analyze_service_with_optional_dependency(self, resolver):
        """Test analyzing a service with optional dependency."""
        dependencies = resolver.analyze_dependencies(ServiceWithOptionalDependency)
        assert len(dependencies) == 1
        
        dep = dependencies[0]
        assert dep.parameter_name == 'simple'
        assert dep.parameter_type == SimpleService
        assert dep.is_optional
        assert dep.default_value is None
    
    def test_analyze_complex_service(self, resolver):
        """Test analyzing a service with multiple dependencies."""
        dependencies = resolver.analyze_dependencies(ComplexService)
        assert len(dependencies) == 3
        
        # Check required dependencies
        required_deps = [d for d in dependencies if not d.is_optional]
        assert len(required_deps) == 2
        
        # Check optional dependencies
        optional_deps = [d for d in dependencies if d.is_optional]
        assert len(optional_deps) == 1
    
    def test_dependency_caching(self, resolver):
        """Test that dependency analysis is cached."""
        # First call
        deps1 = resolver.analyze_dependencies(ServiceWithDependency)
        
        # Second call should return cached result
        deps2 = resolver.analyze_dependencies(ServiceWithDependency)
        
        assert deps1 is deps2  # Same object reference
    
    def test_clear_cache(self, resolver):
        """Test clearing the dependency cache."""
        # Analyze to populate cache
        resolver.analyze_dependencies(ServiceWithDependency)
        assert len(resolver._dependency_cache) == 1
        
        # Clear cache
        resolver.clear_cache()
        assert len(resolver._dependency_cache) == 0
    
    def test_get_dependency_summary(self, resolver):
        """Test getting dependency summary."""
        summary = resolver.get_dependency_summary(ComplexService)
        
        assert summary['class_name'] == 'ComplexService'
        assert summary['total_dependencies'] == 3
        assert summary['required_dependencies'] == 2
        assert summary['optional_dependencies'] == 1
        assert 'SimpleService' in summary['dependency_types']
        assert 'ServiceWithDependency' in summary['dependency_types']


class TestDependencyGraph:
    """Test the DependencyGraph class."""
    
    def test_empty_graph(self):
        """Test empty dependency graph."""
        graph = DependencyGraph()
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0
    
    def test_add_nodes(self):
        """Test adding nodes to graph."""
        graph = DependencyGraph()
        graph.add_node(SimpleService)
        graph.add_node(ServiceWithDependency)
        
        assert len(graph.nodes) == 2
        assert SimpleService in graph.nodes
        assert ServiceWithDependency in graph.nodes
    
    def test_add_edges(self):
        """Test adding edges to graph."""
        graph = DependencyGraph()
        graph.add_edge(ServiceWithDependency, SimpleService)
        
        assert len(graph.nodes) == 2
        assert SimpleService in graph.edges[ServiceWithDependency]
    
    def test_has_cycle_false(self):
        """Test cycle detection on acyclic graph."""
        graph = DependencyGraph()
        graph.add_edge(ServiceWithDependency, SimpleService)
        graph.add_edge(ComplexService, ServiceWithDependency)
        
        assert not graph.has_cycle()
    
    def test_has_cycle_true(self):
        """Test cycle detection on cyclic graph."""
        graph = DependencyGraph()
        graph.add_edge(CircularA, CircularB)
        graph.add_edge(CircularB, CircularA)
        
        assert graph.has_cycle()
    
    def test_find_cycles(self):
        """Test finding specific cycles."""
        graph = DependencyGraph()
        graph.add_edge(CircularA, CircularB)
        graph.add_edge(CircularB, CircularA)
        
        cycles = graph.find_cycles()
        assert len(cycles) > 0
        
        # Should find the circular dependency
        cycle_types = set()
        for cycle in cycles:
            cycle_types.update(cycle)
        
        assert CircularA in cycle_types
        assert CircularB in cycle_types
    
    def test_topological_sort(self):
        """Test topological sorting."""
        graph = DependencyGraph()
        graph.add_edge(ComplexService, ServiceWithDependency)
        graph.add_edge(ServiceWithDependency, SimpleService)
        
        sorted_nodes = graph.topological_sort()
        
        # SimpleService should come before ServiceWithDependency
        simple_index = sorted_nodes.index(SimpleService)
        with_dep_index = sorted_nodes.index(ServiceWithDependency)
        complex_index = sorted_nodes.index(ComplexService)
        
        assert simple_index < with_dep_index
        assert with_dep_index < complex_index
    
    def test_topological_sort_with_cycle(self):
        """Test topological sort fails on cyclic graph."""
        graph = DependencyGraph()
        graph.add_edge(CircularA, CircularB)
        graph.add_edge(CircularB, CircularA)
        
        with pytest.raises(ValueError, match="Cannot perform topological sort"):
            graph.topological_sort()


class TestDependencyResolverAdvanced:
    """Test advanced dependency resolver features."""
    
    def test_build_dependency_graph(self, resolver):
        """Test building complete dependency graph."""
        graph = resolver.build_dependency_graph([ComplexService])
        
        # Should include all dependencies
        assert ComplexService in graph.nodes
        assert ServiceWithDependency in graph.nodes
        assert SimpleService in graph.nodes
        assert ServiceWithOptionalDependency in graph.nodes
    
    def test_detect_circular_dependencies(self, resolver):
        """Test circular dependency detection."""
        cycles = resolver.detect_circular_dependencies([CircularA, CircularB])
        
        assert len(cycles) > 0
        
        # Should detect the circular dependency
        found_circular = False
        for cycle in cycles:
            if CircularA in cycle and CircularB in cycle:
                found_circular = True
                break
        
        assert found_circular
    
    def test_get_resolution_order(self, resolver):
        """Test getting resolution order."""
        order = resolver.get_resolution_order([ComplexService])
        
        # SimpleService should come before its dependents
        simple_index = order.index(SimpleService)
        with_dep_index = order.index(ServiceWithDependency)
        complex_index = order.index(ComplexService)
        
        assert simple_index < with_dep_index
        assert with_dep_index < complex_index
    
    def test_get_resolution_order_with_cycle(self, resolver):
        """Test resolution order fails with circular dependencies."""
        with pytest.raises(ValueError, match="Circular dependencies detected"):
            resolver.get_resolution_order([CircularA, CircularB])
    
    def test_can_resolve(self, resolver):
        """Test checking if a type can be resolved."""
        available_types = {SimpleService, ServiceWithDependency}
        
        # ComplexService requires ServiceWithOptionalDependency which is not available
        # But ServiceWithOptionalDependency is optional, so it should be resolvable
        assert resolver.can_resolve(ComplexService, available_types)
        
        # CircularA requires CircularB which is not available
        assert not resolver.can_resolve(CircularA, {CircularA})
    
    def test_get_missing_dependencies(self, resolver):
        """Test getting missing dependencies."""
        available_types = {SimpleService}
        
        missing = resolver.get_missing_dependencies(ComplexService, available_types)
        
        # Should be missing ServiceWithDependency (required)
        # ServiceWithOptionalDependency is optional so not missing
        assert len(missing) == 1
        assert missing[0].parameter_type == ServiceWithDependency
    
    def test_resolve_constructor_args(self, resolver):
        """Test resolving constructor arguments."""
        def mock_resolver(service_type: Type[Any]) -> Any:
            if service_type == SimpleService:
                return SimpleService()
            elif service_type == ServiceWithDependency:
                return ServiceWithDependency(SimpleService())
            raise ValueError(f"Cannot resolve {service_type}")
        
        args = resolver.resolve_constructor_args(ComplexService, mock_resolver)
        
        assert 'simple' in args
        assert 'with_dep' in args
        assert isinstance(args['simple'], SimpleService)
        assert isinstance(args['with_dep'], ServiceWithDependency)
        # 'optional' should not be in args (will use default None)
    
    def test_resolve_constructor_args_circular_dependency(self, resolver):
        """Test constructor arg resolution detects circular dependencies."""
        def mock_resolver(service_type: Type[Any]) -> Any:
            # This will cause infinite recursion without circular detection
            return resolver.resolve_constructor_args(service_type, mock_resolver)
        
        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.resolve_constructor_args(CircularA, mock_resolver)
    
    def test_resolve_constructor_args_missing_required(self, resolver):
        """Test constructor arg resolution with missing required dependency."""
        def mock_resolver(service_type: Type[Any]) -> Any:
            if service_type == SimpleService:
                return SimpleService()
            raise ValueError(f"Cannot resolve {service_type}")
        
        with pytest.raises(ValueError, match="Failed to resolve required dependency"):
            resolver.resolve_constructor_args(ComplexService, mock_resolver)
    
    def test_resolve_constructor_args_optional_fallback(self, resolver):
        """Test constructor arg resolution with optional dependency fallback."""
        def mock_resolver(service_type: Type[Any]) -> Any:
            if service_type == SimpleService:
                return SimpleService()
            elif service_type == ServiceWithDependency:
                return ServiceWithDependency(SimpleService())
            elif service_type == ServiceWithOptionalDependency:
                raise ValueError("Cannot resolve optional dependency")
            raise ValueError(f"Cannot resolve {service_type}")
        
        args = resolver.resolve_constructor_args(ComplexService, mock_resolver)
        
        # Should resolve required dependencies and skip optional one that failed
        assert 'simple' in args
        assert 'with_dep' in args
        assert 'optional' not in args  # Should use default None