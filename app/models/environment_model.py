"""
KangPaket — Environment & Variable dataclasses.
"""
from dataclasses import dataclass, field
import uuid


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Variable:
    key: str
    value: str = ""
    secret: bool = False
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "secret": self.secret,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Variable":
        return cls(
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "vars": [v.to_dict() for v in self.vars],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Environment":
        return cls(
            id=data.get("id") or _new_uuid(),
            name=str(data.get("name", "Untitled")),
            vars=[Variable.from_dict(v) for v in data.get("vars", []) if isinstance(v, dict)],
        )
