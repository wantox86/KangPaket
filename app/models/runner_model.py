"""
KangPaket — Runner dataclasses.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class RunnerConfig:
    name: str
    profile_ids: list[str] = field(default_factory=list)
    iteration_count: int = 1
    delay_between_ms: int = 0
    stop_on_failure: bool = False
    run_mode: str = "sequential"   # "sequential" | "parallel"
    id: str = field(default_factory=_new_uuid)
    created_at: str = field(default_factory=_now_iso)


@dataclass
class RunItemResult:
    profile_id: str
    profile_name: str
    iteration: int
    status: str                         # "success" | "failed" | "error" | "skipped"
    status_code: int | None = None
    elapsed_ms: float | None = None
    size_bytes: int | None = None
    error: str | None = None
    assertion_results: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class RunnerResult:
    config: RunnerConfig
    items: list[RunItemResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total_elapsed_ms: float = 0.0
    finished_at: str = field(default_factory=_now_iso)
