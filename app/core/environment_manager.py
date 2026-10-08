"""
KangPaket — Environment manager (reads/writes data/environments.json).

File format: {"active": <env id | null>, "globals": [Variable...], "envs": [Environment...]}
"""
import json
import os

from app.config import ENVIRONMENTS_FILE
from app.models.environment_model import Environment, Variable


def _layer(variables: list[Variable]) -> dict[str, str]:
    return {v.key.strip(): v.value for v in variables if v.enabled and v.key.strip()}


class EnvironmentManager:
    def __init__(self, path: str = ENVIRONMENTS_FILE) -> None:
        self._path = path
        self.active_id: str | None = None
        self.globals: list[Variable] = []
        self.envs: list[Environment] = []
        self._listeners: list = []
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        self.active_id, self.globals, self.envs = None, [], []
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.globals = [Variable.from_dict(v) for v in data.get("globals", [])]
            self.envs = [Environment.from_dict(e) for e in data.get("envs", [])]
            self.active_id = data.get("active")
        except (json.JSONDecodeError, OSError, AttributeError, TypeError) as e:
            print(f"[EnvironmentManager] Failed to load environments: {e}. Starting empty.")
            self.active_id, self.globals, self.envs = None, [], []
        if self.get(self.active_id) is None:
            self.active_id = None

    def save(self) -> None:
        data = {
            "active": self.active_id,
            "globals": [v.to_dict() for v in self.globals],
            "envs": [e.to_dict() for e in self.envs],
        }
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            print(f"[EnvironmentManager] Failed to save environments: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, env_id: str | None) -> Environment | None:
        return next((e for e in self.envs if e.id == env_id), None) if env_id else None

    @property
    def active(self) -> Environment | None:
        return self.get(self.active_id)

    def set_active(self, env_id: str | None) -> None:
        self.active_id = env_id if self.get(env_id) else None
        self.save()
        self._notify()

    def add(self, env: Environment) -> Environment:
        self.envs.append(env)
        self.save()
        self._notify()
        return env

    def unique_name(self, base: str) -> str:
        names = {e.name for e in self.envs}
        if base not in names:
            return base
        n = 2
        while f"{base} ({n})" in names:
            n += 1
        return f"{base} ({n})"

    def layers(self) -> list[dict[str, str]]:
        """Environment layers for the resolver, highest priority first."""
        active = self.active
        return ([_layer(active.vars)] if active else []) + [_layer(self.globals)]

    def on_change(self, callback) -> None:
        """Register a callback fired after environments are modified."""
        self._listeners.append(callback)

    def changed(self) -> None:
        """Persist and notify; call after mutating envs/globals in place."""
        if self.get(self.active_id) is None:
            self.active_id = None
        self.save()
        self._notify()

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception as e:
                print(f"[EnvironmentManager] listener failed: {e}")
