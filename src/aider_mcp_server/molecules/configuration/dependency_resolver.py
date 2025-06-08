"""
Advanced dependency resolution module for the aider-mcp-server.

This module provides sophisticated dependency analysis and resolution capabilities,
including circular dependency detection, constructor injection, and dependency
graph traversal.
"""

import inspect
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar, get_type_hints

from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

T = TypeVar("T")


class DependencyType(Enum):
    """Types of dependencies that can be resolved."""

    CONSTRUCTOR = auto()
    FACTORY = auto()
    PROPERTY = auto()
    METHOD = auto()


@dataclass
class DependencyInfo:
    """Information about a dependency."""

    parameter_name: str
    parameter_type: Type[Any]
    is_optional: bool
    default_value: Any
    dependency_type: DependencyType
    source_callable: Optional[Callable[..., Any]] = None


class DependencyGraph:
    """Represents a dependency graph for analysis."""

    def __init__(self) -> None:
        self.nodes: Set[Type[Any]] = set()
        self.edges: Dict[Type[Any], Set[Type[Any]]] = {}
        self.dependencies: Dict[Type[Any], List[DependencyInfo]] = {}

    def add_node(self, node_type: Type[Any]) -> None:
        """Add a node to the dependency graph."""
        self.nodes.add(node_type)
        if node_type not in self.edges:
            self.edges[node_type] = set()

    def add_edge(self, from_type: Type[Any], to_type: Type[Any]) -> None:
        """Add a dependency edge from one type to another."""
        self.add_node(from_type)
        self.add_node(to_type)
        self.edges[from_type].add(to_type)

    def has_cycle(self) -> bool:
        """Check if the dependency graph has cycles."""
        visited = set()
        rec_stack = set()

        def dfs(node: Type[Any]) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in self.edges.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in self.nodes:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    def find_cycles(self) -> List[List[Type[Any]]]:
        """Find all cycles in the dependency graph."""
        cycles = []
        visited = set()
        rec_stack: List[Type[Any]] = []

        def dfs(node: Type[Any], path: List[Type[Any]]) -> None:
            if node in rec_stack:
                # Found a cycle
                cycle_start = rec_stack.index(node)
                cycle = rec_stack[cycle_start:] + [node]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.append(node)

            for neighbor in self.edges.get(node, set()):
                dfs(neighbor, path + [neighbor])

            rec_stack.remove(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node, [node])

        return cycles

    def topological_sort(self) -> List[Type[Any]]:
        """Return a topological ordering of the dependency graph."""
        if self.has_cycle():
            raise ValueError("Cannot perform topological sort on a graph with cycles")

        in_degree = dict.fromkeys(self.nodes, 0)
        for node in self.nodes:
            for neighbor in self.edges.get(node, set()):
                in_degree[neighbor] += 1

        queue = [node for node in self.nodes if in_degree[node] == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in self.edges.get(node, set()):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Ensure all nodes are included
        if len(result) != len(self.nodes):
            raise ValueError("Graph contains cycles or is disconnected")

        # Reverse the result for dependency resolution order
        # Dependencies should be resolved before dependents
        return list(reversed(result))


class DependencyResolver:
    """
    Advanced dependency resolver with graph analysis and circular dependency detection.

    This resolver can analyze complex dependency graphs, detect circular dependencies,
    and provide detailed information about dependency relationships.
    """

    def __init__(self, logger: Optional[LoggerProtocol] = None):
        self.logger = logger
        self._dependency_cache: Dict[Type[Any], List[DependencyInfo]] = {}
        self._resolution_cache: Dict[Type[Any], Any] = {}
        self._active_resolutions: Set[Type[Any]] = set()

    def analyze_dependencies(self, cls: Type[T]) -> List[DependencyInfo]:
        """
        Analyze the dependencies of a class based on its constructor and methods.

        Args:
            cls: The class to analyze

        Returns:
            List of dependency information objects
        """
        if cls in self._dependency_cache:
            return self._dependency_cache[cls]

        dependencies = []

        # Analyze constructor dependencies
        if hasattr(cls, "__init__"):
            constructor_deps = self._analyze_callable_dependencies(cls.__init__, DependencyType.CONSTRUCTOR)
            dependencies.extend(constructor_deps)

        # Cache the results
        self._dependency_cache[cls] = dependencies

        if self.logger:
            self.logger.verbose(f"Analyzed dependencies for {cls.__name__}: {len(dependencies)} found")

        return dependencies

    def _analyze_callable_dependencies(
        self, callable_obj: Callable[..., Any], dep_type: DependencyType
    ) -> List[DependencyInfo]:
        """Analyze dependencies for a specific callable."""
        dependencies = []

        # Get type hints to resolve string annotations
        try:
            type_hints = get_type_hints(callable_obj)
        except NameError:
            # Fall back to raw signature if we can't resolve type hints
            type_hints = {}
            signature = inspect.signature(callable_obj)
            for param_name, param in signature.parameters.items():
                if param.annotation is not inspect.Parameter.empty:
                    type_hints[param_name] = param.annotation

        signature = inspect.signature(callable_obj)

        for param_name, param in signature.parameters.items():
            # Skip self parameter for methods
            if param_name == "self":
                continue

            # Skip kwargs and varargs parameters
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue

            # Get parameter type from type hints
            param_type = type_hints.get(param_name)
            if param_type is None:
                # Skip parameters without type annotations
                continue

            # Check if parameter is optional
            is_optional = param.default is not inspect.Parameter.empty
            default_value = param.default if is_optional else None

            dependency_info = DependencyInfo(
                parameter_name=param_name,
                parameter_type=param_type,
                is_optional=is_optional,
                default_value=default_value,
                dependency_type=dep_type,
                source_callable=callable_obj,
            )

            dependencies.append(dependency_info)

        return dependencies

    def build_dependency_graph(self, root_types: List[Type[Any]]) -> DependencyGraph:
        """
        Build a complete dependency graph starting from root types.

        Args:
            root_types: List of root types to start the analysis from

        Returns:
            Complete dependency graph
        """
        graph = DependencyGraph()
        visited = set()

        def visit_type(cls: Type[Any]) -> None:
            if cls in visited:
                return

            visited.add(cls)
            graph.add_node(cls)

            dependencies = self.analyze_dependencies(cls)
            graph.dependencies[cls] = dependencies

            for dep_info in dependencies:
                dep_type = dep_info.parameter_type

                # Handle generic types and special cases
                if hasattr(dep_type, "__origin__"):
                    # Skip generic types like List[str], Dict[str, int], etc.
                    continue

                # Skip built-in types
                if dep_type in (str, int, float, bool, bytes):
                    continue

                graph.add_edge(cls, dep_type)
                visit_type(dep_type)

        for root_type in root_types:
            visit_type(root_type)

        if self.logger:
            self.logger.verbose(f"Built dependency graph with {len(graph.nodes)} nodes")

        return graph

    def detect_circular_dependencies(self, root_types: List[Type[Any]]) -> List[List[Type[Any]]]:
        """
        Detect circular dependencies in a set of types.

        Args:
            root_types: List of types to analyze

        Returns:
            List of circular dependency chains
        """
        graph = self.build_dependency_graph(root_types)
        cycles = graph.find_cycles()

        if cycles and self.logger:
            self.logger.warning(f"Detected {len(cycles)} circular dependency cycles")
            for i, cycle in enumerate(cycles):
                cycle_names = [getattr(t, "__name__", str(t)) for t in cycle]
                self.logger.warning(f"Cycle {i + 1}: {' -> '.join(cycle_names)}")

        return cycles

    def get_resolution_order(self, root_types: List[Type[Any]]) -> List[Type[Any]]:
        """
        Get the order in which types should be resolved to satisfy dependencies.

        Args:
            root_types: List of types to resolve

        Returns:
            List of types in resolution order

        Raises:
            ValueError: If circular dependencies are detected
        """
        graph = self.build_dependency_graph(root_types)

        if graph.has_cycle():
            cycles = graph.find_cycles()
            cycle_descriptions = []
            for cycle in cycles:
                cycle_names = [getattr(t, "__name__", str(t)) for t in cycle]
                cycle_descriptions.append(" -> ".join(cycle_names))

            raise ValueError(f"Circular dependencies detected: {'; '.join(cycle_descriptions)}")

        return graph.topological_sort()

    def can_resolve(self, cls: Type[T], available_types: Set[Type[Any]]) -> bool:
        """
        Check if a type can be resolved given a set of available types.

        Args:
            cls: Type to check
            available_types: Set of types that are available for injection

        Returns:
            True if the type can be resolved
        """
        dependencies = self.analyze_dependencies(cls)

        for dep_info in dependencies:
            if not dep_info.is_optional:
                if dep_info.parameter_type not in available_types:
                    return False

        return True

    def get_missing_dependencies(self, cls: Type[T], available_types: Set[Type[Any]]) -> List[DependencyInfo]:
        """
        Get list of missing dependencies for a type.

        Args:
            cls: Type to check
            available_types: Set of types that are available

        Returns:
            List of missing dependency information
        """
        dependencies = self.analyze_dependencies(cls)
        missing = []

        for dep_info in dependencies:
            if not dep_info.is_optional:
                if dep_info.parameter_type not in available_types:
                    missing.append(dep_info)

        return missing

    def _check_circular_dependency(self, dep_info: DependencyInfo) -> None:
        """Check for circular dependencies and raise error if found."""
        if dep_info.parameter_type in self._active_resolutions:
            chain = list(self._active_resolutions) + [dep_info.parameter_type]
            chain_names = [getattr(t, "__name__", str(t)) for t in chain]
            raise ValueError(f"Circular dependency: {' -> '.join(chain_names)}")

    def _handle_optional_dependency_error(self, dep_info: DependencyInfo, args: Dict[str, Any]) -> None:
        """Handle errors for optional dependencies."""
        if dep_info.default_value is not inspect.Parameter.empty:
            return  # Skip adding to args, will use default
        else:
            args[dep_info.parameter_name] = None

    def _handle_required_dependency_error(self, dep_info: DependencyInfo, cls: Type[T], e: Exception) -> None:
        """Handle errors for required dependencies."""
        param_type_name = getattr(dep_info.parameter_type, "__name__", str(dep_info.parameter_type))
        raise ValueError(
            f"Failed to resolve required dependency {dep_info.parameter_name} "
            f"of type {param_type_name} for {cls.__name__}"
        ) from e

    def _resolve_single_dependency(
        self, dep_info: DependencyInfo, resolver_func: Callable[[Type[Any]], Any], cls: Type[T], args: Dict[str, Any]
    ) -> None:
        """Resolve a single dependency."""
        try:
            self._check_circular_dependency(dep_info)

            self._active_resolutions.add(dep_info.parameter_type)
            try:
                resolved_value = resolver_func(dep_info.parameter_type)
                args[dep_info.parameter_name] = resolved_value
            finally:
                self._active_resolutions.remove(dep_info.parameter_type)

        except ValueError as e:
            # Check if this is a circular dependency error
            if "Circular dependency" in str(e):
                raise

            if dep_info.is_optional:
                self._handle_optional_dependency_error(dep_info, args)
            else:
                self._handle_required_dependency_error(dep_info, cls, e)
        except Exception as e:
            if dep_info.is_optional:
                self._handle_optional_dependency_error(dep_info, args)
            else:
                self._handle_required_dependency_error(dep_info, cls, e)

    def resolve_constructor_args(self, cls: Type[T], resolver_func: Callable[[Type[Any]], Any]) -> Dict[str, Any]:
        """
        Resolve constructor arguments for a class.

        Args:
            cls: Class to resolve arguments for
            resolver_func: Function to resolve individual dependencies

        Returns:
            Dictionary of resolved constructor arguments
        """
        dependencies = self.analyze_dependencies(cls)
        args: Dict[str, Any] = {}

        for dep_info in dependencies:
            if dep_info.dependency_type == DependencyType.CONSTRUCTOR:
                self._resolve_single_dependency(dep_info, resolver_func, cls, args)

        return args

    def clear_cache(self) -> None:
        """Clear all cached dependency analysis results."""
        self._dependency_cache.clear()
        self._resolution_cache.clear()

        if self.logger:
            self.logger.verbose("Cleared dependency resolver cache")

    def get_dependency_summary(self, cls: Type[T]) -> Dict[str, Any]:
        """
        Get a summary of dependencies for a class.

        Args:
            cls: Class to analyze

        Returns:
            Dictionary containing dependency summary information
        """
        dependencies = self.analyze_dependencies(cls)

        return {
            "class_name": cls.__name__,
            "total_dependencies": len(dependencies),
            "required_dependencies": len([d for d in dependencies if not d.is_optional]),
            "optional_dependencies": len([d for d in dependencies if d.is_optional]),
            "dependency_types": list({d.parameter_type.__name__ for d in dependencies}),
            "dependencies": [
                {
                    "name": d.parameter_name,
                    "type": d.parameter_type.__name__,
                    "optional": d.is_optional,
                    "dependency_type": d.dependency_type.name,
                }
                for d in dependencies
            ],
        }
