"""Monotonic pipeline progress labels (no fixed step total)."""

from __future__ import annotations


class PipelineProgress:
    """
    Print pipeline steps without claiming a final count.

    Refinement loops and curator retries add steps at runtime.
    """

    def __init__(self, *, prefix: str = "Pipeline") -> None:
        self._n = 0
        self._prefix = prefix

    @property
    def count(self) -> int:
        return self._n

    def step(self, agent: str, *, detail: str = "") -> int:
        self._n += 1
        suffix = f" · {detail}" if detail else ""
        print(f"{self._prefix} · step {self._n}: {agent}{suffix}")
        return self._n
