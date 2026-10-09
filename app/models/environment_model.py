"""
KangPaket — Environment & Variable dataclasses.
"""
from dataclasses import dataclass, field
import uuid


def _new_uuid() -> str:
    return str(uuid.uuid4())


_VAR_KEYS = frozenset({"key", "value", "secret", "enabled"})
_ENV_KEYS = frozenset({"id", "name", "vars", "updated_at"})


@dataclass
class Variable:
    key: str
    value: str = ""
    secret: bool = False
    enabled: bool = True
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **self.extra,
            "key": self.key,
            "value": self.value,
            "secret": self.secret,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Variable":
        return cls(
            extra={k: v for k, v in data.items() if k not in _VAR_KEYS},
            key=str(data.get("key", "")),
            value=str(data.get("value", "")),
            secret=bool(data.get("secret", False)),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class Environment:
    name: str
    vars: list[Variable] = field(default_factory=list)
    id: str = field(default_factory=_new_uuid)
    updated_at: int = 0               # unix ms of the last local edit (stamped by EnvironmentManager)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **self.extra,
            "id": self.id,
            "name": self.name,
            "vars": [v.to_dict() for v in self.vars],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Environment":
        try:
            updated_at = int(data.get("updated_at") or 0)
        except (TypeError, ValueError):
            updated_at = 0
        return cls(
            extra={k: v for k, v in data.items() if k not in _ENV_KEYS},
            updated_at=updated_at,
            id=data.get("id") or _new_uuid(),
            name=str(data.get("name", "Untitled")),
            vars=[Variable.from_dict(v) for v in data.get("vars", []) if isinstance(v, dict)],
        )
