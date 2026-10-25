"""
KangPaket — Mapping between local models and Cloud Sync wire items.

Wire item (push): {"id", "collection"|"name", "client_updated_at", "payload"} or a tombstone
{"id", "deleted": true, "client_updated_at"}. Pull items add "kind", "label", "server_version".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.models.environment_model import Environment, Variable
from app.models.request_model import RequestProfile

PROFILE = "profile"
ENVIRONMENT = "environment"

# Globals is synced as an ordinary environment with this fixed id (same on every device).
GLOBALS_ID = "00000000-0000-4000-8000-000000000001"
GLOBALS_NAME = "Globals"

MAX_PAYLOAD_BYTES = 256 * 1024

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def is_valid_id(item_id: str) -> bool:
    return bool(_UUID_RE.match(item_id))


def iso_to_ms(value: str) -> int:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(1, int(dt.timestamp() * 1000))
    except (ValueError, OverflowError, OSError):
        return int(datetime.now(timezone.utc).timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def content_key(label: str, payload: dict) -> bytes:
    """Same ordering key the server uses to break timestamp ties."""
    return (label + "\0" + dumps(payload)).encode("utf-8")


# ------------------------------------------------------------------
# Profiles
# ------------------------------------------------------------------

def profile_ts(profile: RequestProfile) -> int:
    return iso_to_ms(profile.updated_at)


def profile_payload(profile: RequestProfile) -> dict:
    payload = profile.to_dict()
    payload["updated_at"] = ms_to_iso(profile_ts(profile))
    return payload


def profile_to_wire(profile: RequestProfile) -> dict:
    return {
        "id": profile.id,
        "collection": profile.collection,
        "client_updated_at": profile_ts(profile),
        "payload": profile_payload(profile),
    }


def profile_from_wire(item: dict) -> RequestProfile:
    payload = dict(item["payload"])
    payload["id"] = item["id"]
    if "collection" not in payload and item.get("label"):
        payload["collection"] = item["label"]
    profile = RequestProfile.from_dict(payload)
    profile.updated_at = ms_to_iso(item["client_updated_at"])
    return profile


# ------------------------------------------------------------------
# Environments (and Globals)
# ------------------------------------------------------------------

def environment_payload(env: Environment) -> dict:
    return env.to_dict()


def environment_to_wire(env: Environment) -> dict:
    return {
        "id": env.id,
        "name": env.name,
        "client_updated_at": env.updated_at,
        "payload": environment_payload(env),
    }


def globals_as_environment(variables: list[Variable], updated_at: int) -> Environment:
    return Environment(name=GLOBALS_NAME, vars=variables, id=GLOBALS_ID, updated_at=updated_at)


def environment_from_wire(item: dict) -> Environment:
    payload = dict(item["payload"])
    payload["id"] = item["id"]
    if "name" not in payload and item.get("label"):
        payload["name"] = item["label"]
    env = Environment.from_dict(payload)
    env.updated_at = item["client_updated_at"]
    return env


def tombstone_to_wire(item_id: str, deleted_at: int) -> dict:
    return {"id": item_id, "deleted": True, "client_updated_at": deleted_at}
