"""
KangPaket — ResponseResult dataclass.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ResponseResult:
    status_code: int = 0
    status_text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    elapsed_ms: float = 0.0
    size_bytes: int = 0
    timestamp: str = field(default_factory=_now_iso)
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def size_human(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        return f"{self.size_bytes / (1024 * 1024):.1f} MB"

    @property
    def elapsed_human(self) -> str:
        if self.elapsed_ms < 1000:
            return f"{self.elapsed_ms:.0f} ms"
        return f"{self.elapsed_ms / 1000:.2f} s"
