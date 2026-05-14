"""
DAG validation and topological resolution for multi-spec tasks.
Produces execution layers: specs in the same layer can run concurrently.
"""

from __future__ import annotations
from collections import defaultdict, deque
from .task_models import Task, TaskSpec


class CyclicDependencyError(ValueError):
    pass


class DAGResolver:
    """
    Validates and resolves a Task's dependency graph via Kahn's algorithm.
    Specs in the same layer share no interdependencies — safe to run in parallel.
    """

    def validate(self, task: Task) -> None:
        known_ids = {ts.spec.id for ts in task.specs}
        for ts in task.specs:
            for dep in ts.depends_on:
                if dep not in known_ids:
                    raise ValueError(
                        f"Spec '{ts.spec.id}' depends on unknown spec '{dep}'"
                    )
        if self._has_cycle(task):
            raise CyclicDependencyError(
                f"Task '{task.id}' contains a dependency cycle"
            )

    def execution_layers(self, task: Task) -> list[list[TaskSpec]]:
        """
        Topological sort. Returns ordered groups of specs.
        Specs within a group are independent and can run concurrently.
        """
        in_degree: dict[str, int] = {ts.spec.id: 0 for ts in task.specs}
        dependents: dict[str, list[str]] = defaultdict(list)

        for ts in task.specs:
            for dep in ts.depends_on:
                in_degree[ts.spec.id] += 1
                dependents[dep].append(ts.spec.id)

        by_id = {ts.spec.id: ts for ts in task.specs}
        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
        layers: list[list[TaskSpec]] = []

        while queue:
            layer = []
            for _ in range(len(queue)):
                sid = queue.popleft()
                layer.append(by_id[sid])
                for child in dependents[sid]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        queue.append(child)
            layers.append(layer)

        return layers

    def _has_cycle(self, task: Task) -> bool:
        adj: dict[str, list[str]] = defaultdict(list)
        for ts in task.specs:
            for dep in ts.depends_on:
                adj[dep].append(ts.spec.id)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbour in adj[node]:
                if neighbour not in visited and dfs(neighbour):
                    return True
                if neighbour in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        return any(
            dfs(ts.spec.id)
            for ts in task.specs
            if ts.spec.id not in visited
        )
