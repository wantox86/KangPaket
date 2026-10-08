"""
KangPaket — Environment manager (reads/writes data/environments.json).

File format: {"active": <env id | null>, "globals": [Variable...],
"globals_updated_at": <unix ms>, "envs": [Environment...]}

Every env (and the globals block) carries an `updated_at` unix-ms stamp that is bumped
whenever its content changes on save; Cloud Sync uses it for last-write-wins.
"""
import json
import os
import threading
import time

from app.config import ENVIRONMENTS_FILE
from app.models.environment_model import Environment, Variable


def _now_ms() -> int:
    return int(time.time() * 1000)


def _digest(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _layer(variables: list[Variable]) -> dict[str, str]:
    return {v.key.strip(): v.value for v in variables if v.enabled and v.key.strip()}


class EnvironmentManager:
    def __init__(self, path: str = ENVIRONMENTS_FILE) -> None:
        self._path = path
        # Guards stamping/writing against the Cloud Sync thread applying remote changes.
        self._lock = threading.RLock()
        self.active_id: str | None = None
        self.globals: list[Variable] = []
        self.envs: list[Environment] = []
        self.globals_updated_at: int = 0
        self._listeners: list = []
        self._delete_listeners: list = []
        self._data_listeners: list = []
        self._env_digests: dict[str, str] = {}
        self._globals_digest: str = ""
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        self.active_id, self.globals, self.envs = None, [], []
        self.globals_updated_at = 0
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.globals = [Variable.from_dict(v) for v in data.get("globals", [])]
                self.envs = [Environment.from_dict(e) for e in data.get("envs", [])]
                self.active_id = data.get("active")
                self.globals_updated_at = int(data.get("globals_updated_at") or 0)
                mtime = int(os.path.getmtime(self._path) * 1000)
                for env in self.envs:
                    if env.updated_at <= 0:
                        env.updated_at = mtime
            except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError) as e:
                print(f"[EnvironmentManager] Failed to load environments: {e}. Starting empty.")
                self.active_id, self.globals, self.envs = None, [], []
                self.globals_updated_at = 0
        if self.get(self.active_id) is None:
            self.active_id = None
        self._env_digests = {e.id: self._env_digest(e) for e in self.envs}
        self._globals_digest = self._vars_digest(self.globals)

    @staticmethod
    def _vars_digest(variables: list[Variable]) -> str:
        return _digest([v.to_dict() for v in variables])

    @staticmethod
    def _env_digest(env: Environment) -> str:
        d = env.to_dict()
        d.pop("updated_at", None)
        return _digest(d)

    def _stamp(self) -> tuple[bool, list[str]]:
        """Bump updated_at of changed envs/globals; return (anything_changed, removed_ids)."""
        changed = False
        now = _now_ms()
        digests: dict[str, str] = {}
        for env in self.envs:
            digests[env.id] = d = self._env_digest(env)
            if self._env_digests.get(env.id) != d:
                env.updated_at = max(now, env.updated_at + 1)
                changed = True
        removed = [i for i in self._env_digests if i not in digests]
        self._env_digests = digests
        g = self._vars_digest(self.globals)
        if g != self._globals_digest:
            self.globals_updated_at = max(now, self.globals_updated_at + 1)
            self._globals_digest = g
            changed = True
        return changed or bool(removed), removed

    def save(self) -> None:
        with self._lock:
            changed, removed = self._stamp()
            self._write()
        for env_id in removed:
            for cb in list(self._delete_listeners):
                self._safe(cb, env_id)
        if changed:
            for cb in list(self._data_listeners):
                self._safe(cb)

    @staticmethod
    def _safe(cb, *args) -> None:
        try:
            cb(*args)
        except Exception as e:
            print(f"[EnvironmentManager] listener failed: {e}")

    def _write(self) -> None:
        data = {
            "active": self.active_id,
            "globals": [v.to_dict() for v in self.globals],
            "globals_updated_at": self.globals_updated_at,
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

    def on_delete(self, callback) -> None:
        """Register callback(env_id) fired after an environment is removed and saved."""
        self._delete_listeners.append(callback)

    def on_data_change(self, callback) -> None:
        """Register a callback fired when env/globals content (not the active selection) changed."""
        self._data_listeners.append(callback)

    # ------------------------------------------------------------------
    # Remote apply (Cloud Sync): no stamping, no listeners
    # ------------------------------------------------------------------

    def apply_remote_env(self, env: Environment) -> None:
        with self._lock:
            for i, existing in enumerate(self.envs):
                if existing.id == env.id:
                    self.envs[i] = env
                    break
            else:
                self.envs.append(env)
            self._env_digests[env.id] = self._env_digest(env)
            self._write()

    def apply_remote_delete(self, env_id: str) -> None:
        with self._lock:
            self.envs = [e for e in self.envs if e.id != env_id]
            self._env_digests.pop(env_id, None)
            if self.get(self.active_id) is None:
                self.active_id = None
            self._write()

    def apply_remote_globals(self, variables: list[Variable], updated_at: int) -> None:
        with self._lock:
            self.globals = variables
            self.globals_updated_at = updated_at
            self._globals_digest = self._vars_digest(variables)
            self._write()

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
