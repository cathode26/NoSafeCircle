from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CircuitBreaker:
    """Bounded retry policy required by Assignment 6."""

    max_refinements: int = 3
    refinements_used: int = 0

    def can_refine(self) -> bool:
        return self.refinements_used < self.max_refinements

    def record_refinement(self) -> None:
        if not self.can_refine():
            raise RuntimeError("Circuit breaker is already tripped.")
        self.refinements_used += 1

    def status(self) -> dict[str, int | bool]:
        return {
            "max_refinements": self.max_refinements,
            "refinements_used": self.refinements_used,
            "tripped": not self.can_refine(),
        }
