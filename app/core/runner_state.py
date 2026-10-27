"""
KangPaket — Runner result counters (pure state, no GUI imports).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunCounters:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    done: int = 0
    total: int = 0

    def reset(self, total: int = 0) -> None:
        self.passed = self.failed = self.errors = self.skipped = self.done = 0
        self.total = total

    def add(self, status: str) -> None:
        self.done += 1
        if status == "success":
            self.passed += 1
        elif status == "failed":
            self.failed += 1
        elif status == "error":
            self.errors += 1
        elif status == "skipped":
            self.skipped += 1
