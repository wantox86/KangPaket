"""
KangPaket — RequestProfile dataclass.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class RequestProfile:
    name: str
    url: str
    method: str = "GET"
    collection: str = "Default"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body_type: str = "none"           # none | raw | form-data | x-www-form-urlencoded
    body_content: str = ""            # Raw body string
    body_form: dict[str, str] = field(default_factory=dict)
    auth_type: str = "none"           # none | basic | bearer | api-key
    auth_data: dict[str, str] = field(default_factory=dict)
    timeout: float | None = None      # None = use global default
    follow_redirects: bool = True
    verify_ssl: bool = True
    id: str = field(default_factory=_new_uuid)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "collection": self.collection,
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
            "params": self.params,
            "body_type": self.body_type,
            "body_content": self.body_content,
            "body_form": self.body_form,
            "auth_type": self.auth_type,
            "auth_data": self.auth_data,
            "timeout": self.timeout,
            "follow_redirects": self.follow_redirects,
            "verify_ssl": self.verify_ssl,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RequestProfile":
        return cls(
            id=data.get("id", _new_uuid()),
            name=data.get("name", "Untitled"),
            collection=data.get("collection", "Default"),
            method=data.get("method", "GET"),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            params=data.get("params", {}),
            body_type=data.get("body_type", "none"),
            body_content=data.get("body_content", ""),
            body_form=data.get("body_form", {}),
            auth_type=data.get("auth_type", "none"),
            auth_data=data.get("auth_data", {}),
            timeout=data.get("timeout"),
            follow_redirects=data.get("follow_redirects", True),
            verify_ssl=data.get("verify_ssl", True),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )
