"""
KangPaket — {{variable}} resolver shared by the request panel and the runner.

Layers are dicts ordered highest priority first; system variables ($guid, ...)
are the implicit lowest layer. Substitution is single-pass (values are never
re-expanded) and unknown placeholders are left as-is.
"""
from __future__ import annotations

import copy
import random
import re
import time
import uuid
from datetime import datetime, timezone

from app.models.request_model import RequestProfile

_PLACEHOLDER = re.compile(r"\{\{([^}]+)\}\}")


def system_vars() -> dict[str, str]:
    return {
        "$timestamp": str(int(time.time())),
        "$isoTimestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "$guid": str(uuid.uuid4()),
        "$randomInt": str(random.randint(0, 1000)),
    }


def _sub(text: str, layers: list[dict[str, str]], sysvars: dict[str, str]) -> str:
    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        for layer in layers:
            if key in layer:
                return str(layer[key])
        return sysvars.get(key, match.group(0))
    return _PLACEHOLDER.sub(_replace, text)


def resolve_text(text: str, layers: list[dict[str, str]]) -> str:
    return _sub(text, layers, system_vars())


def resolve_profile(
    profile: RequestProfile, layers: list[dict[str, str]]
) -> RequestProfile:
    """Return a shallow-copied profile with all {{var}} placeholders resolved.
    The original profile is not mutated."""
    sysvars = system_vars()

    def sub(text: str) -> str:
        return _sub(text, layers, sysvars)

    p = copy.copy(profile)
    p.url          = sub(p.url)
    p.headers      = {k: sub(v) for k, v in p.headers.items()}
    p.params       = {k: sub(v) for k, v in p.params.items()}
    p.body_content = sub(p.body_content)
    p.body_form    = {k: sub(v) for k, v in p.body_form.items()}
    p.auth_data    = {k: sub(str(v)) for k, v in p.auth_data.items()}
    p.assertions   = [
        {k: sub(v) if isinstance(v, str) else v for k, v in a.items()}
        for a in p.assertions
    ]
    return p
