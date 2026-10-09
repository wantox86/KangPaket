"""
KangPaket — Cloud Sync HTTP client (talks to KangPaket-server).

Access token lives in memory only; the refresh token is persisted in SyncState.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import httpx

from app.config import SYNC_DEFAULT_URL, SYNC_HTTP_TIMEOUT, SYNC_SETTINGS_URL_KEY, USER_AGENT
from app.core.sync_state import SyncState


class SyncError(Exception):
    """Base error; str(e) is a user-presentable message."""

    def __init__(self, message: str, *, status: int | None = None, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class AuthError(SyncError):
    """Credentials rejected or session expired; the user must log in again."""


class NetworkError(SyncError):
    """Server unreachable (DNS, connect, timeout)."""


class RateLimited(SyncError):
    def __init__(self, message: str, *, retry_after: float = 0.0, **kw) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


class PayloadTooLarge(SyncError):
    pass


class ServerError(SyncError):
    pass


class RequestRejected(SyncError):
    """Other 4xx (bad request)."""


_CODE_MESSAGES = {
    "payload_too_large": "Data yang dikirim terlalu besar.",
    "too_many_items": "Terlalu banyak item dalam satu kiriman.",
    "item_too_large": "Ada item yang melebihi batas ukuran 256 KiB.",
    "invalid_id": "ID item tidak valid.",
    "invalid_payload": "Isi item tidak valid.",
    "rate_limited": "Terlalu banyak permintaan, coba lagi sebentar.",
}


def resolve_server_url(settings=None, state: SyncState | None = None) -> str:
    """Settings override > URL stored at login > built-in default."""
    url = ""
    if settings is not None:
        url = str(settings.get(SYNC_SETTINGS_URL_KEY) or "")
    if not url and state is not None:
        url = state.server_url
    return (url or SYNC_DEFAULT_URL).strip().rstrip("/")


@dataclass(frozen=True)
class PendingLogin:
    """Tokens of a successful login that has not been stored yet (account-switch confirmation)."""
    base_url: str
    username: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


class SyncClient:
    def __init__(
        self,
        state: SyncState,
        base_url: str = SYNC_DEFAULT_URL,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = SYNC_HTTP_TIMEOUT,
    ) -> None:
        self._state = state
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
        self._access_token = ""
        self._refresh_lock = threading.Lock()

    def close(self) -> None:
        self._http.close()

    @property
    def logged_in(self) -> bool:
        return self._state.logged_in

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        self.commit_login(self.authenticate(username, password))

    def authenticate(self, username: str, password: str) -> "PendingLogin":
        """Validate credentials against the server WITHOUT storing anything locally."""
        data = self._send("POST", "/auth/login", json={"username": username, "password": password})
        return PendingLogin(self.base_url, username.strip().lower(), data["access_token"], data["refresh_token"])

    def commit_login(self, pending: "PendingLogin") -> None:
        self._access_token = pending.access_token
        self._state.begin_session(pending.base_url, pending.username, pending.refresh_token)

    def discard_login(self, pending: "PendingLogin") -> None:
        """Revoke an authenticated-but-never-committed login (best effort); local state untouched."""
        try:
            self._send("POST", "/auth/logout", json={"refresh_token": pending.refresh_token})
        except SyncError:
            pass

    def logout(self) -> None:
        """Best-effort server logout; local session is always cleared."""
        token = self._state.refresh_token
        try:
            if token:
                self._send("POST", "/auth/logout", json={"refresh_token": token})
        except SyncError:
            pass
        finally:
            self._access_token = ""
            self._state.end_session()

    def _refresh(self, stale_token: str) -> None:
        with self._refresh_lock:
            if self._access_token and self._access_token != stale_token:
                return
            refresh = self._state.refresh_token
            if not refresh:
                raise AuthError("Belum login.")
            try:
                data = self._send("POST", "/auth/refresh", json={"refresh_token": refresh})
            except AuthError:
                self._access_token = ""
                self._state.set_refresh_token("")
                raise AuthError("Sesi berakhir, silakan login ulang.") from None
            self._access_token = data["access_token"]
            self._state.set_refresh_token(data["refresh_token"])

    # ------------------------------------------------------------------
    # Sync endpoints
    # ------------------------------------------------------------------

    def pull(self, since: int, limit: int = 500) -> dict:
        return self._authed("GET", "/sync/pull", params={"since": since, "limit": limit})

    def push(self, profiles: list[dict], environments: list[dict]) -> dict:
        return self._authed("POST", "/sync/push", json={"profiles": profiles, "environments": environments})

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _authed(self, method: str, path: str, **kw) -> dict:
        if not self._access_token:
            self._refresh("")
        token = self._access_token
        try:
            return self._send(method, path, token=token, **kw)
        except AuthError:
            self._refresh(token)
            return self._send(method, path, token=self._access_token, **kw)

    def _send(self, method: str, path: str, *, token: str = "", **kw) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            resp = self._http.request(method, self.base_url + path, headers=headers, **kw)
        except httpx.TransportError as e:
            raise NetworkError("Tidak bisa terhubung ke server sync.") from e
        if resp.status_code < 300:
            if resp.status_code == 204 or not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as e:
                raise ServerError("Respons server tidak valid.", status=resp.status_code) from e
        raise self._error(resp, path)

    @staticmethod
    def _error(resp: httpx.Response, path: str) -> SyncError:
        try:
            code = str(resp.json().get("error", ""))
        except (ValueError, AttributeError):
            code = ""
        status = resp.status_code
        kw = {"status": status, "code": code}
        if status == 401:
            msg = "Username atau password salah." if path == "/auth/login" else "Sesi berakhir, silakan login ulang."
            return AuthError(msg, **kw)
        if status == 429:
            try:
                retry = float(resp.headers.get("Retry-After", "") or 0)
            except ValueError:
                retry = 0.0
            return RateLimited(_CODE_MESSAGES["rate_limited"], retry_after=retry, **kw)
        if status == 413:
            return PayloadTooLarge(_CODE_MESSAGES.get(code, "Data terlalu besar."), **kw)
        if status >= 500:
            return ServerError("Server sync sedang bermasalah.", **kw)
        return RequestRejected(_CODE_MESSAGES.get(code, f"Permintaan ditolak ({code or status})."), **kw)
